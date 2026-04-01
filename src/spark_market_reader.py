# spark_market_reader.py
# Spark Protocol - deteccao de compressao e gatilho de explosao
# Gattiboni Enterprises - claudinho_o_sabio
#
# Logica:
#   1h + 15m : compressao de Bollinger (energia acumulando)
#   5m       : pre-sinal (tremidas com corpo, volume crescendo)
#   1m       : gatilho PAH (volume explode, corpo cheio, rompimento)
#
# Performance: fase 1 (1h + 15m) em paralelo para todos os ativos
#   Fases 2 e 3 permanecem sequenciais (universo ja reduzido)

import warnings
warnings.filterwarnings("ignore")

import requests
import pandas as pd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from spark_universe import get_spark_universe


# -----------------------------------------------------------------------
# CONFIGURACAO
# -----------------------------------------------------------------------

DEBUG = True

BINANCE_BASE_URL = "https://fapi.binance.com"
CANDLES_LIMIT    = 100

BB_PERIOD = 20
BB_STD    = 2.0

BBW_PERCENTILE_THRESHOLD = 25

PRESIGNAL_CANDLES     = 3
BODY_RATIO_MIN        = 0.4
VOLUME_CREEP_FACTOR   = 1.1

VOLUME_EXPLOSION_FACTOR = 3.0
BODY_FULL_RATIO         = 0.6

BB_SPREAD_LOW_THRESHOLD = 5.0
CALLBACK_LOW            = 3.0
CALLBACK_HIGH           = 5.0

MAX_WORKERS_FASE1 = 20

# Bear/crab mode
BEAR_PRESIGNAL_CANDLES = 2
BEAR_NEAR_UPPER_PCT    = 3.0
BEAR_VOLUME_EXPLOSION  = 2.0
BEAR_BODY_FULL_RATIO   = 0.5
BEAR_1M_BULLISH_MIN    = 3
BEAR_1M_VOL_ACCEL      = 1.3


# -----------------------------------------------------------------------
# INDICADORES NATIVOS
# -----------------------------------------------------------------------

def calc_bbands(series, period=BB_PERIOD, std=BB_STD):
    mid   = series.rolling(window=period).mean()
    sigma = series.rolling(window=period).std(ddof=0)
    upper = mid + std * sigma
    lower = mid - std * sigma
    return upper, mid, lower


# -----------------------------------------------------------------------
# COLETA DE DADOS
# -----------------------------------------------------------------------

def get_candles(symbol, interval, limit=CANDLES_LIMIT):
    url    = f"{BINANCE_BASE_URL}/fapi/v1/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        raw  = resp.json()
    except Exception:
        return None

    df = pd.DataFrame(raw, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_buy_base", "taker_buy_quote", "ignore"
    ])
    for col in ["open", "high", "low", "close", "volume", "quote_volume"]:
        df[col] = pd.to_numeric(df[col])
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    df.set_index("open_time", inplace=True)
    return df


# -----------------------------------------------------------------------
# INDICADORES
# -----------------------------------------------------------------------

def add_bbands(df):
    if df is None or len(df) < BB_PERIOD + 5:
        return None
    upper, mid, lower = calc_bbands(df["close"])
    df["bb_upper"]    = upper
    df["bb_mid"]      = mid
    df["bb_lower"]    = lower
    df["bb_width"]    = (upper - lower) / mid * 100
    df["volume_ma20"] = df["volume"].rolling(20).mean()
    return df


# -----------------------------------------------------------------------
# LOGICA DO SPARK
# -----------------------------------------------------------------------

def check_compression(df_1h, df_15m):
    if df_1h is None or df_15m is None:
        return False, {}

    df_1h  = add_bbands(df_1h)
    df_15m = add_bbands(df_15m)

    if df_1h is None or df_15m is None:
        return False, {}

    bbw_now_1h    = df_1h["bb_width"].iloc[-1]
    bbw_pct_1h    = (df_1h["bb_width"] <= bbw_now_1h).mean() * 100
    compressed_1h = bbw_pct_1h <= BBW_PERCENTILE_THRESHOLD

    bbw_now_15m    = df_15m["bb_width"].iloc[-1]
    bbw_pct_15m    = (df_15m["bb_width"] <= bbw_now_15m).mean() * 100
    compressed_15m = bbw_pct_15m <= BBW_PERCENTILE_THRESHOLD + 10

    passed  = compressed_1h and compressed_15m
    details = {
        "bbw_1h":             round(float(bbw_now_1h), 4),
        "bbw_percentile_1h":  round(bbw_pct_1h, 1),
        "compressed_1h":      compressed_1h,
        "bbw_15m":            round(float(bbw_now_15m), 4),
        "bbw_percentile_15m": round(bbw_pct_15m, 1),
        "compressed_15m":     compressed_15m,
    }
    return passed, details


def check_presignal(df_5m, regime="trending"):
    if df_5m is None:
        return False, {}

    bear_mode         = regime in ("crab", "bear")
    presignal_candles = BEAR_PRESIGNAL_CANDLES if bear_mode else PRESIGNAL_CANDLES
    near_upper_thresh = BEAR_NEAR_UPPER_PCT    if bear_mode else 1.5

    df_5m = add_bbands(df_5m)
    if df_5m is None:
        return False, {}

    recent = df_5m.iloc[-(presignal_candles + 1):-1]
    last   = df_5m.iloc[-1]

    bodies_ok = all(
        abs(row["close"] - row["open"]) / (row["high"] - row["low"] + 1e-10) >= BODY_RATIO_MIN
        for _, row in recent.iterrows()
    )

    closes_up = sum(
        1 for _, row in recent.iterrows() if row["close"] > row["open"]
    ) >= (presignal_candles - 1)

    vol_mean   = df_5m["volume_ma20"].iloc[-1]
    vol_creep  = recent["volume"].mean() >= vol_mean * VOLUME_CREEP_FACTOR
    vol_no_exp = recent["volume"].max() < vol_mean * 2.5

    dist_to_upper = (last["bb_upper"] - last["close"]) / last["bb_upper"] * 100
    near_upper    = dist_to_upper <= near_upper_thresh

    passed  = bodies_ok and closes_up and vol_creep and vol_no_exp and near_upper
    details = {
        "bodies_ok":         bodies_ok,
        "closes_up":         closes_up,
        "vol_creep":         vol_creep,
        "vol_no_explosion":  vol_no_exp,
        "near_upper_bb":     near_upper,
        "dist_to_upper_pct": round(dist_to_upper, 2),
    }
    return passed, details


def check_trigger(df_1m, regime="trending"):
    if df_1m is None:
        return False, {}

    bear_mode = regime in ("crab", "bear")
    vol_explosion_factor = BEAR_VOLUME_EXPLOSION if bear_mode else VOLUME_EXPLOSION_FACTOR
    body_full_ratio      = BEAR_BODY_FULL_RATIO  if bear_mode else BODY_FULL_RATIO

    df_1m = add_bbands(df_1m)
    if df_1m is None:
        return False, {}

    last = df_1m.iloc[-1]

    vol_mean      = df_1m["volume_ma20"].iloc[-1]
    vol_explosion = last["volume"] >= vol_mean * vol_explosion_factor

    candle_range = last["high"] - last["low"]
    body_ratio   = abs(last["close"] - last["open"]) / (candle_range + 1e-10)
    full_body    = body_ratio >= body_full_ratio

    if bear_mode:
        breakout = last["close"] > last["bb_mid"] and last["close"] > last["open"]
    else:
        breakout = last["close"] > last["bb_upper"]

    momentum_ok         = True
    momentum_bull_count = None
    momentum_vol_accel  = None

    if bear_mode and len(df_1m) >= 7:
        recent_5            = df_1m.iloc[-6:-1]
        momentum_bull_count = int((recent_5["close"] > recent_5["open"]).sum())
        vol_mean_5          = recent_5["volume"].mean()
        vol_accel           = recent_5["volume"].iloc[-3:].mean() / (vol_mean_5 + 1e-10)
        momentum_vol_accel  = round(float(vol_accel), 2)
        momentum_ok = (
            momentum_bull_count >= BEAR_1M_BULLISH_MIN and
            vol_accel >= BEAR_1M_VOL_ACCEL
        )

    spread   = (last["bb_upper"] - last["bb_lower"]) / last["bb_lower"] * 100
    sl_level = last["bb_lower"]
    sl_pct   = round((last["close"] - last["bb_lower"]) / last["close"] * 100, 2)
    callback = CALLBACK_HIGH if spread >= BB_SPREAD_LOW_THRESHOLD else CALLBACK_LOW

    passed  = vol_explosion and full_body and breakout and momentum_ok
    details = {
        "vol_explosion":          vol_explosion,
        "vol_ratio":              round(last["volume"] / (vol_mean + 1e-10), 2),
        "full_body":              full_body,
        "body_ratio":             round(body_ratio, 2),
        "breakout_upper_bb":      breakout,
        "entry_price":            round(float(last["close"]), 6),
        "sl_level":               round(float(sl_level), 6),
        "sl_pct_from_entry":      sl_pct,
        "trailing_callback_pct":  callback,
        "bb_spread_pct":          round(spread, 2),
        "bb_upper":               round(float(last["bb_upper"]), 6),
        "momentum_1m_bull_count": momentum_bull_count,
        "momentum_1m_vol_accel":  momentum_vol_accel,
    }
    return passed, details


# -----------------------------------------------------------------------
# WORKER PARALELO - FASE 1
# -----------------------------------------------------------------------

def fetch_compression(item):
    """Busca 1h e 15m e verifica compressao. Retorna item enriquecido ou None."""
    symbol = item["symbol"]
    df_1h  = get_candles(symbol, "1h")
    df_15m = get_candles(symbol, "15m")

    ok_comp, details_comp = check_compression(df_1h, df_15m)

    if not ok_comp:
        if DEBUG:
            motivos = []
            if not details_comp.get("compressed_1h"):
                motivos.append(f"1h:BBW_pct={details_comp.get('bbw_percentile_1h', '?')}%")
            if not details_comp.get("compressed_15m"):
                motivos.append(f"15m:BBW_pct={details_comp.get('bbw_percentile_15m', '?')}%")
            print(f"  [SKIP-COMP]  {symbol:20s} | {item['change_pct']:+6.2f}% | {', '.join(motivos)}")
        return None

    return {
        "item":         item,
        "details_comp": details_comp,
    }


# -----------------------------------------------------------------------
# SCANNER PRINCIPAL
# -----------------------------------------------------------------------

def scan_spark(regime="trending"):
    t_start = datetime.now()
    print(f"\n[{t_start.strftime('%H:%M:%S')}] Iniciando scan Spark...")
    print(f"[INFO] Regime atual: {regime}")

    universe = get_spark_universe()
    print(f"[INFO] {len(universe)} candidatos no universo Spark (esquecidos, sem movimento)")

    # Fase 1: compressao 1h + 15m em paralelo
    comprimidos = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_FASE1) as executor:
        futures = {executor.submit(fetch_compression, item): item for item in universe}
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                comprimidos.append(result)

    print(f"[INFO] {len(comprimidos)} ativos comprimidos encontrados")

    sparks = []

    # Fases 2 e 3: sequenciais sobre universo ja reduzido
    for candidate in comprimidos:
        item         = candidate["item"]
        symbol       = item["symbol"]
        change       = item["change_pct"]
        details_comp = candidate["details_comp"]

        df_5m = get_candles(symbol, "5m")
        ok_pre, details_pre = check_presignal(df_5m, regime=regime)

        if not ok_pre:
            if DEBUG:
                motivos = []
                if not details_pre.get("bodies_ok"):        motivos.append("5m:corpo_fraco")
                if not details_pre.get("closes_up"):         motivos.append("5m:direcao")
                if not details_pre.get("vol_creep"):         motivos.append("5m:vol_baixo")
                if not details_pre.get("vol_no_explosion"):  motivos.append("5m:vol_explodiu_cedo")
                if not details_pre.get("near_upper_bb"):     motivos.append(f"5m:longe_BB({details_pre.get('dist_to_upper_pct', '?')}%)")
                print(f"  [SKIP-PRE]   {symbol:20s} | {change:+6.2f}% | {', '.join(motivos)}")
            continue

        df_1m = get_candles(symbol, "1m")
        ok_trig, details_trig = check_trigger(df_1m, regime=regime)

        if not ok_trig:
            print(f"  [CANDIDATO]  {symbol:20s} | {change:+6.2f}% | comprimido + pre-sinal | aguardando PAH")
            continue

        spark = {
            "symbol":         symbol,
            "change_24h_pct": change,
            "volume_24h_usd": item["volume_24h"],
            "compression":    details_comp,
            "presignal":      details_pre,
            "trigger":        details_trig,
        }
        sparks.append(spark)
        print(f"  [SPARK]      {symbol:20s} | {change:+6.2f}% | PAH DETECTADO")

    elapsed = (datetime.now() - t_start).total_seconds()
    print(f"[INFO] Scan completo em {elapsed:.1f}s")

    return sparks


# -----------------------------------------------------------------------
# OUTPUT
# -----------------------------------------------------------------------

def print_spark(spark):
    s  = spark
    tr = s["trigger"]
    print("\n" + "=" * 60)
    print(f"SPARK: {s['symbol']}")
    print(f"Variacao 24h:   {s['change_24h_pct']:+.2f}%")
    print(f"Volume 24h:     ${s['volume_24h_usd']:,.0f}")
    print("-" * 60)
    print(f"Entrada:        {tr['entry_price']}")
    sl_warn = "  [ATENCAO: acima de 8%]" if tr["sl_pct_from_entry"] > 8 else ""
    print(f"SL (BB inf 1m): {tr['sl_level']}  (-{tr['sl_pct_from_entry']}%){sl_warn}")
    print(f"Trailing CB:    {tr['trailing_callback_pct']}%")
    print(f"BB spread 1m:   {tr['bb_spread_pct']}%")
    print("-" * 60)
    print("Compressao:")
    print(f"  1h  BBW:      {s['compression']['bbw_1h']}  (percentil {s['compression']['bbw_percentile_1h']}%)")
    print(f"  15m BBW:      {s['compression']['bbw_15m']}  (percentil {s['compression']['bbw_percentile_15m']}%)")
    print("Pre-sinal 5m:")
    print(f"  Corpo medio:  {s['presignal']['bodies_ok']}")
    print(f"  Fechando up:  {s['presignal']['closes_up']}")
    print(f"  Vol crescendo:{s['presignal']['vol_creep']}")
    print(f"  Dist BB sup:  {s['presignal']['dist_to_upper_pct']}%")
    print("Gatilho 1m:")
    print(f"  Volume ratio: {tr['vol_ratio']}x  explosao: {tr['vol_explosion']}")
    print(f"  Corpo cheio:  {tr['full_body']}  ({tr['body_ratio']})")
    print(f"  Rompimento:   {tr['breakout_upper_bb']}")
    print("=" * 60)


# -----------------------------------------------------------------------
# ENTRYPOINT
# -----------------------------------------------------------------------

if __name__ == "__main__":
    sparks = scan_spark()

    if not sparks:
        print("\nNenhum Spark detectado neste momento.")
    else:
        print(f"\n{len(sparks)} Spark(s) detectado(s):\n")
        for spark in sparks:
            print_spark(spark)
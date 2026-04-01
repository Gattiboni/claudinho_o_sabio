# top5_hunter.py
# Top 5 Hunter - Quais ativos tem maior probabilidade de atingir 5% na proxima hora?
# Gattiboni Enterprises - claudinho_o_sabio
#
# Logica:
#   1h  : veto de estrutura macro (MA + MACD)
#   15m : confirmacao de direcao (BB + TSI + StochRSI + MACD)
#   5m  : energia e pressao (Volume + MACD + StochRSI + proximidade BB)
#   1m  : gatilho iminente (Volume + corpo + StochRSI)
#
# Score maximo: 12 pontos (bonus +1 se TSI + StochRSI ambos confirmados no 15m)
# Filtro minimo: score >= 7
# Output: top 5 ativos com maior score
#
# Performance: requests paralelos em duas fases
#   Fase 1: 1h + 15m em paralelo para todos os ativos (veto + direcao)
#   Fase 2: 5m + 1m em paralelo apenas para quem passou a fase 1

import warnings
warnings.filterwarnings("ignore")

import requests
import pandas as pd
import numpy as np
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial


# -----------------------------------------------------------------------
# CONFIGURACAO
# -----------------------------------------------------------------------

BINANCE_BASE_URL = "https://fapi.binance.com"
CANDLES_LIMIT    = 100

# Universo
VOLUME_MIN_24H_USD  = 2_000_000
CHANGE_MIN_24H_PCT  = 10.0
EXCLUDE_SYMBOLS     = {"BTCUSDT", "ETHUSDT", "BNBUSDT"}

# Score minimo para aparecer no output
SCORE_MIN = 7

# Bollinger
BB_PERIOD = 20
BB_STD    = 2.0

# MACD
MACD_FAST   = 12
MACD_SLOW   = 26
MACD_SIGNAL = 9

# Stoch RSI
STOCH_RSI_PERIOD = 14
STOCH_RSI_K      = 3
STOCH_RSI_D      = 3

# TSI
TSI_FAST = 13
TSI_SLOW = 25

# MAs
MA_FAST = 7
MA_SLOW = 99

# Veto 1h
MACD_VETO_FACTOR = 0.5

# Score 5m
NEAR_BB_UPPER_PCT   = 2.0
VOLUME_ABOVE_FACTOR = 1.2

# Score 1m
VOLUME_EXPLOSION_FACTOR = 2.5
BODY_FULL_RATIO         = 0.5

# Paralelismo
MAX_WORKERS_FASE1 = 20
MAX_WORKERS_FASE2 = 10

# Bear/crab mode
BEAR_CHANGE_MIN_24H_PCT = 5.0
BEAR_SCORE_MIN          = 6
BEAR_1M_BULLISH_MIN     = 3
BEAR_1M_VOL_ACCEL       = 1.3


# -----------------------------------------------------------------------
# INDICADORES NATIVOS
# -----------------------------------------------------------------------

def calc_sma(series, period):
    return series.rolling(window=period).mean()


def calc_bbands(series, period=BB_PERIOD, std=BB_STD):
    mid   = series.rolling(window=period).mean()
    sigma = series.rolling(window=period).std(ddof=0)
    upper = mid + std * sigma
    lower = mid - std * sigma
    return upper, mid, lower


def calc_macd(series, fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL):
    ema_fast    = series.ewm(span=fast,   adjust=False).mean()
    ema_slow    = series.ewm(span=slow,   adjust=False).mean()
    macd_line   = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram   = macd_line - signal_line
    return macd_line, signal_line, histogram


def calc_rsi(series, period):
    delta    = series.diff()
    gain     = delta.clip(lower=0)
    loss     = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()
    rs  = avg_gain / (avg_loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calc_stochrsi(series, rsi_period=STOCH_RSI_PERIOD, stoch_period=STOCH_RSI_PERIOD,
                  k_period=STOCH_RSI_K, d_period=STOCH_RSI_D):
    rsi       = calc_rsi(series, rsi_period)
    rsi_min   = rsi.rolling(window=stoch_period).min()
    rsi_max   = rsi.rolling(window=stoch_period).max()
    stoch_rsi = (rsi - rsi_min) / (rsi_max - rsi_min + 1e-10) * 100
    k         = stoch_rsi.rolling(window=k_period).mean()
    d         = k.rolling(window=d_period).mean()
    return k, d


def calc_tsi(series, fast=TSI_FAST, slow=TSI_SLOW):
    delta             = series.diff()
    abs_delta         = delta.abs()
    smooth1           = delta.ewm(span=slow,   adjust=False).mean()
    double_smooth     = smooth1.ewm(span=fast, adjust=False).mean()
    smooth1_abs       = abs_delta.ewm(span=slow, adjust=False).mean()
    double_smooth_abs = smooth1_abs.ewm(span=fast, adjust=False).mean()
    tsi = 100 * double_smooth / (double_smooth_abs + 1e-10)
    return tsi


# -----------------------------------------------------------------------
# CALCULO DE INDICADORES
# -----------------------------------------------------------------------

def enrich(df):
    if df is None or len(df) < BB_PERIOD + 10:
        return None

    df["ma_fast"]                                = calc_sma(df["close"], MA_FAST)
    df["ma_slow"]                                = calc_sma(df["close"], MA_SLOW)
    df["bb_upper"], df["bb_mid"], df["bb_lower"] = calc_bbands(df["close"])
    _, _, df["macd_hist"]                        = calc_macd(df["close"])
    df["stoch_k"], _                             = calc_stochrsi(df["close"])
    df["tsi"]                                    = calc_tsi(df["close"])
    df["vol_ma20"]                               = df["volume"].rolling(20).mean()

    return df


# -----------------------------------------------------------------------
# COLETA DE DADOS
# -----------------------------------------------------------------------

def get_universe(change_min=CHANGE_MIN_24H_PCT):
    try:
        resp = requests.get(f"{BINANCE_BASE_URL}/fapi/v1/ticker/24hr", timeout=10)
        resp.raise_for_status()
        tickers = resp.json()
    except Exception as e:
        print(f"[ERRO] Tickers: {e}")
        return []

    try:
        resp2 = requests.get(f"{BINANCE_BASE_URL}/fapi/v1/exchangeInfo", timeout=10)
        resp2.raise_for_status()
        perpetuals = {
            s["symbol"] for s in resp2.json()["symbols"]
            if s.get("status") == "TRADING"
            and s.get("marginAsset") == "USDT"
            and s.get("contractType") == "PERPETUAL"
        }
    except Exception as e:
        print(f"[ERRO] ExchangeInfo: {e}")
        return []

    candidates = []
    for t in tickers:
        symbol = t.get("symbol", "")
        if symbol not in perpetuals:
            continue
        if symbol in EXCLUDE_SYMBOLS:
            continue
        try:
            volume = float(t["quoteVolume"])
            change = abs(float(t["priceChangePercent"]))
        except Exception:
            continue

        if volume < VOLUME_MIN_24H_USD:
            continue
        if change < change_min:
            continue

        candidates.append({
            "symbol":     symbol,
            "volume_24h": volume,
            "change_pct": float(t["priceChangePercent"]),
        })

    return candidates


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
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col])
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    df.set_index("open_time", inplace=True)
    return df


# -----------------------------------------------------------------------
# VETO 1H
# -----------------------------------------------------------------------

def check_veto_1h(df):
    if df is None or len(df) < 2:
        return True, "sem_dados"

    last = df.iloc[-1]

    if last["ma_fast"] < last["ma_slow"]:
        return True, "MA_veto"

    hist_abs_mean = df["macd_hist"].abs().tail(20).mean()
    if last["macd_hist"] < -(hist_abs_mean * MACD_VETO_FACTOR):
        return True, "MACD_veto"

    return False, None


# -----------------------------------------------------------------------
# SCORE 15M
# -----------------------------------------------------------------------

def score_15m(df):
    if df is None or len(df) < 2:
        return 0, {}

    last = df.iloc[-1]
    prev = df.iloc[-2]
    score = 0
    detail = {}

    bb_rising = last["bb_upper"] > df["bb_upper"].iloc[-5] and last["bb_lower"] > df["bb_lower"].iloc[-5]
    if bb_rising:
        score += 1
    detail["bb_rising"] = bb_rising

    tsi_ok = not pd.isna(last["tsi"]) and last["tsi"] > 0
    if tsi_ok:
        score += 1
    detail["tsi_positive"] = tsi_ok

    stoch_ok = last["stoch_k"] > 50 and last["stoch_k"] > prev["stoch_k"]
    if stoch_ok:
        score += 1
    detail["stoch_ok"] = stoch_ok
    detail["stoch_k"]  = round(last["stoch_k"], 1)

    macd_ok = last["macd_hist"] > 0 and last["macd_hist"] > prev["macd_hist"]
    if macd_ok:
        score += 1
    detail["macd_ok"]   = macd_ok
    detail["macd_hist"] = round(float(last["macd_hist"]), 6)

    double_confirm = tsi_ok and stoch_ok
    if double_confirm:
        score += 1
    detail["double_confirm"] = double_confirm

    return score, detail


# -----------------------------------------------------------------------
# SCORE 5M
# -----------------------------------------------------------------------

def score_5m(df):
    if df is None or len(df) < 2:
        return 0, {}

    last = df.iloc[-1]
    prev = df.iloc[-2]
    score = 0
    detail = {}

    bb_spread_pct = (last["bb_upper"] - last["bb_lower"]) / (last["bb_lower"] + 1e-10) * 100
    detail["bb_spread_pct"] = round(bb_spread_pct, 2)

    vol_ok = last["volume"] > last["vol_ma20"] * VOLUME_ABOVE_FACTOR
    if vol_ok:
        score += 1
    detail["volume_ok"] = vol_ok

    macd_ok = last["macd_hist"] > prev["macd_hist"]
    if macd_ok:
        score += 1
    detail["macd_rising"] = macd_ok

    stoch_ok = last["stoch_k"] > 50 and last["stoch_k"] > prev["stoch_k"]
    if stoch_ok:
        score += 1
    detail["stoch_ok"] = stoch_ok
    detail["stoch_k"]  = round(last["stoch_k"], 1)

    dist = (last["bb_upper"] - last["close"]) / last["bb_upper"] * 100
    near_upper = dist <= NEAR_BB_UPPER_PCT
    if near_upper:
        score += 1
    detail["near_upper"]     = near_upper
    detail["dist_upper_pct"] = round(dist, 2)

    return score, detail


# -----------------------------------------------------------------------
# SCORE 1M
# -----------------------------------------------------------------------

def score_1m(df):
    if df is None or len(df) < 2:
        return 0, {}

    last = df.iloc[-1]
    prev = df.iloc[-2]
    score = 0
    detail = {}

    vol_exp = last["volume"] >= last["vol_ma20"] * VOLUME_EXPLOSION_FACTOR
    if vol_exp:
        score += 1
    detail["vol_explosion"] = vol_exp
    detail["vol_ratio"]     = round(last["volume"] / (last["vol_ma20"] + 1e-10), 2)

    candle_range = last["high"] - last["low"]
    body_ratio   = abs(last["close"] - last["open"]) / (candle_range + 1e-10)
    full_body    = body_ratio >= BODY_FULL_RATIO
    if full_body:
        score += 1
    detail["full_body"]  = full_body
    detail["body_ratio"] = round(body_ratio, 2)

    stoch_ok = last["stoch_k"] > 50 and last["stoch_k"] > prev["stoch_k"]
    if stoch_ok:
        score += 1
    detail["stoch_ok"] = stoch_ok
    detail["stoch_k"]  = round(last["stoch_k"], 1)

    return score, detail


# -----------------------------------------------------------------------
# WORKERS PARALELOS
# -----------------------------------------------------------------------

def fetch_fase1(item):
    """Busca 1h e 15m. Retorna candidato enriquecido ou None se vetado."""
    symbol = item["symbol"]
    df_1h  = enrich(get_candles(symbol, "1h"))
    vetoed, _ = check_veto_1h(df_1h)
    if vetoed:
        return None

    df_15m   = enrich(get_candles(symbol, "15m"))
    s15, d15 = score_15m(df_15m)

    return {
        "item":       item,
        "score_15m":  s15,
        "detail_15m": d15,
    }


def fetch_fase2(candidate, regime="trending"):
    """Busca 5m e 1m para quem passou a fase 1."""
    symbol = candidate["item"]["symbol"]
    df_5m  = enrich(get_candles(symbol, "5m"))
    df_1m  = enrich(get_candles(symbol, "1m"))

    s5, d5 = score_5m(df_5m)
    s1, d1 = score_1m(df_1m)

    entry_price = float(df_5m.iloc[-1]["close"]) if df_5m is not None else None
    total_score = candidate["score_15m"] + s5 + s1

    detail_1m_momentum = None
    if regime in ("crab", "bear"):
        df_1m_raw = get_candles(symbol, "1m", limit=20)
        df_1m_enr = enrich(df_1m_raw)
        if df_1m_enr is not None and len(df_1m_enr) >= 7:
            recent_5    = df_1m_enr.iloc[-6:-1]
            bull_count  = int((recent_5["close"] > recent_5["open"]).sum())
            vol_mean_5  = recent_5["volume"].mean()
            vol_accel   = recent_5["volume"].iloc[-3:].mean() / (vol_mean_5 + 1e-10)
            momentum_ok = (
                bull_count >= BEAR_1M_BULLISH_MIN and
                vol_accel  >= BEAR_1M_VOL_ACCEL
            )
            if not momentum_ok:
                # Penalidade: reduz score em 1 (nao eliminacao direta, para nao ser muito restritivo)
                total_score -= 1
            detail_1m_momentum = {
                "bull_count":   bull_count,
                "vol_accel":    round(float(vol_accel), 2),
                "momentum_ok":  momentum_ok,
            }

    return {
        "symbol":              symbol,
        "change_pct":          candidate["item"]["change_pct"],
        "volume_24h":          candidate["item"]["volume_24h"],
        "score":               total_score,
        "score_15m":           candidate["score_15m"],
        "score_5m":            s5,
        "score_1m":            s1,
        "detail_15m":          candidate["detail_15m"],
        "detail_5m":           d5,
        "detail_1m":           d1,
        "detail_1m_momentum":  detail_1m_momentum,
        "entry_price":         entry_price,
    }


# -----------------------------------------------------------------------
# SCANNER PRINCIPAL
# -----------------------------------------------------------------------

def scan_top5(regime="trending"):
    t_start = datetime.now()
    print(f"\n[{t_start.strftime('%H:%M:%S')}] Top 5 Hunter iniciando...")

    bear_mode  = regime in ("crab", "bear")
    change_min = BEAR_CHANGE_MIN_24H_PCT if bear_mode else CHANGE_MIN_24H_PCT
    score_min  = BEAR_SCORE_MIN          if bear_mode else SCORE_MIN
    print(f"[INFO] Regime atual: {regime} | change_min={change_min}% | score_min={score_min}")

    universe = get_universe(change_min=change_min)
    print(f"[INFO] {len(universe)} ativos no universo (vol > $2M, variacao > {change_min}%)")

    if not universe:
        return []

    # Fase 1: veto 1h + score 15m em paralelo
    fase1_passed = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_FASE1) as executor:
        futures = {executor.submit(fetch_fase1, item): item for item in universe}
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                fase1_passed.append(result)

    print(f"[INFO] {len(fase1_passed)} ativos passaram o veto do 1h")

    if not fase1_passed:
        return []

    # Fase 2: score 5m + 1m em paralelo apenas para quem passou
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_FASE2) as executor:
        _fetch_fase2 = partial(fetch_fase2, regime=regime)
        futures = {executor.submit(_fetch_fase2, candidate): candidate for candidate in fase1_passed}
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                results.append(result)

    elapsed = (datetime.now() - t_start).total_seconds()
    print(f"[INFO] Scan completo em {elapsed:.1f}s")

    results.sort(key=lambda x: x["score"], reverse=True)
    results = [
        r for r in results
        if r["score"] >= score_min
        and r["detail_5m"].get("bb_spread_pct", 100.0) >= 3.0
    ]
    top5 = results[:5]

    return top5


# -----------------------------------------------------------------------
# OUTPUT
# -----------------------------------------------------------------------

def print_top5(results):
    if not results:
        print(f"\nNenhum ativo atingiu score minimo de {SCORE_MIN} neste momento.")
        return

    print(f"\n{'=' * 60}")
    print(f"TOP 5 HUNTER - {datetime.now().strftime('%H:%M:%S')}")
    print(f"Ativos com maior score para atingir 5% na proxima hora")
    print(f"{'=' * 60}")

    for i, r in enumerate(results, 1):
        double     = r['detail_15m'].get('double_confirm')
        double_tag = "  [DUPLA CONFIRMACAO TSI+STOCH]" if double else ""
        print(f"\n#{i} {r['symbol']}  |  {r['change_pct']:+.2f}% 24h  |  Score: {r['score']}/12{double_tag}")
        print(f"    Entrada:  {r['entry_price']}")
        print(f"    Vol 24h:  ${r['volume_24h']:,.0f}")
        print(f"    15m [{r['score_15m']}/5]: BB={r['detail_15m'].get('bb_rising')}  TSI={r['detail_15m'].get('tsi_positive')}  Stoch={r['detail_15m'].get('stoch_k')}  MACD={r['detail_15m'].get('macd_ok')}  Dupla={double}")
        print(f"    5m  [{r['score_5m']}/4]: Vol={r['detail_5m'].get('volume_ok')}  MACD={r['detail_5m'].get('macd_rising')}  Stoch={r['detail_5m'].get('stoch_k')}  DistBB={r['detail_5m'].get('dist_upper_pct')}%  BBspr={r['detail_5m'].get('bb_spread_pct')}%")
        print(f"    1m  [{r['score_1m']}/3]: VolExp={r['detail_1m'].get('vol_explosion')}({r['detail_1m'].get('vol_ratio')}x)  Corpo={r['detail_1m'].get('body_ratio')}  Stoch={r['detail_1m'].get('stoch_k')}")

    print(f"\n{'=' * 60}")
    print("Lembrete: score e sinal, nao certeza. Protocolo define a entrada.")
    print(f"{'=' * 60}\n")


# -----------------------------------------------------------------------
# ENTRYPOINT
# -----------------------------------------------------------------------

if __name__ == "__main__":
    top5 = scan_top5()
    print_top5(top5)
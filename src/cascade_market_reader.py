# cascade_market_reader.py
# Cascade Protocol - Fase 1: leitura de mercado e identificacao de setups
# Gattiboni Enterprises - claudinho_o_sabio
#
# Performance: requests paralelos em duas fases
#   Fase 1: 1h + 15m em paralelo para todos os ativos (veto + confirmacao)
#   Fase 2: 5m em paralelo apenas para quem passou a fase 1

import warnings
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial

warnings.filterwarnings("ignore", category=RuntimeWarning)


# -----------------------------------------------------------------------
# CONFIGURACAO
# -----------------------------------------------------------------------

DEBUG = True

BINANCE_BASE_URL   = "https://fapi.binance.com"
VOLUME_MIN_24H_USD = 2_000_000
TOP_BOTTOM_N       = 30
CANDLES_LIMIT      = 100

BB_PERIOD = 20
BB_STD    = 2.0

MACD_FAST   = 12
MACD_SLOW   = 26
MACD_SIGNAL = 9

STOCH_RSI_PERIOD = 14
STOCH_RSI_K      = 3
STOCH_RSI_D      = 3

TSI_FAST = 13
TSI_SLOW = 25

MA_PERIODS = [7, 25, 99]

BB_SPREAD_THRESHOLD_PCT  = 5.0
CALLBACK_LOW_VOLATILITY  = 1.0
CALLBACK_HIGH_VOLATILITY = 2.0

BTC_SYMBOL           = "BTCUSDT"
CORR_WINDOW          = 20
CORR_ALIGNED_MIN     = 0.6
CORR_INDEPENDENT_MAX = 0.4

MAX_WORKERS_FASE1 = 20
MAX_WORKERS_FASE2 = 10

# Bear/crab mode
BEAR_1M_BULLISH_MIN = 3
BEAR_1M_VOL_ACCEL   = 1.3


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
# COLETA DE DADOS
# -----------------------------------------------------------------------

def get_top_bottom_symbols(n=TOP_BOTTOM_N, volume_min=VOLUME_MIN_24H_USD):
    url = f"{BINANCE_BASE_URL}/fapi/v1/ticker/24hr"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        tickers = response.json()
    except Exception as e:
        print(f"[ERRO] Falha ao buscar tickers: {e}")
        return []

    filtered = []
    for t in tickers:
        try:
            symbol = t["symbol"]
            if not symbol.endswith("USDT"):
                continue
            volume = float(t["quoteVolume"])
            change = float(t["priceChangePercent"])
            if volume >= volume_min:
                filtered.append({"symbol": symbol, "change_pct": change, "volume": volume})
        except Exception:
            continue

    if not filtered:
        return []

    filtered.sort(key=lambda x: x["change_pct"])
    bottom = filtered[:n]
    top    = filtered[-n:]

    combined = {s["symbol"]: s for s in bottom + top}
    return list(combined.values())


def get_candles(symbol, interval, limit=CANDLES_LIMIT):
    url    = f"{BINANCE_BASE_URL}/fapi/v1/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        raw = response.json()
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
# CORRELACAO BTC
# -----------------------------------------------------------------------

def calc_btc_correlation(df_asset, df_btc, window=CORR_WINDOW):
    if df_asset is None or df_btc is None:
        return None
    if len(df_asset) < window or len(df_btc) < window:
        return None
    returns_asset = df_asset["close"].pct_change().tail(window)
    returns_btc   = df_btc["close"].pct_change().tail(window)
    if returns_asset.isnull().all() or returns_btc.isnull().all():
        return None
    try:
        corr = returns_asset.corr(returns_btc)
        return round(float(corr), 4)
    except Exception:
        return None


def classify_btc_correlation(corr):
    if corr is None:
        return "unknown"
    if corr >= CORR_ALIGNED_MIN:
        return "aligned"
    if corr <= CORR_INDEPENDENT_MAX:
        return "independent"
    return "dead_zone"


# -----------------------------------------------------------------------
# INDICADORES
# -----------------------------------------------------------------------

def calculate_indicators(df):
    if df is None or len(df) < BB_PERIOD + 10:
        return None

    for period in MA_PERIODS:
        df[f"ma{period}"] = calc_sma(df["close"], period)

    bb_upper, bb_mid, bb_lower = calc_bbands(df["close"])
    df["bb_upper"] = bb_upper
    df["bb_mid"]   = bb_mid
    df["bb_lower"] = bb_lower

    macd_line, signal_line, histogram = calc_macd(df["close"])
    df["macd"]        = macd_line
    df["macd_signal"] = signal_line
    df["macd_hist"]   = histogram

    stoch_k, stoch_d = calc_stochrsi(df["close"])
    df["stoch_k"] = stoch_k
    df["stoch_d"] = stoch_d

    df["tsi"]         = calc_tsi(df["close"])
    df["volume_ma20"] = df["volume"].rolling(20).mean()

    return df


# -----------------------------------------------------------------------
# LOGICA DO CASCADE
# -----------------------------------------------------------------------

def bb_spread_pct(row):
    try:
        return (row["bb_upper"] - row["bb_lower"]) / row["bb_lower"] * 100
    except Exception:
        return None


def bb_bands_rising(df, window=5):
    if df is None or len(df) < window + 1:
        return False
    return df["bb_upper"].iloc[-1] > df["bb_upper"].iloc[-window] and \
           df["bb_lower"].iloc[-1] > df["bb_lower"].iloc[-window]


def check_1h(df, regime="trending"):
    if df is None or len(df) < 2:
        return False, {}
    last = df.iloc[-1]
    ma_veto       = last["ma7"] < last["ma99"]
    hist_abs_mean = df["macd_hist"].abs().tail(20).mean()
    macd_veto     = last["macd_hist"] < -(hist_abs_mean * 0.5)

    bear_mode = regime in ("crab", "bear")

    # MA veto: hard em trending, warning em crab/bear
    ma_veto_warning = False
    if bear_mode and ma_veto:
        ma_veto_warning   = True
        ma_veto_effective = False   # nao bloqueia em bear/crab
    else:
        ma_veto_effective = ma_veto

    passed  = not ma_veto_effective and not macd_veto
    details = {
        "ma_veto":         ma_veto,
        "macd_veto":       macd_veto,
        "ma7_above_ma99":  last["ma7"] > last["ma99"],
        "macd_hist":       round(float(last["macd_hist"]), 8),
        "ma_veto_warning": ma_veto_warning,
    }
    return passed, details


def check_15m(df, df_btc_15m):
    if df is None or len(df) < 2:
        return False, {}
    last = df.iloc[-1]
    prev = df.iloc[-2]

    stoch_rising  = last["stoch_k"] > prev["stoch_k"]
    stoch_above50 = last["stoch_k"] > 50
    stoch_ok      = stoch_rising and stoch_above50

    tsi_raw = last.get("tsi", float("nan"))
    tsi_ok  = (not pd.isna(tsi_raw)) and (tsi_raw > 0)

    bb_ok          = bb_bands_rising(df)
    corr_15m       = calc_btc_correlation(df, df_btc_15m)
    corr_class_15m = classify_btc_correlation(corr_15m)
    btc_ok         = corr_class_15m in ("aligned", "independent")

    passed  = stoch_ok and tsi_ok and bb_ok and btc_ok
    details = {
        "stoch_rsi_rising":  stoch_rising,
        "stoch_above_50":    stoch_above50,
        "stoch_k_value":     round(last["stoch_k"], 2),
        "tsi_positive":      tsi_ok,
        "bb_bands_rising":   bb_ok,
        "btc_correlation":   corr_15m,
        "btc_case":          corr_class_15m,
    }
    return passed, details


def check_5m(df, df_btc_5m):
    if df is None or len(df) < 2:
        return False, {}
    last = df.iloc[-1]
    prev = df.iloc[-2]

    macd_ascending  = last["macd_hist"] > prev["macd_hist"]
    macd_positive   = last["macd_hist"] > 0
    macd_min_recent = df["macd_hist"].tail(10).min()
    if macd_positive:
        macd_ok = macd_ascending
    elif macd_ascending and macd_min_recent < 0:
        recovery = (last["macd_hist"] - macd_min_recent) / abs(macd_min_recent)
        macd_ok  = recovery >= 0.30
    else:
        macd_ok = False

    stoch_rising = last["stoch_k"] > prev["stoch_k"]
    tsi_raw      = last.get("tsi", float("nan"))
    tsi_rising   = (not pd.isna(tsi_raw)) and (tsi_raw > prev.get("tsi", float("nan")))
    tsi_positive = (not pd.isna(tsi_raw)) and (tsi_raw > 0)
    same_dir_ok  = stoch_rising and tsi_rising and tsi_positive

    bb_ok           = bb_bands_rising(df)
    price_above_ma7 = last["close"] > last["ma7"]
    spread          = bb_spread_pct(last)
    if spread is None:
        return False, {}

    sl_level = last["bb_lower"]
    sl_pct   = round((last["close"] - last["bb_lower"]) / last["close"] * 100, 2)
    callback = CALLBACK_HIGH_VOLATILITY if spread >= BB_SPREAD_THRESHOLD_PCT else CALLBACK_LOW_VOLATILITY

    corr_5m       = calc_btc_correlation(df, df_btc_5m)
    corr_class_5m = classify_btc_correlation(corr_5m)
    btc_ok        = corr_class_5m in ("aligned", "independent")

    try:
        if not macd_positive and macd_ascending and macd_min_recent < 0:
            macd_recovery_val = round((last["macd_hist"] - macd_min_recent) / abs(macd_min_recent) * 100, 1)
        else:
            macd_recovery_val = None
    except Exception:
        macd_recovery_val = None

    passed  = macd_ok and same_dir_ok and bb_ok and price_above_ma7 and btc_ok
    details = {
        "macd_ok":               macd_ok,
        "macd_positive":         macd_positive,
        "macd_ascending":        macd_ascending,
        "macd_recovery":         macd_recovery_val,
        "stoch_rsi_rising":      stoch_rising,
        "tsi_rising":            tsi_rising,
        "tsi_positive":          tsi_positive,
        "bb_bands_rising":       bb_ok,
        "price_above_ma7":       price_above_ma7,
        "bb_spread_pct":         round(spread, 2),
        "sl_level":              round(sl_level, 6),
        "sl_pct_from_entry":     sl_pct,
        "trailing_callback_pct": callback,
        "entry_price":           round(last["close"], 6),
        "bb_upper":              round(last["bb_upper"], 6),
        "bb_lower":              round(last["bb_lower"], 6),
        "btc_correlation":       corr_5m,
        "btc_case":              corr_class_5m,
    }
    return passed, details


# -----------------------------------------------------------------------
# WORKERS PARALELOS
# -----------------------------------------------------------------------

def fetch_fase1(item, df_btc_15m, regime="trending"):
    symbol = item["symbol"]
    if symbol == BTC_SYMBOL:
        return None

    df_1h = calculate_indicators(get_candles(symbol, "1h"))
    ok_1h, details_1h = check_1h(df_1h, regime=regime)
    if not ok_1h:
        if DEBUG:
            motivos = []
            if details_1h.get("ma_veto"):   motivos.append("1h:MA_veto")
            if details_1h.get("macd_veto"): motivos.append("1h:MACD_veto")
            print(f"  [SKIP] {symbol:20s} | {item['change_pct']:+6.2f}% | {', '.join(motivos)}")
        return None

    df_15m = calculate_indicators(get_candles(symbol, "15m"))
    ok_15m, details_15m = check_15m(df_15m, df_btc_15m)

    return {
        "item":        item,
        "ok_15m":      ok_15m,
        "details_1h":  details_1h,
        "details_15m": details_15m,
    }


def fetch_fase2(candidate, df_btc_5m, regime="trending"):
    item        = candidate["item"]
    symbol      = item["symbol"]
    details_1h  = candidate["details_1h"]
    details_15m = candidate["details_15m"]
    ok_15m      = candidate["ok_15m"]

    df_5m = calculate_indicators(get_candles(symbol, "5m"))
    ok_5m, details_5m = check_5m(df_5m, df_btc_5m)

    if ok_15m and ok_5m:
        result_1m = None
        if regime in ("crab", "bear"):
            df_1m = get_candles(symbol, "1m", limit=20)
            if df_1m is not None and len(df_1m) >= 7:
                recent_5    = df_1m.iloc[-6:-1]
                bull_count  = int((recent_5["close"] > recent_5["open"]).sum())
                vol_mean_5  = recent_5["volume"].mean()
                vol_accel   = recent_5["volume"].iloc[-3:].mean() / (vol_mean_5 + 1e-10)
                momentum_ok = (
                    bull_count >= BEAR_1M_BULLISH_MIN and
                    vol_accel  >= BEAR_1M_VOL_ACCEL
                )
                if not momentum_ok:
                    if DEBUG:
                        print(f"  [SKIP-1M]    {symbol:20s} | bear/crab: momentum 1m insuficiente (bull={bull_count}, vol_accel={vol_accel:.2f})")
                    return None
                result_1m = {"bull_count": bull_count, "vol_accel": round(float(vol_accel), 2)}

        return {
            "symbol":         symbol,
            "change_24h_pct": item["change_pct"],
            "volume_24h_usd": item["volume"],
            "1h":             details_1h,
            "15m":            details_15m,
            "5m":             details_5m,
            "1m":             result_1m,
            "passed":         True,
        }

    if DEBUG:
        motivos = []
        if not ok_15m:
            if not details_15m.get("stoch_rsi_rising"):    motivos.append("15m:StochRSI")
            if not details_15m.get("stoch_above_50"):      motivos.append("15m:Stoch<50")
            if not details_15m.get("tsi_positive"):        motivos.append("15m:TSI")
            if not details_15m.get("bb_bands_rising"):     motivos.append("15m:BB_dir")
            if details_15m.get("btc_case") == "dead_zone": motivos.append("15m:BTC_dz")
            if details_15m.get("btc_case") == "unknown":   motivos.append("15m:BTC_unk")
        if not ok_5m:
            if not details_5m.get("macd_ascending"):       motivos.append("5m:MACD_flat")
            if not details_5m.get("macd_ok"):              motivos.append("5m:MACD_recovery<30%")
            if not details_5m.get("stoch_rsi_rising"):     motivos.append("5m:StochRSI")
            if not details_5m.get("tsi_rising"):           motivos.append("5m:TSI_flat")
            if not details_5m.get("bb_bands_rising"):      motivos.append("5m:BB_dir")
            if not details_5m.get("price_above_ma7"):      motivos.append("5m:MA7")
            if details_5m.get("btc_case") == "dead_zone":  motivos.append("5m:BTC_dz")
            if details_5m.get("btc_case") == "unknown":    motivos.append("5m:BTC_unk")
        print(f"  [SKIP] {symbol:20s} | {item['change_pct']:+6.2f}% | {', '.join(motivos)}")

    return None


# -----------------------------------------------------------------------
# SCANNER PRINCIPAL
# -----------------------------------------------------------------------

def scan_market(regime="trending"):
    t_start = datetime.now()
    print(f"\n[{t_start.strftime('%H:%M:%S')}] Iniciando scan Cascade...")
    print(f"[INFO] Regime atual: {regime}")

    symbols_data = get_top_bottom_symbols()
    if not symbols_data:
        print("[ERRO] Nenhum simbolo retornado.")
        return []

    print(f"[INFO] {len(symbols_data)} simbolos no universo (top/bottom {TOP_BOTTOM_N} por variacao 24h)")

    df_btc_15m = calculate_indicators(get_candles(BTC_SYMBOL, "15m"))
    df_btc_5m  = calculate_indicators(get_candles(BTC_SYMBOL, "5m"))

    fase1_passed = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_FASE1) as executor:
        _fetch_fase1 = partial(fetch_fase1, df_btc_15m=df_btc_15m, regime=regime)
        futures = {executor.submit(_fetch_fase1, item): item for item in symbols_data}
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                fase1_passed.append(result)

    print(f"[INFO] {len(fase1_passed)} simbolos passaram o veto do 1h")

    if not fase1_passed:
        elapsed = (datetime.now() - t_start).total_seconds()
        print(f"[INFO] Scan completo em {elapsed:.1f}s")
        return []

    setups = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_FASE2) as executor:
        _fetch_fase2 = partial(fetch_fase2, df_btc_5m=df_btc_5m, regime=regime)
        futures = {executor.submit(_fetch_fase2, candidate): candidate for candidate in fase1_passed}
        for future in as_completed(futures):
            result = future.result()
            if result is not None and result.get("passed"):
                setups.append(result)
                print(f"  [SETUP] {result['symbol']} | {result['change_24h_pct']:+.2f}% 24h | BTC 15m: {result['15m']['btc_case']} | BTC 5m: {result['5m']['btc_case']}")

    elapsed = (datetime.now() - t_start).total_seconds()
    print(f"[INFO] Scan completo em {elapsed:.1f}s")

    return setups


# -----------------------------------------------------------------------
# OUTPUT
# -----------------------------------------------------------------------

def print_setup(setup):
    s  = setup
    d5 = s["5m"]
    print("\n" + "=" * 60)
    print(f"CASCADE SETUP: {s['symbol']}")
    print(f"Variacao 24h:  {s['change_24h_pct']:+.2f}%")
    print(f"Volume 24h:    ${s['volume_24h_usd']:,.0f}")
    print("-" * 60)
    print(f"Entrada (preco atual):  {d5['entry_price']}")
    sl_warn = "  [ATENCAO: SL acima de 8%]" if d5['sl_pct_from_entry'] > 8 else ""
    print(f"SL (banda inf BB 5m):   {d5['sl_level']}  (-{d5['sl_pct_from_entry']}%){sl_warn}")
    print(f"Trailing callback:      {d5['trailing_callback_pct']}%")
    print(f"BB spread 5m:           {d5['bb_spread_pct']}%")
    print(f"BB superior 5m:         {d5['bb_upper']}")
    print("-" * 60)
    print("Confirmacoes:")
    print(f"  1h  - MA7 acima MA99:    {s['1h']['ma7_above_ma99']}  [veto MA: {s['1h']['ma_veto']}]")
    print(f"  1h  - MACD veto:         {s['1h']['macd_veto']}  (hist: {s['1h']['macd_hist']})")
    print(f"  15m - StochRSI subindo:  {s['15m']['stoch_rsi_rising']}  acima 50: {s['15m']['stoch_above_50']}  (valor: {s['15m']['stoch_k_value']})")
    print(f"  15m - TSI positivo:      {s['15m']['tsi_positive']}")
    print(f"  15m - BB inclinadas:     {s['15m']['bb_bands_rising']}")
    print(f"  15m - BTC correlacao:    {s['15m']['btc_correlation']}  [{s['15m']['btc_case']}]")
    macd_str = f"positivo: {s['5m']['macd_positive']}  ascendente: {s['5m']['macd_ascending']}"
    if not s['5m']['macd_positive'] and s['5m'].get('macd_recovery') is not None:
        macd_str += f"  recovery: {s['5m']['macd_recovery']}%"
    print(f"  5m  - MACD:              {macd_str}")
    print(f"  5m  - StochRSI subindo:  {s['5m']['stoch_rsi_rising']}  TSI subindo: {s['5m']['tsi_rising']}")
    print(f"  5m  - BB inclinadas:     {s['5m']['bb_bands_rising']}")
    print(f"  5m  - Preco > MA7:       {s['5m']['price_above_ma7']}")
    print(f"  5m  - BTC correlacao:    {s['5m']['btc_correlation']}  [{s['5m']['btc_case']}]")
    print("=" * 60)


# -----------------------------------------------------------------------
# ENTRYPOINT
# -----------------------------------------------------------------------

if __name__ == "__main__":
    setups = scan_market()

    if not setups:
        print("\nNenhum setup Cascade identificado neste momento.")
    else:
        print(f"\n{len(setups)} setup(s) Cascade encontrado(s):\n")
        for setup in setups:
            print_setup(setup)
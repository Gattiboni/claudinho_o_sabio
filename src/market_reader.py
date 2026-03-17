# market_reader.py
# Cascade Protocol - Fase 1: leitura de mercado e identificacao de setups
# Gattiboni Enterprises - claudinho_o_sabio

import warnings
import requests
import pandas as pd
import pandas_ta as ta
from datetime import datetime

warnings.filterwarnings("ignore", category=RuntimeWarning)


# -----------------------------------------------------------------------
# CONFIGURACAO
# -----------------------------------------------------------------------

BINANCE_BASE_URL  = "https://fapi.binance.com"
VOLUME_MIN_24H_USD = 10_000_000
TOP_BOTTOM_N      = 30
CANDLES_LIMIT     = 100

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
MA_PERIODS = [7, 25, 99]

# Cascade - risco
BB_SPREAD_THRESHOLD_PCT  = 5.0
CALLBACK_LOW_VOLATILITY  = 1.0
CALLBACK_HIGH_VOLATILITY = 2.0

# Correlacao BTC
BTC_SYMBOL           = "BTCUSDT"
CORR_WINDOW          = 20       # velas para calcular correlacao
CORR_ALIGNED_MIN     = 0.7     # acima disso: andando junto com BTC
CORR_INDEPENDENT_MAX = 0.3     # abaixo disso: vida propria


# -----------------------------------------------------------------------
# COLETA DE DADOS
# -----------------------------------------------------------------------

def get_top_bottom_symbols(n=TOP_BOTTOM_N, volume_min=VOLUME_MIN_24H_USD):
    """
    Retorna top N e bottom N simbolos USDT por variacao 24h,
    filtrados por volume minimo.
    """
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
    """
    Retorna DataFrame OHLCV para o simbolo e intervalo dados.
    """
    url    = f"{BINANCE_BASE_URL}/fapi/v1/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        raw = response.json()
    except Exception as e:
        print(f"[ERRO] Candles {symbol} {interval}: {e}")
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
    """
    Calcula correlacao de Pearson entre a variacao percentual do ativo
    e do BTC nas ultimas `window` velas.

    Retorna float entre -1 e 1, ou None se dados insuficientes.

    Interpretacao:
      > CORR_ALIGNED_MIN    : andando junto com BTC (caso A)
      < CORR_INDEPENDENT_MAX: vida propria, ignorando BTC (caso B)
      entre os dois         : zona morta, sem sinal claro
    """
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
    """
    Retorna o caso de correlacao para o Cascade:
      'aligned'     : andando junto com BTC forte (permitido)
      'independent' : vida propria, ignorando BTC (permitido)
      'dead_zone'   : zona morta entre os dois (descartado)
      'unknown'     : correlacao nao calculavel (descartado)
    """
    if corr is None:
        return "unknown"
    if corr >= CORR_ALIGNED_MIN:
        return "aligned"
    if corr <= CORR_INDEPENDENT_MAX:
        return "independent"
    return "dead_zone"


# -----------------------------------------------------------------------
# CALCULO DE INDICADORES
# -----------------------------------------------------------------------

def calculate_indicators(df):
    """
    Adiciona indicadores tecnicos ao DataFrame.
    """
    if df is None or len(df) < BB_PERIOD + 10:
        return None

    for period in MA_PERIODS:
        df[f"ma{period}"] = ta.sma(df["close"], length=period)

    bb = ta.bbands(df["close"], length=BB_PERIOD, std=BB_STD)
    if bb is not None:
        cols         = bb.columns.tolist()
        bb_lower_col = [c for c in cols if c.startswith("BBL")][0]
        bb_mid_col   = [c for c in cols if c.startswith("BBM")][0]
        bb_upper_col = [c for c in cols if c.startswith("BBU")][0]
        df["bb_upper"] = bb[bb_upper_col]
        df["bb_mid"]   = bb[bb_mid_col]
        df["bb_lower"] = bb[bb_lower_col]

    macd = ta.macd(df["close"], fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL)
    if macd is not None:
        df["macd"]        = macd[f"MACD_{MACD_FAST}_{MACD_SLOW}_{MACD_SIGNAL}"]
        df["macd_signal"] = macd[f"MACDs_{MACD_FAST}_{MACD_SLOW}_{MACD_SIGNAL}"]
        df["macd_hist"]   = macd[f"MACDh_{MACD_FAST}_{MACD_SLOW}_{MACD_SIGNAL}"]

    stoch = ta.stochrsi(df["close"], length=STOCH_RSI_PERIOD, rsi_length=STOCH_RSI_PERIOD,
                        k=STOCH_RSI_K, d=STOCH_RSI_D)
    if stoch is not None:
        cols          = stoch.columns.tolist()
        df["stoch_k"] = stoch[cols[0]]
        df["stoch_d"] = stoch[cols[1]]

    try:
        tsi = ta.tsi(df["close"], fast=TSI_FAST, slow=TSI_SLOW)
        if tsi is not None and not tsi.empty:
            df["tsi"] = tsi.iloc[:, 0]
        else:
            df["tsi"] = float("nan")
    except Exception:
        df["tsi"] = float("nan")

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


def check_1h(df):
    """
    Filtro macro no 1h:
    - MA7 > MA25 > MA99
    - MACD histograma positivo e crescente
    - Preco abaixo da banda superior
    """
    if df is None or len(df) < 2:
        return False, {}

    last = df.iloc[-1]
    prev = df.iloc[-2]

    ma_ok    = last["ma7"] > last["ma25"] and last["ma25"] > last["ma99"]
    macd_ok  = last["macd_hist"] > 0 and last["macd_hist"] > prev["macd_hist"]
    space_ok = last["close"] < last["bb_upper"]

    passed  = ma_ok and macd_ok and space_ok
    details = {
        "ma_alignment":      ma_ok,
        "macd_expanding":    macd_ok,
        "space_to_upper_bb": space_ok,
    }
    return passed, details


def check_15m(df, df_btc_15m, ma_alignment_1h=False):
    """
    Confirmacao no 15m:
    - StochRSI subindo (limite 80 dispensado se MA 1h alinhada)
    - TSI positivo
    - Volume acima da media
    - Correlacao BTC: alinhado ou independente (zona morta descartada)
    """
    if df is None or len(df) < 2:
        return False, {}

    last = df.iloc[-1]
    prev = df.iloc[-2]

    stoch_rising = last["stoch_k"] > prev["stoch_k"]
    if ma_alignment_1h:
        stoch_ok = stoch_rising
    else:
        stoch_ok = stoch_rising and last["stoch_k"] < 80

    tsi_raw = last.get("tsi", float("nan"))
    tsi_ok  = (not pd.isna(tsi_raw)) and (tsi_raw > 0)

    volume_ok = last["volume"] > last["volume_ma20"]

    corr_15m      = calc_btc_correlation(df, df_btc_15m)
    corr_class_15m = classify_btc_correlation(corr_15m)
    btc_ok        = corr_class_15m in ("aligned", "independent")

    passed  = stoch_ok and tsi_ok and volume_ok and btc_ok
    details = {
        "stoch_rsi_rising":     stoch_rising,
        "stoch_k_value":        round(last["stoch_k"], 2),
        "stoch_limit_bypassed": ma_alignment_1h and last["stoch_k"] >= 80,
        "tsi_positive":         tsi_ok,
        "volume_above_avg":     volume_ok,
        "btc_correlation":      corr_15m,
        "btc_case":             corr_class_15m,
    }
    return passed, details


def check_5m(df, df_btc_5m):
    """
    Entrada no 5m:
    - MACD cruzado ou expandindo
    - Preco acima da MA7
    - Espaco ate banda superior
    - Correlacao BTC: alinhado ou independente
    - Calcula SL e callback via spread BB
    """
    if df is None or len(df) < 2:
        return False, {}

    last = df.iloc[-1]
    prev = df.iloc[-2]

    macd_cross     = prev["macd"] <= prev["macd_signal"] and last["macd"] > last["macd_signal"]
    macd_expanding = last["macd_hist"] > 0 and last["macd_hist"] > prev["macd_hist"]
    macd_ok        = macd_cross or macd_expanding

    price_above_ma7 = last["close"] > last["ma7"]
    space_ok        = last["close"] < last["bb_upper"]

    spread = bb_spread_pct(last)
    if spread is None:
        return False, {}

    sl_level = last["bb_lower"]
    sl_pct   = round((last["close"] - last["bb_lower"]) / last["close"] * 100, 2)
    callback = CALLBACK_HIGH_VOLATILITY if spread >= BB_SPREAD_THRESHOLD_PCT else CALLBACK_LOW_VOLATILITY

    corr_5m      = calc_btc_correlation(df, df_btc_5m)
    corr_class_5m = classify_btc_correlation(corr_5m)
    btc_ok       = corr_class_5m in ("aligned", "independent")

    passed  = macd_ok and price_above_ma7 and space_ok and btc_ok
    details = {
        "macd_ok":              macd_ok,
        "macd_cross":           macd_cross,
        "price_above_ma7":      price_above_ma7,
        "space_to_upper_bb":    space_ok,
        "bb_spread_pct":        round(spread, 2),
        "sl_level":             round(sl_level, 6),
        "sl_pct_from_entry":    sl_pct,
        "trailing_callback_pct": callback,
        "entry_price":          round(last["close"], 6),
        "bb_upper":             round(last["bb_upper"], 6),
        "bb_lower":             round(last["bb_lower"], 6),
        "btc_correlation":      corr_5m,
        "btc_case":             corr_class_5m,
    }
    return passed, details


# -----------------------------------------------------------------------
# SCANNER PRINCIPAL
# -----------------------------------------------------------------------

def scan_market():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Iniciando scan Cascade...")

    symbols_data = get_top_bottom_symbols()
    if not symbols_data:
        print("[ERRO] Nenhum simbolo retornado.")
        return []

    print(f"[INFO] {len(symbols_data)} simbolos no universo (top/bottom {TOP_BOTTOM_N} por variacao 24h)")

    # BTC buscado uma vez, reutilizado para todos os ativos
    df_btc_15m = get_candles(BTC_SYMBOL, "15m")
    df_btc_5m  = get_candles(BTC_SYMBOL, "5m")

    setups = []

    for item in symbols_data:
        symbol = item["symbol"]
        if symbol == BTC_SYMBOL:
            continue

        change = item["change_pct"]

        df_1h  = calculate_indicators(get_candles(symbol, "1h"))
        df_15m = calculate_indicators(get_candles(symbol, "15m"))
        df_5m  = calculate_indicators(get_candles(symbol, "5m"))

        ok_1h,  details_1h  = check_1h(df_1h)
        ok_15m, details_15m = check_15m(df_15m, df_btc_15m,
                                         ma_alignment_1h=details_1h.get("ma_alignment", False))
        ok_5m,  details_5m  = check_5m(df_5m, df_btc_5m)

        if ok_1h and ok_15m and ok_5m:
            setup = {
                "symbol":         symbol,
                "change_24h_pct": change,
                "volume_24h_usd": item["volume"],
                "1h":             details_1h,
                "15m":            details_15m,
                "5m":             details_5m,
            }
            setups.append(setup)
            print(f"  [SETUP] {symbol} | {change:+.2f}% 24h | BTC 15m: {details_15m['btc_case']} | BTC 5m: {details_5m['btc_case']}")

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
    sl_warn = "  [ATENCAO: SL acima de 8% - considere -8% como teto]" if d5['sl_pct_from_entry'] > 8 else ""
    print(f"SL (banda inf BB 5m):   {d5['sl_level']}  (-{d5['sl_pct_from_entry']}%){sl_warn}")
    print(f"Trailing callback:      {d5['trailing_callback_pct']}%")
    print(f"BB spread 5m:           {d5['bb_spread_pct']}%")
    print(f"BB superior 5m:         {d5['bb_upper']}")
    print("-" * 60)
    print("Confirmacoes:")
    print(f"  1h  - MA alinhada:       {s['1h']['ma_alignment']}")
    print(f"  1h  - MACD expandindo:   {s['1h']['macd_expanding']}")
    print(f"  1h  - Espaco BB:         {s['1h']['space_to_upper_bb']}")

    stoch_line = f"  15m - StochRSI subindo:  {s['15m']['stoch_rsi_rising']}  (valor: {s['15m']['stoch_k_value']}"
    if s['15m']['stoch_limit_bypassed']:
        stoch_line += "  [limite 80 dispensado - MA 1h forte]"
    print(stoch_line + ")")

    print(f"  15m - TSI positivo:      {s['15m']['tsi_positive']}")
    print(f"  15m - Volume acima avg:  {s['15m']['volume_above_avg']}")
    print(f"  15m - BTC correlacao:    {s['15m']['btc_correlation']}  [{s['15m']['btc_case']}]")
    print(f"  5m  - MACD ok:           {s['5m']['macd_ok']}")
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
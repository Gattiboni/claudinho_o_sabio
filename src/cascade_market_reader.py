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

DEBUG = True  # False em producao

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
CORR_ALIGNED_MIN     = 0.6     # acima disso: andando junto com BTC
CORR_INDEPENDENT_MAX = 0.4     # abaixo disso: vida propria


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


def bb_bands_rising(df, window=5):
    """
    Verifica se ambas as bandas da Bollinger estao inclinadas para cima
    nas ultimas `window` velas. Nao precisa ser explosivo — so nao pode
    estar caindo.
    """
    if df is None or len(df) < window + 1:
        return False
    upper_rising = df["bb_upper"].iloc[-1] > df["bb_upper"].iloc[-window]
    lower_rising = df["bb_lower"].iloc[-1] > df["bb_lower"].iloc[-window]
    return upper_rising and lower_rising


def check_1h(df):
    """
    VETO no 1h — so rejeita se claramente contra o movimento.
    Nao e confirmacao, e freio de mao.

    Rejeita se:
    - MA completamente invertida (MA7 < MA99, tendencia baixista estrutural)
    - MACD fortemente negativo (histograma abaixo de zero por margem relevante)

    Passa em tudo mais — inclusive MAs em formacao ou MACD proximo de zero.
    """
    if df is None or len(df) < 2:
        return False, {}

    last = df.iloc[-1]

    # Veto de MA: so rejeita se MA7 abaixo de MA99 (inversao estrutural)
    ma_veto = last["ma7"] < last["ma99"]

    # Veto de MACD: so rejeita se histograma claramente negativo
    # Usa 20% da media do valor absoluto do hist como threshold de "claramente"
    hist_abs_mean = df["macd_hist"].abs().tail(20).mean()
    macd_veto = last["macd_hist"] < -(hist_abs_mean * 0.5)

    vetoed  = ma_veto or macd_veto
    passed  = not vetoed

    details = {
        "ma_veto":        ma_veto,
        "macd_veto":      macd_veto,
        "ma7_above_ma99": last["ma7"] > last["ma99"],
        "macd_hist":      round(float(last["macd_hist"]), 8),
    }
    return passed, details


def check_15m(df, df_btc_15m):
    """
    CONFIRMACAO no 15m:
    - StochRSI acima de 50 E ascendendo
    - TSI positivo
    - Ambas as bandas BB inclinadas para cima
    - Correlacao BTC: alinhado ou independente
    """
    if df is None or len(df) < 2:
        return False, {}

    last = df.iloc[-1]
    prev = df.iloc[-2]

    stoch_rising = last["stoch_k"] > prev["stoch_k"]
    stoch_above50 = last["stoch_k"] > 50
    stoch_ok = stoch_rising and stoch_above50

    tsi_raw = last.get("tsi", float("nan"))
    tsi_ok  = (not pd.isna(tsi_raw)) and (tsi_raw > 0)

    bb_ok = bb_bands_rising(df)

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
    """
    GATILHO no 5m — onde o setup aparece primeiro:
    - MACD positivo E ascendente (histograma crescendo)
    - StochRSI e TSI apontando na mesma direcao (ambos subindo)
    - Ambas as bandas BB inclinadas para cima
    - Preco acima da MA7
    - Correlacao BTC: alinhado ou independente
    - Calcula SL e callback via spread BB
    """
    if df is None or len(df) < 2:
        return False, {}

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # MACD ascendente em direcao ao zero ou acima dele
    # Sweet spot: histograma subindo com forca, independente do sinal
    # StochRSI e TSI ja confirmam — MACD ligeiramente antes do cruzamento e ouro
    macd_ascending = last["macd_hist"] > prev["macd_hist"]
    macd_positive  = last["macd_hist"] > 0
    # Aceita MACD ainda negativo se estiver claramente subindo em direcao ao zero
    # Threshold: histograma negativo mas ja recuperou pelo menos 30% do seu minimo recente
    macd_min_recent = df["macd_hist"].tail(10).min()
    if macd_positive:
        macd_ok = macd_ascending
    elif macd_ascending and macd_min_recent < 0:
        recovery = (last["macd_hist"] - macd_min_recent) / abs(macd_min_recent)
        macd_ok = recovery >= 0.30
    else:
        macd_ok = False

    # StochRSI e TSI na mesma direcao (ambos subindo)
    stoch_rising = last["stoch_k"] > prev["stoch_k"]
    tsi_raw      = last.get("tsi", float("nan"))
    tsi_rising   = (not pd.isna(tsi_raw)) and (tsi_raw > prev.get("tsi", float("nan")))
    tsi_positive = (not pd.isna(tsi_raw)) and (tsi_raw > 0)
    same_dir_ok  = stoch_rising and tsi_rising and tsi_positive

    # BB inclinadas para cima
    bb_ok = bb_bands_rising(df)

    # Preco acima da MA7
    price_above_ma7 = last["close"] > last["ma7"]

    # SL e callback via spread
    spread = bb_spread_pct(last)
    if spread is None:
        return False, {}

    sl_level = last["bb_lower"]
    sl_pct   = round((last["close"] - last["bb_lower"]) / last["close"] * 100, 2)
    callback = CALLBACK_HIGH_VOLATILITY if spread >= BB_SPREAD_THRESHOLD_PCT else CALLBACK_LOW_VOLATILITY

    # Correlacao BTC
    corr_5m       = calc_btc_correlation(df, df_btc_5m)
    corr_class_5m = classify_btc_correlation(corr_5m)
    btc_ok        = corr_class_5m in ("aligned", "independent")

    # Calcula recovery para exibir no output
    try:
        macd_min_recent = df["macd_hist"].tail(10).min()
        if not macd_positive and macd_ascending and macd_min_recent < 0:
            macd_recovery_val = round((last["macd_hist"] - macd_min_recent) / abs(macd_min_recent) * 100, 1)
        else:
            macd_recovery_val = None
    except Exception:
        macd_recovery_val = None

    passed  = macd_ok and same_dir_ok and bb_ok and price_above_ma7 and btc_ok
    details = {
        "macd_ok":              macd_ok,
        "macd_positive":        macd_positive,
        "macd_ascending":       macd_ascending,
        "macd_recovery":        macd_recovery_val,
        "stoch_rsi_rising":     stoch_rising,
        "tsi_rising":           tsi_rising,
        "tsi_positive":         tsi_positive,
        "bb_bands_rising":      bb_ok,
        "price_above_ma7":      price_above_ma7,
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
        ok_15m, details_15m = check_15m(df_15m, df_btc_15m)
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
        elif DEBUG:
            motivos = []
            if not ok_1h:
                if details_1h.get("ma_veto"):                  motivos.append("1h:MA_veto")
                if details_1h.get("macd_veto"):                motivos.append("1h:MACD_veto")
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
            print(f"  [SKIP] {symbol:20s} | {change:+6.2f}% | {', '.join(motivos)}")

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
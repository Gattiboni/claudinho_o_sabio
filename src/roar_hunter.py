# roar_hunter.py
# Roar Hunter - Ativos dormentes com momentum em recuperacao
# Gattiboni Enterprises - claudinho_o_sabio
#
# Logica:
#   Universo : perpétuos USDT-M, volume >$30M, variacao 24h <= +3%
#              volume 24h pelo menos 20% acima do dia anterior (vitalidade)
#   1h       : coracao do protocolo — BB aberta, direcao, posicao do close,
#              MACD positivo, TSI positivo e ascendente, StochRSI ascendente
#              StochRSI cruzado pra baixo = veto direto
#   1h bonus : analise do ultimo ciclo de MACD nos 100 candles — roar historico
#   15m      : confirmacao de direcao (BB + TSI + MACD)
#   5m       : energia e pressao (Volume + MACD)
#
# Score maximo: 13 pontos (7 no 1h + 1 bonus + 3 no 15m + 2 no 5m)
# Filtro minimo: score >= 9
# Output: top 5 ativos em ordem de score
#
# SL: banda inferior da BB do 1h
# Trailing CB: 2% fixo (horizonte de 2-4h, tese de swing)
# Alvo: 5-7% minimo, trailing define a saida

import warnings
warnings.filterwarnings("ignore")

import requests
import pandas as pd
import numpy as np
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed


# -----------------------------------------------------------------------
# CONFIGURACAO
# -----------------------------------------------------------------------

BINANCE_BASE_URL = "https://fapi.binance.com"
CANDLES_LIMIT    = 100

# Universo
VOLUME_MIN_24H_USD  = 2_000_000
CHANGE_MAX_24H_PCT  = 3.0
VOLUME_GROWTH_MIN   = 0.20
EXCLUDE_SYMBOLS     = {"BTCUSDT", "ETHUSDT", "BNBUSDT"}

# Score minimo para aparecer no output
SCORE_MIN = 9

# Bollinger
BB_PERIOD = 20
BB_STD    = 2.0

# Limiares 1h
BB_SPREAD_MIN_PCT      = 10.0
CLOSE_UPPER_RANGE_MAX  = 0.70
BB_RISING_LOOKBACK     = 5

# MACD
MACD_FAST   = 12
MACD_SLOW   = 26
MACD_SIGNAL = 9

# TSI
TSI_FAST = 13
TSI_SLOW = 25

# StochRSI
STOCH_RSI_PERIOD = 14
STOCH_RSI_K      = 3
STOCH_RSI_D      = 3
STOCH_K_MIN      = 40.0

# Analise historica de roar
ROAR_MIN_PCT          = 7.0
ROAR_LOOKFORWARD      = 20
MACD_CONFIRM_CANDLES  = 3

# Score 5m
VOLUME_ABOVE_FACTOR = 1.2

# Paralelismo
MAX_WORKERS_FASE1 = 20
MAX_WORKERS_FASE2 = 10


# -----------------------------------------------------------------------
# INDICADORES NATIVOS
# -----------------------------------------------------------------------

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
# ENRIQUECIMENTO
# -----------------------------------------------------------------------

def enrich(df):
    if df is None or len(df) < BB_PERIOD + 10:
        return None

    df["bb_upper"], df["bb_mid"], df["bb_lower"] = calc_bbands(df["close"])
    _, _, df["macd_hist"]                        = calc_macd(df["close"])
    df["stoch_k"], df["stoch_d"]                 = calc_stochrsi(df["close"])
    df["tsi"]                                    = calc_tsi(df["close"])
    df["vol_ma20"]                               = df["volume"].rolling(20).mean()

    return df


# -----------------------------------------------------------------------
# COLETA DE DADOS
# -----------------------------------------------------------------------

def get_universe():
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
            change = float(t["priceChangePercent"])
        except Exception:
            continue

        if volume < VOLUME_MIN_24H_USD:
            continue
        if change > CHANGE_MAX_24H_PCT:
            continue

        candidates.append({
            "symbol":     symbol,
            "volume_24h": volume,
            "change_pct": change,
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


def get_volume_growth(symbol):
    """
    Busca os 2 ultimos candles diarios e calcula crescimento de volume.
    Retorna (crescimento_pct, vol_hoje, vol_ontem) ou (None, None, None) em caso de erro.
    """
    df = get_candles(symbol, "1d", limit=2)
    if df is None or len(df) < 2:
        return None, None, None
    vol_hoje  = float(df["volume"].iloc[-1])
    vol_ontem = float(df["volume"].iloc[-2])
    if vol_ontem < 1e-10:
        return None, None, None
    growth = (vol_hoje - vol_ontem) / vol_ontem
    return growth, vol_hoje, vol_ontem


# -----------------------------------------------------------------------
# SCORE 1H
# -----------------------------------------------------------------------

def score_1h(df):
    """
    Retorna (vetado, score, detail).
    vetado=True encerra a analise do ativo imediatamente.
    Score maximo: 7 pontos + 1 bonus historico.
    """
    if df is None or len(df) < BB_RISING_LOOKBACK + 5:
        return True, 0, {"veto_reason": "sem_dados"}

    last = df.iloc[-1]
    prev = df.iloc[-2]
    score  = 0
    detail = {}

    # Veto: StochRSI cruzado pra baixo (K abaixo de D e descendo)
    stoch_k = last["stoch_k"]
    stoch_d = last["stoch_d"]
    stoch_k_prev = prev["stoch_k"]
    stoch_d_prev = prev["stoch_d"]

    crossed_down = (
        not pd.isna(stoch_k) and not pd.isna(stoch_d)
        and stoch_k < stoch_d
        and stoch_k_prev >= stoch_d_prev
    )
    if crossed_down:
        return True, 0, {"veto_reason": "stochrsi_cruzado_baixo"}

    # Veto: close acima de 70% do range BB — movimento ja consumido
    bb_range = last["bb_upper"] - last["bb_lower"]
    if bb_range < 1e-10:
        return True, 0, {"veto_reason": "bb_range_zero"}

    close_position = (last["close"] - last["bb_lower"]) / bb_range
    if close_position > CLOSE_UPPER_RANGE_MAX:
        return True, 0, {"veto_reason": "close_acima_70pct_range"}

    detail["close_position_pct"] = round(close_position * 100, 1)

    # +1: BB spread > 10%
    bb_spread_pct = (bb_range / last["bb_mid"]) * 100 if last["bb_mid"] > 1e-10 else 0
    spread_ok = bb_spread_pct >= BB_SPREAD_MIN_PCT
    if spread_ok:
        score += 1
    detail["bb_spread_pct"] = round(bb_spread_pct, 2)
    detail["spread_ok"]     = spread_ok

    # +1: ambas as bandas apontando pra cima
    ref = df.iloc[-(BB_RISING_LOOKBACK + 1)]
    bb_rising = (
        last["bb_upper"] > ref["bb_upper"]
        and last["bb_lower"] > ref["bb_lower"]
    )
    if bb_rising:
        score += 1
    detail["bb_rising"] = bb_rising

    # +1: close abaixo do BB mid
    below_mid = last["close"] < last["bb_mid"]
    if below_mid:
        score += 1
    detail["below_mid"] = below_mid

    # +1: MACD histograma positivo
    macd_positive = not pd.isna(last["macd_hist"]) and last["macd_hist"] > 0
    if macd_positive:
        score += 1
    detail["macd_positive"] = macd_positive
    detail["macd_hist"]     = round(float(last["macd_hist"]), 6) if not pd.isna(last["macd_hist"]) else None

    # +1: TSI acima de zero e ascendente
    tsi_ok = (
        not pd.isna(last["tsi"])
        and not pd.isna(prev["tsi"])
        and last["tsi"] > 0
        and last["tsi"] > prev["tsi"]
    )
    if tsi_ok:
        score += 1
    detail["tsi_ok"]  = tsi_ok
    detail["tsi_val"] = round(float(last["tsi"]), 2) if not pd.isna(last["tsi"]) else None

    # +1: StochRSI K >= 40 e ascendente
    stoch_ok = (
        not pd.isna(stoch_k)
        and stoch_k >= STOCH_K_MIN
        and stoch_k > stoch_k_prev
    )
    if stoch_ok:
        score += 1
    detail["stoch_ok"] = stoch_ok
    detail["stoch_k"]  = round(stoch_k, 1) if not pd.isna(stoch_k) else None

    # +1 bonus: analise historica de roar
    bonus, roar_detail = _analyze_roar_history(df)
    score += bonus
    detail["roar_bonus"]  = bonus == 1
    detail["roar_detail"] = roar_detail

    # SL: banda inferior do 1h
    sl_level = float(last["bb_lower"])
    sl_pct   = round((float(last["close"]) - sl_level) / float(last["close"]) * 100, 2)
    detail["sl_level"] = sl_level
    detail["sl_pct"]   = sl_pct

    return False, score, detail


def _analyze_roar_history(df):
    """
    Nos ultimos 100 candles do 1h, encontra cruzamentos validos de MACD pra cima
    (histograma positivo por pelo menos MACD_CONFIRM_CANDLES consecutivos).
    Mede amplitude maxima nos ROAR_LOOKFORWARD candles seguintes.
    Retorna (bonus, detail_dict).
    bonus=1 se em algum ciclo o ativo andou >= ROAR_MIN_PCT.
    """
    if df is None or len(df) < MACD_CONFIRM_CANDLES + ROAR_LOOKFORWARD + 5:
        return 0, {}

    hist    = df["macd_hist"].values
    closes  = df["close"].values
    n       = len(hist)
    roars   = []

    i = MACD_CONFIRM_CANDLES
    while i < n - ROAR_LOOKFORWARD:
        # Verifica cruzamento valido: MACD_CONFIRM_CANDLES positivos consecutivos
        # apos pelo menos um candle negativo
        window = hist[i - MACD_CONFIRM_CANDLES: i]
        if any(pd.isna(window)):
            i += 1
            continue
        if not all(h > 0 for h in window):
            i += 1
            continue
        if i - MACD_CONFIRM_CANDLES > 0 and hist[i - MACD_CONFIRM_CANDLES - 1] > 0:
            # Nao e um cruzamento novo — ja estava positivo antes
            i += 1
            continue

        # Cruzamento valido encontrado em i - MACD_CONFIRM_CANDLES
        entry_close = closes[i - MACD_CONFIRM_CANDLES]
        if entry_close < 1e-10:
            i += 1
            continue

        future_closes = closes[i: i + ROAR_LOOKFORWARD]
        max_close     = max(future_closes)
        amplitude_pct = (max_close - entry_close) / entry_close * 100
        candles_to_max = int(np.argmax(future_closes)) + 1

        roars.append({
            "amplitude_pct":  round(amplitude_pct, 2),
            "candles_to_max": candles_to_max,
        })

        # Avanca para apos o lookforward para nao sobrepor ciclos
        i += ROAR_LOOKFORWARD

    if not roars:
        return 0, {"cycles_found": 0}

    best = max(roars, key=lambda x: x["amplitude_pct"])
    qualified = [r for r in roars if r["amplitude_pct"] >= ROAR_MIN_PCT]

    if not qualified:
        return 0, {
            "cycles_found": len(roars),
            "best_pct":     best["amplitude_pct"],
            "qualified":    False,
        }

    avg_candles = round(sum(r["candles_to_max"] for r in qualified) / len(qualified), 1)

    return 1, {
        "cycles_found":    len(roars),
        "qualified":       True,
        "best_pct":        best["amplitude_pct"],
        "avg_candles_max": avg_candles,
    }


# -----------------------------------------------------------------------
# SCORE 15M
# -----------------------------------------------------------------------

def score_15m(df):
    if df is None or len(df) < 2:
        return 0, {}

    last = df.iloc[-1]
    prev = df.iloc[-2]
    score  = 0
    detail = {}

    # +1: BB apontando pra cima
    ref = df.iloc[-(BB_RISING_LOOKBACK + 1)] if len(df) > BB_RISING_LOOKBACK + 1 else df.iloc[0]
    bb_rising = (
        last["bb_upper"] > ref["bb_upper"]
        and last["bb_lower"] > ref["bb_lower"]
    )
    if bb_rising:
        score += 1
    detail["bb_rising"] = bb_rising

    # +1: TSI positivo e ascendente
    tsi_ok = (
        not pd.isna(last["tsi"])
        and not pd.isna(prev["tsi"])
        and last["tsi"] > 0
        and last["tsi"] > prev["tsi"]
    )
    if tsi_ok:
        score += 1
    detail["tsi_ok"]  = tsi_ok
    detail["tsi_val"] = round(float(last["tsi"]), 2) if not pd.isna(last["tsi"]) else None

    # +1: MACD histograma positivo
    macd_ok = not pd.isna(last["macd_hist"]) and last["macd_hist"] > 0
    if macd_ok:
        score += 1
    detail["macd_ok"]   = macd_ok
    detail["macd_hist"] = round(float(last["macd_hist"]), 6) if not pd.isna(last["macd_hist"]) else None

    return score, detail


# -----------------------------------------------------------------------
# SCORE 5M
# -----------------------------------------------------------------------

def score_5m(df):
    if df is None or len(df) < 2:
        return 0, {}

    last = df.iloc[-1]
    prev = df.iloc[-2]
    score  = 0
    detail = {}

    # +1: volume acima da MA20
    vol_ok = (
        not pd.isna(last["vol_ma20"])
        and last["volume"] > last["vol_ma20"] * VOLUME_ABOVE_FACTOR
    )
    if vol_ok:
        score += 1
    detail["volume_ok"]  = vol_ok
    detail["vol_ratio"]  = round(last["volume"] / (last["vol_ma20"] + 1e-10), 2)

    # +1: MACD histograma positivo e ascendente
    macd_ok = (
        not pd.isna(last["macd_hist"])
        and not pd.isna(prev["macd_hist"])
        and last["macd_hist"] > 0
        and last["macd_hist"] > prev["macd_hist"]
    )
    if macd_ok:
        score += 1
    detail["macd_ok"]   = macd_ok
    detail["macd_hist"] = round(float(last["macd_hist"]), 6) if not pd.isna(last["macd_hist"]) else None

    return score, detail


# -----------------------------------------------------------------------
# WORKERS PARALELOS
# -----------------------------------------------------------------------

def fetch_fase1(item):
    """
    Busca candles diarios (volume growth), 1h e 15m.
    Retorna candidato enriquecido ou None se vetado ou sem vitalidade.
    """
    symbol = item["symbol"]

    # Vitalidade: soma das ultimas 3 velas 1h >= 20% acima da soma das 3 anteriores
    df_1h_raw = get_candles(symbol, "1h")
    if df_1h_raw is None or len(df_1h_raw) < 6:
        return None

    vol_recent = float(df_1h_raw["volume"].iloc[-3:].sum())
    vol_prev   = float(df_1h_raw["volume"].iloc[-6:-3].sum())
    vol_growth = (vol_recent - vol_prev) / (vol_prev + 1e-10)

    if vol_growth < VOLUME_GROWTH_MIN:
        print(f"[DESCARTE] {symbol} — vol_growth={round(vol_growth, 3)}")
        return None

    df_1h = enrich(df_1h_raw)
    vetoed, s1h, d1h = score_1h(df_1h)
    if vetoed:
        print(f"[DESCARTE] {symbol} — veto 1h: {d1h.get('veto_reason')}")
        return None

    df_15m   = enrich(get_candles(symbol, "15m"))
    s15, d15 = score_15m(df_15m)

    return {
        "item":        item,
        "score_1h":    s1h,
        "detail_1h":   d1h,
        "score_15m":   s15,
        "detail_15m":  d15,
        "vol_growth":  round(vol_growth * 100, 1),
    }


def fetch_fase2(candidate):
    """Busca 5m para quem passou a fase 1."""
    symbol = candidate["item"]["symbol"]
    df_5m  = enrich(get_candles(symbol, "5m"))

    s5, d5 = score_5m(df_5m)

    entry_price = float(df_5m.iloc[-1]["close"]) if df_5m is not None else None

    total = candidate["score_1h"] + candidate["score_15m"] + s5

    return {
        "symbol":      symbol,
        "change_pct":  candidate["item"]["change_pct"],
        "volume_24h":  candidate["item"]["volume_24h"],
        "vol_growth":  candidate["vol_growth"],
        "score":       total,
        "score_1h":    candidate["score_1h"],
        "score_15m":   candidate["score_15m"],
        "score_5m":    s5,
        "detail_1h":   candidate["detail_1h"],
        "detail_15m":  candidate["detail_15m"],
        "detail_5m":   d5,
        "entry_price": entry_price,
    }


# -----------------------------------------------------------------------
# SCANNER PRINCIPAL
# -----------------------------------------------------------------------

def scan_roar():
    t_start = datetime.now()
    print(f"\n[{t_start.strftime('%H:%M:%S')}] Roar Hunter iniciando...")

    universe = get_universe()
    print(f"[INFO] {len(universe)} ativos no universo (vol > $30M, variacao <= +3%)")

    if not universe:
        return []

    # Fase 1: volume growth diario + score 1h + score 15m em paralelo
    fase1_passed = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_FASE1) as executor:
        futures = {executor.submit(fetch_fase1, item): item for item in universe}
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                fase1_passed.append(result)

    print(f"[INFO] {len(fase1_passed)} ativos passaram veto e vitalidade")

    if not fase1_passed:
        return []

    # Fase 2: score 5m em paralelo apenas para quem passou
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_FASE2) as executor:
        futures = {executor.submit(fetch_fase2, candidate): candidate for candidate in fase1_passed}
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                results.append(result)

    elapsed = (datetime.now() - t_start).total_seconds()
    print(f"[INFO] Scan completo em {elapsed:.1f}s")

    results.sort(key=lambda x: x["score"], reverse=True)
    results = [r for r in results if r["score"] >= SCORE_MIN]
    top5    = results[:5]

    return top5


# -----------------------------------------------------------------------
# OUTPUT
# -----------------------------------------------------------------------

def print_roar(results):
    if not results:
        print(f"\nNenhum ativo atingiu score minimo de {SCORE_MIN} neste momento.")
        return

    print(f"\n{'=' * 60}")
    print(f"ROAR HUNTER - {datetime.now().strftime('%H:%M:%S')}")
    print(f"Dormentes com momentum em recuperacao — alvo 5-7% em 2-4h")
    print(f"{'=' * 60}")

    for i, r in enumerate(results, 1):
        d1h = r["detail_1h"]
        d15 = r["detail_15m"]
        d5  = r["detail_5m"]

        sl_warn = "  [ATENCAO: SL acima de 8%]" if d1h.get("sl_pct", 0) > 8 else ""
        roar    = d1h.get("roar_detail", {})
        roar_str = ""
        if d1h.get("roar_bonus"):
            roar_str = f"  [ROAR: +{roar.get('best_pct')}% em {roar.get('avg_candles_max')} candles historico]"

        print(f"\n#{i} {r['symbol']}  |  {r['change_pct']:+.2f}% 24h  |  Score: {r['score']}/13{roar_str}")
        print(f"    Entrada:     {r['entry_price']}")
        sl_level_val = d1h.get('sl_level')
        sl_level_str = f"{sl_level_val:.4f}" if sl_level_val is not None else "n/a"
        print(f"    SL (BB 1h):  {sl_level_str}  (-{d1h.get('sl_pct', 'n/a')}%){sl_warn}")
        print(f"    Trailing CB: 2%")
        print(f"    Vol 24h:     ${r['volume_24h']:,.0f}  |  Crescimento vol: +{r['vol_growth']}%")
        print(
            f"    1h [{r['score_1h']}/8]: Spread={d1h.get('bb_spread_pct')}%  "
            f"BB={d1h.get('bb_rising')}  "
            f"Close={d1h.get('close_position_pct')}%range  "
            f"MACD={d1h.get('macd_positive')}  "
            f"TSI={d1h.get('tsi_ok')}({d1h.get('tsi_val')})  "
            f"Stoch={d1h.get('stoch_k')}"
        )
        print(
            f"    15m [{r['score_15m']}/3]: BB={d15.get('bb_rising')}  "
            f"TSI={d15.get('tsi_ok')}  "
            f"MACD={d15.get('macd_ok')}"
        )
        print(
            f"    5m  [{r['score_5m']}/2]: Vol={d5.get('volume_ok')}({d5.get('vol_ratio')}x)  "
            f"MACD={d5.get('macd_ok')}"
        )

    print(f"\n{'=' * 60}")
    print("Score e sinal, nao certeza. Protocolo define a entrada.")
    print(f"{'=' * 60}\n")


# -----------------------------------------------------------------------
# ENTRYPOINT
# -----------------------------------------------------------------------

if __name__ == "__main__":
    top5 = scan_roar()
    print_roar(top5)
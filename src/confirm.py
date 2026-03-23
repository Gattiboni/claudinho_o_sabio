# confirm.py
# Confirmador de ativo - valida em tempo real se um ativo visto na tela merece entrada
# Gattiboni Enterprises - claudinho_o_sabio
#
# Uso: py -3.11 src/confirm.py
# O script solicita o simbolo no terminal e devolve o score completo.
#
# analyze_to_dict(symbol) -> dict
#   Retorna os mesmos dados de analyze() em formato dict, para uso pelo runner e notifier.

import warnings
warnings.filterwarnings("ignore")

import requests
import pandas as pd
import numpy as np
from datetime import datetime


# -----------------------------------------------------------------------
# CONFIGURACAO
# -----------------------------------------------------------------------

BINANCE_BASE_URL = "https://fapi.binance.com"
CANDLES_LIMIT    = 100
SCORE_MIN        = 7

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

MA_FAST = 7
MA_SLOW = 99

MACD_VETO_FACTOR = 0.5

NEAR_BB_UPPER_PCT   = 2.0
VOLUME_ABOVE_FACTOR = 1.2

VOLUME_EXPLOSION_FACTOR = 2.5
BODY_FULL_RATIO         = 0.5


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
# COLETA E ENRIQUECIMENTO
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
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col])
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    df.set_index("open_time", inplace=True)
    return df


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


def validate_symbol(symbol):
    try:
        resp = requests.get(
            f"{BINANCE_BASE_URL}/fapi/v1/ticker/price",
            params={"symbol": symbol},
            timeout=10
        )
        return resp.status_code == 200
    except Exception:
        return False


# -----------------------------------------------------------------------
# VETO 1H
# -----------------------------------------------------------------------

def check_veto_1h(df):
    if df is None or len(df) < 2:
        return True, "sem dados suficientes"

    last = df.iloc[-1]

    if last["ma_fast"] < last["ma_slow"]:
        return True, "MA7 abaixo de MA99 — estrutura macro baixista"

    hist_abs_mean = df["macd_hist"].abs().tail(20).mean()
    if last["macd_hist"] < -(hist_abs_mean * MACD_VETO_FACTOR):
        return True, "MACD fortemente negativo no 1h"

    return False, None


# -----------------------------------------------------------------------
# SCORES
# -----------------------------------------------------------------------

def score_15m(df):
    if df is None or len(df) < 2:
        return 0, {}

    last  = df.iloc[-1]
    prev  = df.iloc[-2]
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


def score_5m(df):
    if df is None or len(df) < 2:
        return 0, {}

    last  = df.iloc[-1]
    prev  = df.iloc[-2]
    score = 0
    detail = {}

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


def score_1m(df):
    if df is None or len(df) < 2:
        return 0, {}

    last  = df.iloc[-1]
    prev  = df.iloc[-2]
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
# NUCLEO DE ANALISE
# -----------------------------------------------------------------------

def _build_result(symbol, df_5m, df_1h, df_15m, df_1m):
    """
    Executa veto, scores e monta o dict de resultado.
    Usado por analyze() e analyze_to_dict().
    """
    vetoed, veto_reason = check_veto_1h(df_1h)

    if vetoed:
        return {
            "symbol":      symbol,
            "vetoed":      True,
            "veto_reason": veto_reason,
        }

    s15, d15 = score_15m(df_15m)
    s5,  d5  = score_5m(df_5m)
    s1,  d1  = score_1m(df_1m)
    total    = s15 + s5 + s1

    entry_price = float(df_5m.iloc[-1]["close"]) if df_5m is not None else None
    sl_level    = float(df_5m.iloc[-1]["bb_lower"]) if df_5m is not None else None
    sl_pct      = round((entry_price - sl_level) / entry_price * 100, 2) if entry_price and sl_level else None
    bb_spread   = round((float(df_5m.iloc[-1]["bb_upper"]) - sl_level) / sl_level * 100, 2) if df_5m is not None else None
    callback    = 2.0 if bb_spread and bb_spread >= 5.0 else 1.0

    return {
        "symbol":      symbol,
        "vetoed":      False,
        "veto_reason": None,
        "total":       total,
        "score_15m":   s15,
        "score_5m":    s5,
        "score_1m":    s1,
        "detail_15m":  d15,
        "detail_5m":   d5,
        "detail_1m":   d1,
        "entry_price": entry_price,
        "sl_level":    sl_level,
        "sl_pct":      sl_pct,
        "bb_spread":   bb_spread,
        "callback":    callback,
        "sl_warning":  sl_pct is not None and sl_pct > 8,
        "confirmed":   total >= SCORE_MIN,
    }


# -----------------------------------------------------------------------
# INTERFACE TERMINAL
# -----------------------------------------------------------------------

def analyze(symbol):
    """Analisa o simbolo e imprime o resultado no terminal."""
    symbol = symbol.upper().strip()
    if not symbol.endswith("USDT"):
        symbol = symbol + "USDT"

    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Analisando {symbol}...")

    if not validate_symbol(symbol):
        print(f"  Simbolo {symbol} nao encontrado na Binance Futures.")
        return

    df_1h  = enrich(get_candles(symbol, "1h"))
    df_15m = enrich(get_candles(symbol, "15m"))
    df_5m  = enrich(get_candles(symbol, "5m"))
    df_1m  = enrich(get_candles(symbol, "1m"))

    r = _build_result(symbol, df_5m, df_1h, df_15m, df_1m)

    print(f"\n{'=' * 60}")
    print(f"CONFIRMADOR - {symbol}  |  {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'=' * 60}")

    if r["vetoed"]:
        print(f"\n  VETADO no 1h: {r['veto_reason']}")
        print(f"  Score: irrelevante — estrutura macro nao permite entrada.")
        print(f"\n{'=' * 60}\n")
        return

    print(f"  1h: passou o veto")

    double     = r["detail_15m"].get("double_confirm")
    double_tag = "  [DUPLA CONFIRMACAO TSI+STOCH]" if double else ""

    print(f"\n  Score: {r['total']}/12{double_tag}")
    print(f"  Entrada:        {r['entry_price']}")
    print(f"  SL (BB inf 5m): {r['sl_level']}  (-{r['sl_pct']}%)")
    print(f"  Trailing CB:    {r['callback']}%")
    print(f"  BB spread 5m:   {r['bb_spread']}%")

    if r["sl_warning"]:
        print(f"  ATENCAO: SL acima de 8% — revise o tamanho da posicao")

    d15 = r["detail_15m"]
    d5  = r["detail_5m"]
    d1  = r["detail_1m"]

    print(f"\n  15m [{r['score_15m']}/5]: BB={d15.get('bb_rising')}  TSI={d15.get('tsi_positive')}  Stoch={d15.get('stoch_k')}  MACD={d15.get('macd_ok')}  Dupla={double}")
    print(f"  5m  [{r['score_5m']}/4]:  Vol={d5.get('volume_ok')}  MACD={d5.get('macd_rising')}  Stoch={d5.get('stoch_k')}  DistBB={d5.get('dist_upper_pct')}%")
    print(f"  1m  [{r['score_1m']}/3]:  VolExp={d1.get('vol_explosion')}({d1.get('vol_ratio')}x)  Corpo={d1.get('body_ratio')}  Stoch={d1.get('stoch_k')}")

    status = "CONFIRMADO — score >= 7. Protocolo define a entrada." if r["confirmed"] else f"NAO CONFIRMADO — score {r['total']} abaixo do minimo {SCORE_MIN}."
    print(f"\n  {status}")
    print(f"\n{'=' * 60}\n")


# -----------------------------------------------------------------------
# INTERFACE DICT (para runner e notifier)
# -----------------------------------------------------------------------

def analyze_to_dict(symbol: str) -> dict:
    """
    Analisa o simbolo e retorna o resultado como dict.
    Nao imprime nada no terminal.
    Retorna None se o simbolo nao for encontrado na Binance.
    """
    symbol = symbol.upper().strip()
    if not symbol.endswith("USDT"):
        symbol = symbol + "USDT"

    if not validate_symbol(symbol):
        return None

    df_1h  = enrich(get_candles(symbol, "1h"))
    df_15m = enrich(get_candles(symbol, "15m"))
    df_5m  = enrich(get_candles(symbol, "5m"))
    df_1m  = enrich(get_candles(symbol, "1m"))

    return _build_result(symbol, df_5m, df_1h, df_15m, df_1m)


# -----------------------------------------------------------------------
# ENTRYPOINT
# -----------------------------------------------------------------------

if __name__ == "__main__":
    while True:
        try:
            raw = input("Insira o ativo e pressione Enter (ou CTRL+C para sair): ").strip()
            if not raw:
                continue
            analyze(raw)
        except KeyboardInterrupt:
            print("\nSaindo.")
            break
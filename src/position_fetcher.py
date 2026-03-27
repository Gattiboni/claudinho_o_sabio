# position_fetcher.py
# Busca posicao aberta na Binance Futures + contexto de mercado (BB, MACD, StochRSI)
# Gattiboni Enterprises - claudinho_o_sabio
#
# Uso programatico:
#   from position_fetcher import get_open_position
#   pos = get_open_position("SOLUSDT")   # retorna None se sem posicao aberta

import requests
import pandas as pd

from binance_auth import signed_get

BINANCE_BASE_URL = "https://fapi.binance.com"
KLINES_LIMIT     = 100


# -----------------------------------------------------------------------
# UTILS
# -----------------------------------------------------------------------

def _normalize_symbol(symbol: str) -> str:
    s = symbol.upper().strip()
    if not s.endswith("USDT"):
        s += "USDT"
    return s


def _fetch_klines(symbol: str, interval: str) -> pd.DataFrame | None:
    try:
        resp = requests.get(
            f"{BINANCE_BASE_URL}/fapi/v1/klines",
            params={"symbol": symbol, "interval": interval, "limit": KLINES_LIMIT},
            timeout=10,
        )
        resp.raise_for_status()
        df = pd.DataFrame(resp.json(), columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_vol", "trades", "taker_base", "taker_quote", "ignore",
        ])
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = df[col].astype(float)
        return df
    except Exception as e:
        print(f"[POSITION_FETCHER] Erro ao buscar klines {symbol} {interval}: {e}")
        return None


def _calc_bb(close: pd.Series, period: int = 20, std: float = 2.0) -> dict:
    middle    = close.rolling(period).mean()
    deviation = close.rolling(period).std()
    upper     = middle + std * deviation
    lower     = middle - std * deviation
    spread    = (upper.iloc[-1] - lower.iloc[-1]) / middle.iloc[-1] * 100
    rising    = bool(lower.iloc[-1] > lower.iloc[-3] and upper.iloc[-1] > upper.iloc[-3])
    return {
        "upper":      round(float(upper.iloc[-1]),  6),
        "middle":     round(float(middle.iloc[-1]), 6),
        "lower":      round(float(lower.iloc[-1]),  6),
        "spread_pct": round(float(spread), 2),
        "rising":     rising,
    }


def _calc_macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd     = ema_fast - ema_slow
    sig      = macd.ewm(span=signal, adjust=False).mean()
    hist     = macd - sig
    return {
        "positive":  bool(hist.iloc[-1] > 0),
        "ascending": bool(hist.iloc[-1] > hist.iloc[-2]),
        "hist":      round(float(hist.iloc[-1]), 6),
    }


def _calc_stochrsi(close: pd.Series, rsi_period: int = 14, stoch_period: int = 14, smooth: int = 3) -> dict:
    delta   = close.diff()
    gain    = delta.clip(lower=0).rolling(rsi_period).mean()
    loss    = (-delta.clip(upper=0)).rolling(rsi_period).mean()
    rs      = gain / loss.replace(0, float("nan"))
    rsi     = 100 - (100 / (1 + rs))
    rsi_min = rsi.rolling(stoch_period).min()
    rsi_max = rsi.rolling(stoch_period).max()
    stoch   = (rsi - rsi_min) / (rsi_max - rsi_min).replace(0, float("nan")) * 100
    k       = stoch.rolling(smooth).mean()
    k_val   = float(k.iloc[-1]) if not pd.isna(k.iloc[-1]) else 50.0
    return {
        "k":        round(k_val, 2),
        "oversold": k_val < 20,
    }


# -----------------------------------------------------------------------
# INTERFACE PRINCIPAL
# -----------------------------------------------------------------------

def get_open_position(symbol: str) -> dict | None:
    """
    Busca posicao aberta na Binance Futures e contexto de mercado
    (BB, MACD, StochRSI em 15m e 5m).
    Retorna None se nao houver posicao aberta para o simbolo ou em caso de erro.
    """
    symbol = _normalize_symbol(symbol)

    data = signed_get("/fapi/v2/positionRisk", {"symbol": symbol})
    if not data:
        return None

    pos = next((p for p in data if float(p.get("positionAmt", 0)) != 0), None)
    if pos is None:
        return None

    position_amt    = float(pos["positionAmt"])
    entry_price     = float(pos["entryPrice"])
    mark_price      = float(pos["markPrice"])
    unrealized_pnl  = float(pos["unRealizedProfit"])
    leverage        = int(pos["leverage"])
    liq_price       = float(pos["liquidationPrice"])
    margin_type     = pos["marginType"]
    isolated_margin = float(pos.get("isolatedMargin", 0))

    direction   = "LONG" if position_amt > 0 else "SHORT"
    size_usdt   = abs(position_amt) * entry_price
    margin_used = isolated_margin if margin_type == "isolated" else size_usdt / leverage

    pnl_pct_margin = (unrealized_pnl / margin_used * 100) if margin_used > 0 else 0.0

    # Movimentacao de preco sem alavancagem (positivo = a favor da posicao)
    raw_pct_move = (mark_price - entry_price) / entry_price * 100
    if direction == "SHORT":
        raw_pct_move = -raw_pct_move

    context = {}
    for label, interval in [("15m", "15m"), ("5m", "5m")]:
        df = _fetch_klines(symbol, interval)
        if df is None or len(df) < 30:
            context[label] = None
            continue
        close = df["close"]
        bb    = _calc_bb(close)
        macd  = _calc_macd(close)
        stoch = _calc_stochrsi(close)
        dist_from_lower = (mark_price - bb["lower"]) / bb["lower"] * 100
        context[label] = {
            "bb":                  bb,
            "macd":                macd,
            "stoch":               stoch,
            "dist_from_lower_pct": round(dist_from_lower, 2),
        }

    return {
        "symbol":         symbol,
        "direction":      direction,
        "entry_price":    entry_price,
        "mark_price":     mark_price,
        "unrealized_pnl": round(unrealized_pnl, 2),
        "pnl_pct_margin": round(pnl_pct_margin, 2),
        "raw_pct_move":   round(raw_pct_move, 2),
        "leverage":       leverage,
        "liq_price":      liq_price,
        "margin_type":    margin_type,
        "margin_used":    round(margin_used, 2),
        "size_usdt":      round(size_usdt, 2),
        "15m":            context.get("15m"),
        "5m":             context.get("5m"),
    }

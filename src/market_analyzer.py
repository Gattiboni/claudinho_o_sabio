# market_analyzer.py
# Analisador de regime de mercado
# Gattiboni Enterprises - claudinho_o_sabio
#
# Regimes: trending | crab | bear
# Roda a cada hora (silencioso) ou sob demanda ("Claudinho, como ta hoje?")
# Persiste em market_regime no Supabase

import os
import requests
import pandas as pd
from datetime import datetime
import pytz

from dotenv import load_dotenv
from supabase_client import insert, select_ordered
from cryptopanic_client import fetch_important_news

load_dotenv()

BINANCE_BASE_URL = "https://fapi.binance.com"
TIMEZONE         = pytz.timezone("America/Sao_Paulo")
CANDLES_LIMIT    = 100
BTC_SYMBOL       = "BTCUSDT"

BB_PERIOD   = 20
BB_STD      = 2.0
MACD_FAST   = 12
MACD_SLOW   = 26
MACD_SIGNAL = 9
MA_PERIOD   = 7

VOLUME_MIN_24H  = 2_000_000
EXCLUDE_SYMBOLS = {"BTCUSDT", "ETHUSDT"}


# ---------------------------------------------------------------------------
# Indicadores tecnicos
# ---------------------------------------------------------------------------

def calc_bbands(series, period=BB_PERIOD, std=BB_STD):
    mid   = series.rolling(period).mean()
    sigma = series.rolling(period).std(ddof=0)
    upper = mid + std * sigma
    lower = mid - std * sigma
    return upper, mid, lower


def calc_macd(series, fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL):
    ema_fast    = series.ewm(span=fast, adjust=False).mean()
    ema_slow    = series.ewm(span=slow, adjust=False).mean()
    macd_line   = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram   = macd_line - signal_line
    return macd_line, signal_line, histogram


def calc_sma(series, period):
    return series.rolling(period).mean()


# ---------------------------------------------------------------------------
# Dados de mercado
# ---------------------------------------------------------------------------

def get_candles(symbol, interval, limit=CANDLES_LIMIT):
    try:
        resp = requests.get(
            f"{BINANCE_BASE_URL}/fapi/v1/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"[ANALYZER] Erro ao buscar candles {symbol} {interval}: {resp.status_code}")
            return None
        raw = resp.json()
        df = pd.DataFrame(raw, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades",
            "taker_buy_base", "taker_buy_quote", "ignore",
        ])
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        df.set_index("open_time", inplace=True)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
        return df
    except Exception as e:
        print(f"[ANALYZER] Erro ao buscar candles {symbol} {interval}: {e}")
        return None


def get_btc_metrics():
    df_1h = get_candles(BTC_SYMBOL, "1h")
    df_4h = get_candles(BTC_SYMBOL, "4h")

    if df_1h is None or len(df_1h) < 30:
        print("[ANALYZER] Dados insuficientes para BTC 1h.")
        return None
    if df_4h is None or len(df_4h) < 30:
        print("[ANALYZER] Dados insuficientes para BTC 4h.")
        return None

    upper_1h, mid_1h, lower_1h = calc_bbands(df_1h["close"])
    _, _, histogram             = calc_macd(df_1h["close"])
    df_1h["upper_bb"]   = upper_1h
    df_1h["mid_bb"]     = mid_1h
    df_1h["lower_bb"]   = lower_1h
    df_1h["macd_hist"]  = histogram

    df_4h["ma7"] = calc_sma(df_4h["close"], MA_PERIOD)

    btc_bb_mid    = df_1h["close"].iloc[-1] > mid_1h.iloc[-1]
    btc_bb_rising = (
        upper_1h.iloc[-1] > upper_1h.iloc[-5] and
        lower_1h.iloc[-1] > lower_1h.iloc[-5]
    )
    macd_hist_last = df_1h["macd_hist"].iloc[-1]
    macd_hist_prev = df_1h["macd_hist"].iloc[-2]
    btc_macd_ok   = (macd_hist_last > 0) and (macd_hist_last > macd_hist_prev)
    btc_ma7_4h    = df_4h["close"].iloc[-1] > df_4h["ma7"].iloc[-1]

    btc_score = int(sum([btc_bb_mid, btc_bb_rising, btc_macd_ok, btc_ma7_4h]))

    return {
        "btc_score":     btc_score,
        "btc_bb_mid":    bool(btc_bb_mid),
        "btc_bb_rising": bool(btc_bb_rising),
        "btc_macd_ok":   bool(btc_macd_ok),
        "btc_ma7_4h":    bool(btc_ma7_4h),
    }


def get_altcoin_breadth():
    try:
        resp = requests.get(
            f"{BINANCE_BASE_URL}/fapi/v1/ticker/24hr",
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"[ANALYZER] Erro ao buscar tickers: {resp.status_code}")
            return None
        tickers = resp.json()
    except Exception as e:
        print(f"[ANALYZER] Erro ao buscar tickers: {e}")
        return None

    filtered = [
        t for t in tickers
        if t["symbol"].endswith("USDT")
        and float(t["quoteVolume"]) >= VOLUME_MIN_24H
        and t["symbol"] not in EXCLUDE_SYMBOLS
    ]

    alts_above_3  = sum(1 for t in filtered if abs(float(t["priceChangePercent"])) > 3.0)
    alts_above_5  = sum(1 for t in filtered if abs(float(t["priceChangePercent"])) > 5.0)
    alts_above_10 = sum(1 for t in filtered if abs(float(t["priceChangePercent"])) > 10.0)

    return {
        "alts_above_3":  alts_above_3,
        "alts_above_5":  alts_above_5,
        "alts_above_10": alts_above_10,
    }


# ---------------------------------------------------------------------------
# Classificacao de regime
# ---------------------------------------------------------------------------

def classify_regime(btc_score, alts_above_5):
    if btc_score >= 3 and alts_above_5 >= 8:
        return "trending"
    elif btc_score <= 1 and alts_above_5 <= 3:
        return "bear"
    else:
        return "crab"


# ---------------------------------------------------------------------------
# Runner principal
# ---------------------------------------------------------------------------

def run_analyzer(triggered_by="schedule"):
    print(f"[ANALYZER] Iniciando analise de regime ({triggered_by})...")

    btc = get_btc_metrics()
    if btc is None:
        print("[ANALYZER] Aviso: falha em get_btc_metrics — usando defaults.")
        btc_score     = 2
        btc_bb_mid    = False
        btc_bb_rising = False
        btc_macd_ok   = False
        btc_ma7_4h    = False
    else:
        btc_score     = btc["btc_score"]
        btc_bb_mid    = btc["btc_bb_mid"]
        btc_bb_rising = btc["btc_bb_rising"]
        btc_macd_ok   = btc["btc_macd_ok"]
        btc_ma7_4h    = btc["btc_ma7_4h"]

    breadth = get_altcoin_breadth()
    if breadth is None:
        print("[ANALYZER] Aviso: falha em get_altcoin_breadth — usando defaults.")
        alts_above_3  = 0
        alts_above_5  = 0
        alts_above_10 = 0
    else:
        alts_above_3  = breadth["alts_above_3"]
        alts_above_5  = breadth["alts_above_5"]
        alts_above_10 = breadth["alts_above_10"]

    regime = classify_regime(btc_score, alts_above_5)

    news = fetch_important_news()
    news_headlines = [
        {
            "title":           n["title"],
            "published_at":    n["published_at"],
            "votes_important": n["votes_important"],
            "source_domain":   n["source_domain"],
        }
        for n in news[:5]
    ]

    result = {
        "regime":        regime,
        "btc_score":     btc_score,
        "btc_bb_mid":    btc_bb_mid,
        "btc_bb_rising": btc_bb_rising,
        "btc_macd_ok":   btc_macd_ok,
        "btc_ma7_4h":    btc_ma7_4h,
        "alts_above_3":  alts_above_3,
        "alts_above_5":  alts_above_5,
        "alts_above_10": alts_above_10,
        "news_headlines": news_headlines,
        "triggered_by":  triggered_by,
    }

    ok = insert("market_regime", result)
    if ok:
        print(f"[ANALYZER] Regime '{regime}' persistido no Supabase.")
    else:
        print(f"[ANALYZER] Falha ao persistir no Supabase.")

    print(f"[ANALYZER] Regime: {regime} | BTC score: {btc_score}/4 | Alts>5%: {alts_above_5}")
    return result


# ---------------------------------------------------------------------------
# Leitura do regime mais recente
# ---------------------------------------------------------------------------

def get_latest_regime() -> str:
    """
    Le o regime mais recente do Supabase.
    Retorna 'crab' em caso de falha (default seguro para os protocolos).
    """
    try:
        rows = select_ordered("market_regime", order_col="created_at", order_dir="desc", limit=1)
        if rows:
            return rows[0].get("regime", "crab")
    except Exception as e:
        print(f"[ANALYZER] Erro ao ler regime: {e}")
    return "crab"


# ---------------------------------------------------------------------------
# Formatacao da mensagem Telegram
# ---------------------------------------------------------------------------

def format_analyzer_message(result) -> str:
    now    = datetime.now(TIMEZONE)
    ts     = now.strftime("%H:%M - %a %d/%m/%Y")
    regime = result["regime"].upper()

    def yn(flag):
        return "Sim" if flag else "Nao"

    lines = [
        "<b>CLAUDINHO - ANALISE DE MERCADO</b>",
        f"<pre>{ts}</pre>",
        "",
        f"<b>REGIME: {regime}</b>",
        "",
        f"<b>BTC (1h/4h)  —  Score: {result['btc_score']}/4</b>",
        f"  Acima BB_mid:  {yn(result['btc_bb_mid'])}",
        f"  BB subindo:    {yn(result['btc_bb_rising'])}",
        f"  MACD ok:       {yn(result['btc_macd_ok'])}",
        f"  Acima MA7 4h:  {yn(result['btc_ma7_4h'])}",
        "",
        "<b>ALTCOINS  (vol > $2M, excl. BTC/ETH)</b>",
        f"  Acima +3%:   {result['alts_above_3']} ativos",
        f"  Acima +5%:   {result['alts_above_5']} ativos",
        f"  Acima +10%:  {result['alts_above_10']} ativos",
        "",
        "<b>NOTICIAS IMPORTANTES</b>",
    ]

    headlines = result.get("news_headlines", [])
    if headlines:
        for n in headlines:
            lines.append(f"  - {n['title']} ({n['source_domain']})")
    else:
        lines.append("  Nenhuma noticia importante no momento.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entrypoint standalone
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    result = run_analyzer(triggered_by="manual")
    print(format_analyzer_message(result))

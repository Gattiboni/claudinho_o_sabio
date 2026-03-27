# rescue_protocol.py
# Protocolo de gestao de posicao em baixa via Claude API
# Gattiboni Enterprises - claudinho_o_sabio
#
# Acionado por: "Claudinho e agora? SYMBOL"
# Fluxo: busca posicao aberta -> contexto de mercado -> Claude API -> 2 cenarios via Telegram
# Persistencia: scan_results (dados da posicao) + notifications_sent (para cruzamento no analyzer)

import os
import requests
from dotenv import load_dotenv

from position_fetcher import get_open_position
from notifier         import send_message
from supabase_client  import insert

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_URL     = "https://api.anthropic.com/v1/messages"
MODEL             = "claude-sonnet-4-20250514"
MAX_TOKENS        = 700


# -----------------------------------------------------------------------
# PROMPT
# -----------------------------------------------------------------------

SYSTEM_PROMPT = """You are a disciplined risk manager for Binance USDT-M perpetual futures.
You receive data about a losing open position and propose exactly 2 concrete management scenarios.

Hard rules:
- Never suggest adding margin, increasing size, or averaging down
- SL is always set at a Bollinger Band lower of a specific timeframe — never arbitrary
- If BB spread > 5%, trailing callback = 2%. If <= 5%, callback = 1%
- Distance from lower band is a key signal: price at or below lower band = potential floor, price far above = room to fall further
- StochRSI K < 20 = oversold, may suggest bounce. K > 80 = still has room to fall
- MACD ascending even if negative = momentum improving
- Choose the 2 most situationally relevant scenarios given the specific data:
    - Close immediately
    - Close 50% now, hold remainder with SL at 5m BB lower
    - Extend SL to 5m BB lower and hold
    - Extend SL to 15m BB lower and hold
    - Close now, place limit rebuy at current 5m BB lower with 2x-5x size, recalculate trailing TP from that level
    - Hold with current SL, wait for StochRSI bounce at oversold

Respond in Brazilian Portuguese.
Output format — follow exactly, no extra text:

CENARIO A: [nome curto]
Acao: [passos exatos com precos especificos]
Racional: [1-2 frases baseadas nos dados]
Risco: [o que faz esse cenario falhar]

CENARIO B: [nome curto]
Acao: [passos exatos com precos especificos]
Racional: [1-2 frases baseadas nos dados]
Risco: [o que faz esse cenario falhar]"""


def _build_user_prompt(pos: dict) -> str:
    d15 = pos.get("15m")
    d5  = pos.get("5m")

    lines = [
        f"Symbol:          {pos['symbol']}",
        f"Direction:       {pos['direction']}",
        f"Entry price:     {pos['entry_price']}",
        f"Mark price:      {pos['mark_price']}",
        f"Price move:      {pos['raw_pct_move']:+.2f}% unleveraged (negative = against position)",
        f"Unrealized PnL:  ${pos['unrealized_pnl']} ({pos['pnl_pct_margin']:+.2f}% on margin)",
        f"Leverage:        {pos['leverage']}x",
        f"Margin used:     ${pos['margin_used']} ({pos['margin_type']})",
        f"Liquidation:     {pos['liq_price']}",
        "",
    ]

    if d15:
        bb = d15["bb"]
        lines += [
            "15m Bollinger Bands:",
            f"  Upper:         {bb['upper']}",
            f"  Middle:        {bb['middle']}",
            f"  Lower:         {bb['lower']}   <- structural SL reference",
            f"  Spread:        {bb['spread_pct']}%",
            f"  Rising:        {bb['rising']}",
            f"  Dist to lower: {d15['dist_from_lower_pct']:+.2f}%  (negative = price below lower band)",
            f"15m MACD:        hist={d15['macd']['hist']} | positive={d15['macd']['positive']} | ascending={d15['macd']['ascending']}",
            f"15m StochRSI K:  {d15['stoch']['k']} | oversold={d15['stoch']['oversold']}",
            "",
        ]
    else:
        lines += ["15m data: unavailable", ""]

    if d5:
        bb = d5["bb"]
        lines += [
            "5m Bollinger Bands:",
            f"  Upper:         {bb['upper']}",
            f"  Middle:        {bb['middle']}",
            f"  Lower:         {bb['lower']}   <- immediate SL reference",
            f"  Spread:        {bb['spread_pct']}%",
            f"  Rising:        {bb['rising']}",
            f"  Dist to lower: {d5['dist_from_lower_pct']:+.2f}%  (negative = price below lower band)",
            f"5m MACD:         hist={d5['macd']['hist']} | positive={d5['macd']['positive']} | ascending={d5['macd']['ascending']}",
            f"5m StochRSI K:   {d5['stoch']['k']} | oversold={d5['stoch']['oversold']}",
        ]
    else:
        lines += ["5m data: unavailable"]

    return "\n".join(lines)


# -----------------------------------------------------------------------
# PERSISTENCIA
# -----------------------------------------------------------------------

def _persist(pos: dict, response: str):
    """
    Persiste o rescue em scan_results e notifications_sent.
    scan_results: dados da posicao no momento do pedido (para auditoria).
    notifications_sent: para cruzamento no analyzer (categoria rescue).
    Falha silenciosa em ambos.
    """
    try:
        insert("scan_results", {
            "protocol":     "rescue",
            "symbol":       pos["symbol"],
            "score":        None,
            "details_json": {
                "direction":      pos["direction"],
                "entry_price":    pos["entry_price"],
                "mark_price":     pos["mark_price"],
                "unrealized_pnl": pos["unrealized_pnl"],
                "pnl_pct_margin": pos["pnl_pct_margin"],
                "raw_pct_move":   pos["raw_pct_move"],
                "leverage":       pos["leverage"],
                "margin_used":    pos["margin_used"],
                "liq_price":      pos["liq_price"],
                "bb_15m":         pos["15m"]["bb"] if pos.get("15m") else None,
                "bb_5m":          pos["5m"]["bb"]  if pos.get("5m")  else None,
            },
            "notified": True,
        })
    except Exception as e:
        print(f"[RESCUE] Erro ao persistir scan_results: {e}")

    try:
        insert("notifications_sent", {
            "protocol":     "rescue",
            "symbol":       pos["symbol"],
            "score":        None,
            "message_text": response,
            "triggered_by": "rescue",
        })
    except Exception as e:
        print(f"[RESCUE] Erro ao persistir notifications_sent: {e}")


# -----------------------------------------------------------------------
# CHAMADA API
# -----------------------------------------------------------------------

def _call_claude(user_prompt: str) -> str | None:
    if not ANTHROPIC_API_KEY:
        print("[RESCUE] ANTHROPIC_API_KEY nao configurado.")
        return None

    headers = {
        "x-api-key":         ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type":      "application/json",
    }
    body = {
        "model":      MODEL,
        "max_tokens": MAX_TOKENS,
        "system":     SYSTEM_PROMPT,
        "messages":   [{"role": "user", "content": user_prompt}],
    }

    try:
        resp = requests.post(ANTHROPIC_URL, headers=headers, json=body, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"].strip()
    except Exception as e:
        print(f"[RESCUE] Erro na chamada Claude API: {e}")
        return None


# -----------------------------------------------------------------------
# INTERFACE PRINCIPAL
# -----------------------------------------------------------------------

def run_rescue(symbol: str):
    """
    Busca posicao aberta para o symbol, chama Claude API e envia 2 cenarios via Telegram.
    Persiste em scan_results e notifications_sent para rastreamento no analyzer.
    Chamada bloqueante — rodar em thread separada.
    """
    send_message(f"Analisando {symbol.upper()}...")

    pos = get_open_position(symbol)

    if pos is None:
        send_message(f"Nenhuma posicao aberta encontrada para {symbol.upper()}.")
        return

    user_prompt = _build_user_prompt(pos)
    response    = _call_claude(user_prompt)

    if response is None:
        send_message(f"[RESCUE] Falha ao obter analise para {symbol.upper()}. Verifique ANTHROPIC_API_KEY.")
        return

    _persist(pos, response)

    header = (
        f"[E AGORA?] {pos['symbol']}\n"
        f"Entrada: {pos['entry_price']}  |  Mark: {pos['mark_price']}\n"
        f"PnL: ${pos['unrealized_pnl']} ({pos['pnl_pct_margin']:+.2f}% na margem)\n"
        f"Move: {pos['raw_pct_move']:+.2f}% sem alavancagem\n"
        f"---"
    )

    send_message(f"{header}\n\n{response}")

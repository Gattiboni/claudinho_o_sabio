# notifier.py
# Camada de notificacao via Telegram
# Gattiboni Enterprises - claudinho_o_sabio
#
# Responsabilidades:
#   - Enviar mensagens de texto para o chat configurado
#   - Formatar output dos scanners (top5, cascade, spark, confirm)
#
# Se TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID estiverem vazios,
# loga no terminal e segue sem crashar.

import os
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_BASE_URL  = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


# -----------------------------------------------------------------------
# ENVIO
# -----------------------------------------------------------------------

def send_message(text: str) -> bool:
    """
    Envia mensagem de texto puro para o chat configurado.
    Retorna True se enviou com sucesso, False caso contrario.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[NOTIFIER] Telegram nao configurado. Mensagem suprimida:\n{text}")
        return False

    url     = f"{TELEGRAM_BASE_URL}/sendMessage"
    payload = {
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       text,
        "parse_mode": "",
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[NOTIFIER] Falha ao enviar mensagem: {e}")
        return False


# -----------------------------------------------------------------------
# FORMATADORES
# -----------------------------------------------------------------------

def format_top5(results: list) -> str:
    """
    Formata o output de scan_top5() para envio no Telegram.
    Recebe a lista retornada por scan_top5().
    """
    if not results:
        return ""

    ts    = datetime.now().strftime("%H:%M:%S")
    lines = [f"[TOP5 HUNTER] {ts}"]

    for i, r in enumerate(results, 1):
        double     = r["detail_15m"].get("double_confirm")
        double_tag = "  [DUPLA CONFIRMACAO TSI+STOCH]" if double else ""
        lines.append(f"")
        lines.append(f"#{i} {r['symbol']}  |  {r['change_pct']:+.2f}% 24h  |  Score: {r['score']}/12{double_tag}")
        lines.append(f"Entrada:  {r['entry_price']}")
        lines.append(f"Vol 24h:  ${r['volume_24h']:,.0f}")
        lines.append(
            f"15m [{r['score_15m']}/5]: BB={r['detail_15m'].get('bb_rising')}  "
            f"TSI={r['detail_15m'].get('tsi_positive')}  "
            f"Stoch={r['detail_15m'].get('stoch_k')}  "
            f"MACD={r['detail_15m'].get('macd_ok')}  "
            f"Dupla={double}"
        )
        lines.append(
            f"5m  [{r['score_5m']}/4]: Vol={r['detail_5m'].get('volume_ok')}  "
            f"MACD={r['detail_5m'].get('macd_rising')}  "
            f"Stoch={r['detail_5m'].get('stoch_k')}  "
            f"DistBB={r['detail_5m'].get('dist_upper_pct')}%"
        )
        lines.append(
            f"1m  [{r['score_1m']}/3]: VolExp={r['detail_1m'].get('vol_explosion')}"
            f"({r['detail_1m'].get('vol_ratio')}x)  "
            f"Corpo={r['detail_1m'].get('body_ratio')}  "
            f"Stoch={r['detail_1m'].get('stoch_k')}"
        )

    lines.append("")
    lines.append("Score e sinal, nao certeza. Protocolo define a entrada.")
    return "\n".join(lines)


def format_cascade(setups: list) -> str:
    """
    Formata o output de scan_market() para envio no Telegram.
    Recebe a lista retornada por scan_market().
    """
    if not setups:
        return ""

    ts    = datetime.now().strftime("%H:%M:%S")
    lines = [f"[CASCADE] {ts}"]

    for s in setups:
        d5 = s["5m"]
        sl_warn = "  [ATENCAO: SL acima de 8%]" if d5["sl_pct_from_entry"] > 8 else ""
        lines.append("")
        lines.append(f"SETUP: {s['symbol']}  |  {s['change_24h_pct']:+.2f}% 24h")
        lines.append(f"Entrada:   {d5['entry_price']}")
        lines.append(f"SL:        {d5['sl_level']}  (-{d5['sl_pct_from_entry']}%){sl_warn}")
        lines.append(f"Trailing:  {d5['trailing_callback_pct']}%  |  BB spread: {d5['bb_spread_pct']}%")
        lines.append(f"Vol 24h:   ${s['volume_24h_usd']:,.0f}")
        lines.append(
            f"1h:  MA7>MA99={s['1h']['ma7_above_ma99']}  "
            f"MACD_hist={s['1h']['macd_hist']}"
        )
        lines.append(
            f"15m: Stoch={s['15m']['stoch_k_value']}  "
            f"TSI={s['15m']['tsi_positive']}  "
            f"BB={s['15m']['bb_bands_rising']}  "
            f"BTC={s['15m']['btc_case']}"
        )
        macd_str = f"pos={s['5m']['macd_positive']} asc={s['5m']['macd_ascending']}"
        if not s["5m"]["macd_positive"] and s["5m"].get("macd_recovery") is not None:
            macd_str += f" rec={s['5m']['macd_recovery']}%"
        lines.append(
            f"5m:  MACD={macd_str}  "
            f"BB={s['5m']['bb_bands_rising']}  "
            f"BTC={s['5m']['btc_case']}"
        )

    return "\n".join(lines)


def format_spark(sparks: list) -> str:
    """
    Formata o output de scan_spark() para envio no Telegram.
    Recebe a lista retornada por scan_spark().
    """
    if not sparks:
        return ""

    ts    = datetime.now().strftime("%H:%M:%S")
    lines = [f"[SPARK] {ts}"]

    for s in sparks:
        tr = s["trigger"]
        sl_warn = "  [ATENCAO: acima de 8%]" if tr["sl_pct_from_entry"] > 8 else ""
        lines.append("")
        lines.append(f"SPARK: {s['symbol']}  |  {s['change_24h_pct']:+.2f}% 24h")
        lines.append(f"Entrada:   {tr['entry_price']}")
        lines.append(f"SL:        {tr['sl_level']}  (-{tr['sl_pct_from_entry']}%){sl_warn}")
        lines.append(f"Trailing:  {tr['trailing_callback_pct']}%  |  BB spread: {tr['bb_spread_pct']}%")
        lines.append(f"Vol 24h:   ${s['volume_24h_usd']:,.0f}")
        lines.append(
            f"Compressao: 1h={s['compression']['bbw_percentile_1h']}pct  "
            f"15m={s['compression']['bbw_percentile_15m']}pct"
        )
        lines.append(
            f"Pre-sinal:  corpo={s['presignal']['bodies_ok']}  "
            f"dir={s['presignal']['closes_up']}  "
            f"vol={s['presignal']['vol_creep']}  "
            f"distBB={s['presignal']['dist_to_upper_pct']}%"
        )
        lines.append(
            f"Gatilho:    vol={tr['vol_ratio']}x  "
            f"corpo={tr['body_ratio']}  "
            f"breakout={tr['breakout_upper_bb']}"
        )

    return "\n".join(lines)


def format_confirm(symbol: str, result: dict) -> str:
    """
    Formata o resultado do confirmador para envio no Telegram.
    Recebe o simbolo e o dict retornado por analyze_to_dict().
    """
    ts    = datetime.now().strftime("%H:%M:%S")
    lines = [f"[CONFIRM] {symbol}  |  {ts}"]

    if result.get("vetoed"):
        lines.append(f"VETADO no 1h: {result['veto_reason']}")
        lines.append("Estrutura macro nao permite entrada.")
        return "\n".join(lines)

    total  = result["total"]
    double = result["detail_15m"].get("double_confirm")
    double_tag = "  [DUPLA CONFIRMACAO TSI+STOCH]" if double else ""

    lines.append(f"Score: {total}/12{double_tag}")
    lines.append(f"Entrada:      {result['entry_price']}")
    lines.append(f"SL (BB 5m):   {result['sl_level']:.4f}  (-{result['sl_pct']}%)")
    lines.append(f"Trailing CB:  {result['callback']}%")
    lines.append(f"BB spread 5m: {result['bb_spread']}%")

    if result.get("sl_warning"):
        lines.append("ATENCAO: SL acima de 8% — revise o tamanho da posicao")

    d15 = result["detail_15m"]
    d5  = result["detail_5m"]
    d1  = result["detail_1m"]

    lines.append(
        f"15m [{result['score_15m']}/5]: BB={d15.get('bb_rising')}  "
        f"TSI={d15.get('tsi_positive')}  "
        f"Stoch={d15.get('stoch_k')}  "
        f"MACD={d15.get('macd_ok')}  "
        f"Dupla={double}"
    )
    lines.append(
        f"5m  [{result['score_5m']}/4]: Vol={d5.get('volume_ok')}  "
        f"MACD={d5.get('macd_rising')}  "
        f"Stoch={d5.get('stoch_k')}  "
        f"DistBB={d5.get('dist_upper_pct')}%"
    )
    lines.append(
        f"1m  [{result['score_1m']}/3]: VolExp={d1.get('vol_explosion')}"
        f"({d1.get('vol_ratio')}x)  "
        f"Corpo={d1.get('body_ratio')}  "
        f"Stoch={d1.get('stoch_k')}"
    )

    status = "CONFIRMADO — score >= 7." if total >= 7 else f"NAO CONFIRMADO — score {total} abaixo do minimo 7."
    lines.append(status)

    return "\n".join(lines)

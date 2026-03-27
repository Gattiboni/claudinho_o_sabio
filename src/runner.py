# runner_rescue_patch.py
# Patch para runner.py — Protocolo E Agora
# Gattiboni Enterprises - claudinho_o_sabio
#
# Instrucoes de merge:
#   1. Adicionar import no bloco de imports do runner
#   2. Adicionar handle_rescue() apos handle_confirm()
#   3. Adicionar branch em process_message() antes do ultimo return


# -----------------------------------------------------------------------
# 1. IMPORT — adicionar junto aos demais imports do runner
# -----------------------------------------------------------------------

# from rescue_protocol import run_rescue


# -----------------------------------------------------------------------
# 2. HANDLER — adicionar apos handle_confirm()
# -----------------------------------------------------------------------

# def handle_rescue(symbol: str):
#     """
#     Busca posicao aberta para o symbol e envia 2 cenarios de gestao de risco.
#     """
#     threading.Thread(target=run_rescue, args=(symbol,), daemon=True).start()


# -----------------------------------------------------------------------
# 3. BRANCH em process_message() — adicionar apos o bloco "confirm SYMBOL"
# -----------------------------------------------------------------------

# Texto completo do novo branch:
#
#     if text_lower.startswith("claudinho e agora? "):
#         parts = text_stripped.split(maxsplit=3)
#         if len(parts) == 4:
#             symbol = parts[3].strip()
#             handle_rescue(symbol)
#         else:
#             send_message("Uso: Claudinho e agora? SYMBOL  (ex: Claudinho e agora? SOLUSDT)")
#         return


# -----------------------------------------------------------------------
# ARQUIVO COMPLETO — runner.py com patch aplicado para referencia
# -----------------------------------------------------------------------

RUNNER_WITH_PATCH = '''
# runner.py
# Orquestrador principal do claudinho_o_sabio
# Gattiboni Enterprises - claudinho_o_sabio
#
# Responsabilidades:
#   - Rodar os quatro scanners (top5, cascade, spark, roar) em loops independentes
#   - Respeitar horario de operacao automatica (seg-sex 06-23:59, dom 20-23:59)
#   - Enviar notificacoes via Telegram quando encontrar sinais
#   - Persistir scans e notificacoes no Supabase via notifier
#   - Controlar cooldown por ativo (15 min entre notificacoes do mesmo ativo)
#   - Responder comandos via Telegram:
#       "Claudinho roda os protocolos" — disparo unico imediato
#       "Claudinho mute"               — silencia notificacoes
#       "Claudinho unmute"             — retoma notificacoes
#       "Claudinho analisa"            — abre menu de analise de trades
#       "confirm SYMBOL"               — analise pontual de ativo
#       "Claudinho e agora? SYMBOL"    — gestao de posicao em baixa (2 cenarios)
#
# Uso: py -3.11 src/runner.py

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import time
import threading
from datetime import datetime, timedelta

import pytz
from dotenv import load_dotenv
import requests

from top5_hunter           import scan_top5
from cascade_market_reader import scan_market
from spark_market_reader   import scan_spark
from roar_hunter           import scan_roar
from confirm               import analyze_to_dict
from rescue_protocol       import run_rescue
from notifier              import (
    send_message,
    format_top5,
    format_cascade,
    format_spark,
    format_roar,
    format_confirm,
)

load_dotenv()

# -----------------------------------------------------------------------
# CONFIGURACAO
# -----------------------------------------------------------------------

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_BASE_URL  = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

INTERVAL_TOP5    = int(os.getenv("SCAN_INTERVAL_TOP5",    30)) * 60
INTERVAL_CASCADE = int(os.getenv("SCAN_INTERVAL_CASCADE", 30)) * 60
INTERVAL_SPARK   = int(os.getenv("SCAN_INTERVAL_SPARK",   15)) * 60
INTERVAL_ROAR    = int(os.getenv("SCAN_INTERVAL_ROAR",    30)) * 60

COOLDOWN_MINUTES = 15
TIMEZONE         = pytz.timezone("America/Sao_Paulo")

NOTIFICATION_TRADE_WINDOW = 5

# -----------------------------------------------------------------------
# ESTADO COMPARTILHADO
# -----------------------------------------------------------------------

state_lock     = threading.Lock()
muted          = False
cooldown_map   = {}
last_update_id = 0

awaiting_analysis = False


# -----------------------------------------------------------------------
# HORARIO DE OPERACAO
# -----------------------------------------------------------------------

def within_schedule() -> bool:
    now     = datetime.now(TIMEZONE)
    weekday = now.weekday()
    hour    = now.hour
    if weekday in (0, 1, 2, 3, 4):
        return hour >= 6
    if weekday == 6:
        return hour >= 20
    return False


# -----------------------------------------------------------------------
# COOLDOWN
# -----------------------------------------------------------------------

def is_on_cooldown(symbol: str) -> bool:
    with state_lock:
        last = cooldown_map.get(symbol)
        if last is None:
            return False
        return datetime.now() - last < timedelta(minutes=COOLDOWN_MINUTES)


def mark_sent(symbol: str):
    with state_lock:
        cooldown_map[symbol] = datetime.now()


# -----------------------------------------------------------------------
# ENVIO COM COOLDOWN
# -----------------------------------------------------------------------

def notify_if_eligible(symbol: str, text: str):
    global muted
    with state_lock:
        is_muted = muted
    if is_muted:
        return
    if is_on_cooldown(symbol):
        return
    if send_message(text):
        mark_sent(symbol)


# -----------------------------------------------------------------------
# RUNNERS DE SCAN
# -----------------------------------------------------------------------

def run_top5():
    print(f"[RUNNER] Thread Top5 iniciada (intervalo: {INTERVAL_TOP5 // 60} min)")
    while True:
        if within_schedule():
            try:
                results = scan_top5()
                if results:
                    text = format_top5(results, triggered_by="loop")
                    if text:
                        for r in results:
                            notify_if_eligible(r["symbol"], text)
                            break
            except Exception as e:
                print(f"[RUNNER] Erro no scan Top5: {e}")
        time.sleep(INTERVAL_TOP5)


def run_cascade():
    print(f"[RUNNER] Thread Cascade iniciada (intervalo: {INTERVAL_CASCADE // 60} min)")
    while True:
        if within_schedule():
            try:
                setups = scan_market()
                if setups:
                    for setup in setups:
                        symbol = setup["symbol"]
                        text   = format_cascade([setup], triggered_by="loop")
                        notify_if_eligible(symbol, text)
            except Exception as e:
                print(f"[RUNNER] Erro no scan Cascade: {e}")
        time.sleep(INTERVAL_CASCADE)


def run_spark():
    print(f"[RUNNER] Thread Spark iniciada (intervalo: {INTERVAL_SPARK // 60} min)")
    while True:
        if within_schedule():
            try:
                sparks = scan_spark()
                if sparks:
                    for spark in sparks:
                        symbol = spark["symbol"]
                        text   = format_spark([spark], triggered_by="loop")
                        notify_if_eligible(symbol, text)
            except Exception as e:
                print(f"[RUNNER] Erro no scan Spark: {e}")
        time.sleep(INTERVAL_SPARK)


def run_roar():
    print(f"[RUNNER] Thread Roar iniciada (intervalo: {INTERVAL_ROAR // 60} min)")
    while True:
        if within_schedule():
            try:
                results = scan_roar()
                if results:
                    text = format_roar(results, triggered_by="loop")
                    if text:
                        for r in results:
                            notify_if_eligible(r["symbol"], text)
                            break
            except Exception as e:
                print(f"[RUNNER] Erro no scan Roar: {e}")
        time.sleep(INTERVAL_ROAR)


# -----------------------------------------------------------------------
# DISPARO UNICO
# -----------------------------------------------------------------------

def run_once():
    global muted
    with state_lock:
        is_muted = muted
    if is_muted:
        send_message("Claudinho esta em mute. Use \'Claudinho unmute\' para reativar.")
        return

    send_message("Rodando os protocolos agora...")

    try:
        results = scan_top5()
        if results:
            text = format_top5(results, triggered_by="manual")
            if text:
                send_message(text)
                for r in results:
                    mark_sent(r["symbol"])
        else:
            send_message("[TOP5] Nenhum ativo com score suficiente agora.")
    except Exception as e:
        send_message(f"[TOP5] Erro no scan: {e}")

    try:
        setups = scan_market()
        if setups:
            for setup in setups:
                text = format_cascade([setup], triggered_by="manual")
                send_message(text)
                mark_sent(setup["symbol"])
        else:
            send_message("[CASCADE] Nenhum setup identificado agora.")
    except Exception as e:
        send_message(f"[CASCADE] Erro no scan: {e}")

    try:
        sparks = scan_spark()
        if sparks:
            for spark in sparks:
                text = format_spark([spark], triggered_by="manual")
                send_message(text)
                mark_sent(spark["symbol"])
        else:
            send_message("[SPARK] Nenhum Spark detectado agora.")
    except Exception as e:
        send_message(f"[SPARK] Erro no scan: {e}")

    try:
        roars = scan_roar()
        if roars:
            text = format_roar(roars, triggered_by="manual")
            if text:
                send_message(text)
                for r in roars:
                    mark_sent(r["symbol"])
        else:
            send_message("[ROAR] Nenhum dormentes qualificado agora.")
    except Exception as e:
        send_message(f"[ROAR] Erro no scan: {e}")


# -----------------------------------------------------------------------
# HANDLER DE CONFIRM
# -----------------------------------------------------------------------

def handle_confirm(symbol: str):
    result = analyze_to_dict(symbol)
    if result is None:
        send_message(f"Simbolo {symbol.upper()} nao encontrado na Binance Futures.")
        return
    text = format_confirm(symbol.upper(), result, triggered_by="manual")
    send_message(text)


# -----------------------------------------------------------------------
# HANDLER DE RESCUE
# -----------------------------------------------------------------------

def handle_rescue(symbol: str):
    """
    Busca posicao aberta para o symbol e envia 2 cenarios de gestao de risco.
    """
    threading.Thread(target=run_rescue, args=(symbol,), daemon=True).start()


# -----------------------------------------------------------------------
# HANDLER DE ANALISE
# -----------------------------------------------------------------------

def handle_analysis(period_text: str):
    from trade_fetcher import fetch_and_store
    from analyzer      import run_analysis

    period_map = {
        "1": (1,  "24h"),
        "2": (3,  "3d"),
        "3": (7,  "7d"),
        "4": (30, "30d"),
    }

    if period_text not in period_map:
        send_message("Opcao invalida. Envie 1, 2, 3 ou 4.")
        return

    days, label = period_map[period_text]
    send_message(f"Buscando trades dos ultimos {label}...")

    count = fetch_and_store(days=days, period_label=label)
    if count == 0:
        send_message(f"Nenhum trade encontrado nos ultimos {label}.")
        return

    report = run_analysis(days=days)
    send_message(report)


# -----------------------------------------------------------------------
# POLLING DO TELEGRAM
# -----------------------------------------------------------------------

def get_updates(offset: int) -> list:
    try:
        resp = requests.get(
            f"{TELEGRAM_BASE_URL}/getUpdates",
            params={"offset": offset, "timeout": 30},
            timeout=40,
        )
        resp.raise_for_status()
        return resp.json().get("result", [])
    except Exception as e:
        print(f"[RUNNER] Erro no polling Telegram: {e}")
        return []


def process_message(text: str):
    global muted, awaiting_analysis
    text_stripped = text.strip()
    text_lower    = text_stripped.lower()

    with state_lock:
        waiting = awaiting_analysis

    if waiting:
        if text_stripped in ("1", "2", "3", "4"):
            with state_lock:
                awaiting_analysis = False
            threading.Thread(
                target=handle_analysis, args=(text_stripped,), daemon=True
            ).start()
            return
        else:
            with state_lock:
                awaiting_analysis = False

    if text_lower == "claudinho roda os protocolos":
        threading.Thread(target=run_once, daemon=True).start()
        return

    if text_lower == "claudinho mute":
        with state_lock:
            muted = True
        send_message("Mute ativado. Notificacoes suspensas ate \'Claudinho unmute\'.")
        return

    if text_lower == "claudinho unmute":
        with state_lock:
            muted = False
        send_message("Unmute. Notificacoes reativadas.")
        return

    if text_lower == "claudinho analisa":
        with state_lock:
            awaiting_analysis = True
        send_message(
            "Selecione o periodo de analise:\\n"
            "1 - Ultimas 24h\\n"
            "2 - Ultimos 3 dias\\n"
            "3 - Ultimos 7 dias\\n"
            "4 - Ultimos 30 dias"
        )
        return

    if text_lower.startswith("confirm "):
        parts = text_stripped.split(maxsplit=1)
        if len(parts) == 2:
            symbol = parts[1].strip()
            threading.Thread(target=handle_confirm, args=(symbol,), daemon=True).start()
        else:
            send_message("Uso: confirm SYMBOL  (ex: confirm SOLUSDT)")
        return

    if text_lower.startswith("claudinho e agora? "):
        parts = text_stripped.split(maxsplit=3)
        if len(parts) == 4:
            symbol = parts[3].strip()
            handle_rescue(symbol)
        else:
            send_message("Uso: Claudinho e agora? SYMBOL  (ex: Claudinho e agora? SOLUSDT)")
        return


def run_polling():
    global last_update_id
    print("[RUNNER] Thread polling Telegram iniciada")

    updates = get_updates(offset=-1)
    if updates:
        last_update_id = updates[-1]["update_id"] + 1

    while True:
        updates = get_updates(offset=last_update_id)
        for update in updates:
            last_update_id = update["update_id"] + 1
            try:
                msg  = update.get("message", {})
                text = msg.get("text", "")
                if text:
                    print(f"[RUNNER] Comando recebido: {text}")
                    process_message(text)
            except Exception as e:
                print(f"[RUNNER] Erro ao processar update: {e}")


# -----------------------------------------------------------------------
# ENTRYPOINT
# -----------------------------------------------------------------------

if __name__ == "__main__":
    print(f"[RUNNER] Iniciando claudinho_o_sabio — {datetime.now(TIMEZONE).strftime(\'%d/%m/%Y %H:%M:%S\')} (Brasilia)")
    print(f"[RUNNER] Horario automatico: seg-sex 06-23:59 | dom 20-23:59 | sab: somente sob demanda")
    print(f"[RUNNER] Cooldown por ativo: {COOLDOWN_MINUTES} min")
    print(
        f"[RUNNER] Intervalos: Top5={INTERVAL_TOP5 // 60}min | "
        f"Cascade={INTERVAL_CASCADE // 60}min | "
        f"Spark={INTERVAL_SPARK // 60}min | "
        f"Roar={INTERVAL_ROAR // 60}min"
    )

    if not TELEGRAM_BOT_TOKEN:
        print("[RUNNER] ATENCAO: TELEGRAM_BOT_TOKEN nao configurado. Polling e notificacoes desativados.")

    threads = [
        threading.Thread(target=run_top5,    daemon=True, name="top5"),
        threading.Thread(target=run_cascade,  daemon=True, name="cascade"),
        threading.Thread(target=run_spark,    daemon=True, name="spark"),
        threading.Thread(target=run_roar,     daemon=True, name="roar"),
    ]

    if TELEGRAM_BOT_TOKEN:
        threads.append(threading.Thread(target=run_polling, daemon=True, name="polling"))

    for t in threads:
        t.start()

    send_message(
        f"claudinho_o_sabio online — {datetime.now(TIMEZONE).strftime(\'%d/%m/%Y %H:%M:%S\')}\\n"
        f"Intervalos: Top5={INTERVAL_TOP5 // 60}min | Cascade={INTERVAL_CASCADE // 60}min | "
        f"Spark={INTERVAL_SPARK // 60}min | Roar={INTERVAL_ROAR // 60}min\\n"
        f"Horario automatico: seg-sex 06-23:59 | dom 20-23:59"
    )

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\\n[RUNNER] Encerrando.")
'''
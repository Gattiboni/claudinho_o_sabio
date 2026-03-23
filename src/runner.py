# runner.py
# Orquestrador principal do claudinho_o_sabio
# Gattiboni Enterprises - claudinho_o_sabio
#
# Responsabilidades:
#   - Rodar os tres scanners (top5, cascade, spark) em loops independentes
#   - Respeitar horario de operacao automatica (seg-sex 06-23:59, dom 20-23:59)
#   - Enviar notificacoes via Telegram quando encontrar sinais
#   - Controlar cooldown por ativo (15 min entre notificacoes do mesmo ativo)
#   - Responder comandos via Telegram:
#       "Claudinho roda os protocolos" — disparo unico imediato
#       "Claudinho mute"               — silencia notificacoes
#       "Claudinho unmute"             — retoma notificacoes
#       "confirm SYMBOL"               — analise pontual de ativo
#
# Uso: py -3.11 src/runner.py

import os
import time
import threading
from datetime import datetime, timedelta

import pytz
from dotenv import load_dotenv
import requests

from top5_hunter           import scan_top5 # pyright: ignore[reportMissingImports]
from cascade_market_reader import scan_market
from spark_market_reader   import scan_spark
from confirm               import analyze_to_dict
from notifier              import (
    send_message,
    format_top5,
    format_cascade,
    format_spark,
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

COOLDOWN_MINUTES = 15
TIMEZONE         = pytz.timezone("America/Sao_Paulo")

# -----------------------------------------------------------------------
# ESTADO COMPARTILHADO
# -----------------------------------------------------------------------

state_lock   = threading.Lock()
muted        = False
cooldown_map = {}          # {symbol: datetime} — ultimo envio por ativo
last_update_id = 0         # controle de polling do Telegram


# -----------------------------------------------------------------------
# HORARIO DE OPERACAO
# -----------------------------------------------------------------------

def within_schedule() -> bool:
    """
    Retorna True se o momento atual esta dentro do horario de operacao automatica:
      Seg-Sex: 06:00 - 23:59
      Dom:     20:00 - 23:59
      Sab:     nunca automatico
    """
    now     = datetime.now(TIMEZONE)
    weekday = now.weekday()   # 0=seg, 1=ter, ..., 5=sab, 6=dom
    hour    = now.hour

    if weekday in (0, 1, 2, 3, 4):   # seg a sex
        return hour >= 6
    if weekday == 6:                  # domingo
        return hour >= 20
    return False                      # sabado


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
    """
    Envia notificacao apenas se:
      - nao estiver muted
      - o ativo nao estiver em cooldown
    """
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
                    text = format_top5(results)
                    if text:
                        for r in results:
                            notify_if_eligible(r["symbol"], text)
                            break   # envia a mensagem uma vez (agrupa todos)
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
                        text   = format_cascade([setup])
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
                        text   = format_spark([spark])
                        notify_if_eligible(symbol, text)
            except Exception as e:
                print(f"[RUNNER] Erro no scan Spark: {e}")
        time.sleep(INTERVAL_SPARK)


# -----------------------------------------------------------------------
# DISPARO UNICO (comando manual)
# -----------------------------------------------------------------------

def run_once():
    """
    Roda os tres scanners uma vez, sem verificar horario.
    Notifica independente de cooldown (comando explicito do operador).
    """
    global muted
    with state_lock:
        is_muted = muted
    if is_muted:
        send_message("Claudinho esta em mute. Use 'Claudinho unmute' para reativar.")
        return

    send_message("Rodando os protocolos agora...")

    try:
        results = scan_top5()
        if results:
            text = format_top5(results)
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
                text = format_cascade([setup])
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
                text = format_spark([spark])
                send_message(text)
                mark_sent(spark["symbol"])
        else:
            send_message("[SPARK] Nenhum Spark detectado agora.")
    except Exception as e:
        send_message(f"[SPARK] Erro no scan: {e}")


# -----------------------------------------------------------------------
# HANDLER DE CONFIRM
# -----------------------------------------------------------------------

def handle_confirm(symbol: str):
    result = analyze_to_dict(symbol)
    if result is None:
        send_message(f"Simbolo {symbol.upper()} nao encontrado na Binance Futures.")
        return
    text = format_confirm(symbol.upper(), result)
    send_message(text)


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
    """
    Interpreta comandos recebidos via Telegram.
    """
    global muted
    text = text.strip()

    if text.lower() == "claudinho roda os protocolos":
        threading.Thread(target=run_once, daemon=True).start()
        return

    if text.lower() == "claudinho mute":
        with state_lock:
            muted = True
        send_message("Mute ativado. Notificacoes suspensas ate 'Claudinho unmute'.")
        return

    if text.lower() == "claudinho unmute":
        with state_lock:
            muted = False
        send_message("Unmute. Notificacoes reativadas.")
        return

    if text.lower().startswith("confirm "):
        parts = text.split(maxsplit=1)
        if len(parts) == 2:
            symbol = parts[1].strip()
            threading.Thread(target=handle_confirm, args=(symbol,), daemon=True).start()
        else:
            send_message("Uso: confirm SYMBOL  (ex: confirm SOLUSDT)")
        return


def run_polling():
    """
    Thread de polling do Telegram. Fica em long polling continuo.
    Processa apenas mensagens recebidas apos o inicio do runner.
    """
    global last_update_id

    print("[RUNNER] Thread polling Telegram iniciada")

    # Descarta mensagens antigas: busca updates sem offset para pegar o ultimo id
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
    print(f"[RUNNER] Iniciando claudinho_o_sabio — {datetime.now(TIMEZONE).strftime('%d/%m/%Y %H:%M:%S')} (Brasilia)")
    print(f"[RUNNER] Horario automatico: seg-sex 06-23:59 | dom 20-23:59 | sab: somente sob demanda")
    print(f"[RUNNER] Cooldown por ativo: {COOLDOWN_MINUTES} min")
    print(f"[RUNNER] Intervalos: Top5={INTERVAL_TOP5 // 60}min | Cascade={INTERVAL_CASCADE // 60}min | Spark={INTERVAL_SPARK // 60}min")

    if not TELEGRAM_BOT_TOKEN:
        print("[RUNNER] ATENCAO: TELEGRAM_BOT_TOKEN nao configurado. Polling e notificacoes desativados.")

    threads = [
        threading.Thread(target=run_top5,    daemon=True, name="top5"),
        threading.Thread(target=run_cascade,  daemon=True, name="cascade"),
        threading.Thread(target=run_spark,    daemon=True, name="spark"),
    ]

    if TELEGRAM_BOT_TOKEN:
        threads.append(threading.Thread(target=run_polling, daemon=True, name="polling"))

    for t in threads:
        t.start()

    send_message(
        f"claudinho_o_sabio online — {datetime.now(TIMEZONE).strftime('%d/%m/%Y %H:%M:%S')}\n"
        f"Intervalos: Top5={INTERVAL_TOP5 // 60}min | Cascade={INTERVAL_CASCADE // 60}min | Spark={INTERVAL_SPARK // 60}min\n"
        f"Horario automatico: seg-sex 06-23:59 | dom 20-23:59"
    )

    # Mantém a thread principal viva
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n[RUNNER] Encerrando.")

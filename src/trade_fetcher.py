# trade_fetcher.py
# Busca income history (REALIZED_PNL) da Binance Futures e persiste no Supabase
# Gattiboni Enterprises - claudinho_o_sabio
#
# Uso standalone:
#   py -3.11 trade_fetcher.py
#   (busca ultimos 7 dias e salva no Supabase)
#
# Uso programatico:
#   from trade_fetcher import fetch_and_store
#   count = fetch_and_store(days=7, period_label="7d")

import os
from datetime import datetime, timedelta, timezone

from binance_auth    import signed_get
from supabase_client import upsert_many


# -----------------------------------------------------------------------
# CONFIGURACAO
# -----------------------------------------------------------------------

INCOME_ENDPOINT = "/fapi/v1/income"
INCOME_TYPE     = "REALIZED_PNL"
PAGE_LIMIT      = 1000   # maximo permitido pela Binance por chamada


# -----------------------------------------------------------------------
# COLETA
# -----------------------------------------------------------------------

def _fetch_income(start_ms: int, end_ms: int) -> list:
    """
    Busca todos os registros de REALIZED_PNL entre start_ms e end_ms.
    Pagina automaticamente se houver mais de 1000 registros.
    """
    all_records = []
    current_start = start_ms

    while True:
        params = {
            "incomeType": INCOME_TYPE,
            "startTime":  current_start,
            "endTime":    end_ms,
            "limit":      PAGE_LIMIT,
        }
        result = signed_get(INCOME_ENDPOINT, params)

        if not result:
            break

        all_records.extend(result)

        if len(result) < PAGE_LIMIT:
            break

        # Proxima pagina comeca apos o ultimo registro retornado
        current_start = result[-1]["time"] + 1

    return all_records


# -----------------------------------------------------------------------
# PERSISTENCIA
# -----------------------------------------------------------------------

def _to_supabase_rows(records: list, period_label: str) -> list:
    """
    Converte registros da Binance para o formato da tabela trades.
    """
    rows = []
    for r in records:
        try:
            ts_ms  = int(r["time"])
            ts_iso = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()
            rows.append({
                "tran_id":      int(r["tranId"]),
                "symbol":       r["symbol"],
                "realized_pnl": float(r["income"]),
                "commission":   0.0,   # income endpoint nao retorna comissao separada
                "time":         ts_iso,
                "period_label": period_label,
            })
        except Exception as e:
            print(f"[TRADE_FETCHER] Erro ao converter registro: {e} | {r}")
    return rows


# -----------------------------------------------------------------------
# INTERFACE PRINCIPAL
# -----------------------------------------------------------------------

def fetch_and_store(days: int, period_label: str) -> int:
    """
    Busca trades dos ultimos N dias e salva no Supabase.
    Usa upsert para evitar duplicatas (chave: tran_id).
    Retorna quantidade de registros processados.
    """
    now_ms   = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_ms = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)

    print(f"[TRADE_FETCHER] Buscando REALIZED_PNL dos ultimos {days} dias...")
    records = _fetch_income(start_ms, now_ms)

    if not records:
        print(f"[TRADE_FETCHER] Nenhum trade encontrado no periodo.")
        return 0

    print(f"[TRADE_FETCHER] {len(records)} registros encontrados. Salvando no Supabase...")
    rows = _to_supabase_rows(records, period_label)

    ok = upsert_many("trades", rows, on_conflict="tran_id")
    if ok:
        print(f"[TRADE_FETCHER] {len(rows)} registros salvos com sucesso.")
    else:
        print(f"[TRADE_FETCHER] Erro ao salvar no Supabase.")

    return len(rows) if ok else 0


# -----------------------------------------------------------------------
# ENTRYPOINT
# -----------------------------------------------------------------------

if __name__ == "__main__":
    count = fetch_and_store(days=7, period_label="7d")
    print(f"\nTotal processado: {count} registros.")

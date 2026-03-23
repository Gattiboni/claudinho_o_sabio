# supabase_client.py
# Cliente HTTP para o Supabase REST API
# Gattiboni Enterprises - claudinho_o_sabio
#
# Sem biblioteca supabase-py — usa requests direto, mesmo padrao do projeto.
# Suporta insert, select e upsert na API REST do Supabase.

import os
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL      = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")

_HEADERS = {
    "apikey":        SUPABASE_ANON_KEY,
    "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
    "Content-Type":  "application/json",
    "Prefer":        "return=minimal",
}


def _check_config():
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise RuntimeError("SUPABASE_URL ou SUPABASE_ANON_KEY nao configurados no .env")


def insert(table: str, data: dict) -> bool:
    """
    Insere um registro na tabela.
    Retorna True se inseriu com sucesso, False caso contrario.
    """
    try:
        _check_config()
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=_HEADERS,
            json=data,
            timeout=10,
        )
        return resp.status_code in (200, 201)
    except Exception as e:
        print(f"[SUPABASE] Erro ao inserir em {table}: {e}")
        return False


def insert_many(table: str, rows: list) -> bool:
    """
    Insere multiplos registros de uma vez.
    Retorna True se inseriu com sucesso, False caso contrario.
    """
    if not rows:
        return True
    try:
        _check_config()
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=_HEADERS,
            json=rows,
            timeout=10,
        )
        return resp.status_code in (200, 201)
    except Exception as e:
        print(f"[SUPABASE] Erro ao inserir multiplos em {table}: {e}")
        return False


def upsert(table: str, data: dict, on_conflict: str) -> bool:
    """
    Insere ou atualiza um registro baseado na coluna de conflito.
    Util para evitar duplicatas (ex: tran_id na tabela trades).
    """
    try:
        _check_config()
        headers = {**_HEADERS, "Prefer": f"resolution=merge-duplicates,return=minimal"}
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/{table}?on_conflict={on_conflict}",
            headers=headers,
            json=data,
            timeout=10,
        )
        return resp.status_code in (200, 201)
    except Exception as e:
        print(f"[SUPABASE] Erro ao upsert em {table}: {e}")
        return False


def upsert_many(table: str, rows: list, on_conflict: str) -> bool:
    """
    Upsert de multiplos registros de uma vez.
    """
    if not rows:
        return True
    try:
        _check_config()
        headers = {**_HEADERS, "Prefer": f"resolution=merge-duplicates,return=minimal"}
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/{table}?on_conflict={on_conflict}",
            headers=headers,
            json=rows,
            timeout=10,
        )
        return resp.status_code in (200, 201)
    except Exception as e:
        print(f"[SUPABASE] Erro ao upsert multiplos em {table}: {e}")
        return False


def select(table: str, filters: dict = None, limit: int = 1000) -> list:
    """
    Busca registros de uma tabela.
    filters: dict com pares coluna=valor para filtrar (ex: {"protocol": "top5"})
    Retorna lista de dicts ou lista vazia em caso de erro.
    """
    try:
        _check_config()
        params = {"limit": limit}
        if filters:
            for col, val in filters.items():
                params[col] = f"eq.{val}"
        headers = {**_HEADERS, "Prefer": ""}
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=headers,
            params=params,
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
        print(f"[SUPABASE] Erro ao buscar {table}: {resp.status_code} {resp.text}")
        return []
    except Exception as e:
        print(f"[SUPABASE] Erro ao buscar {table}: {e}")
        return []


def select_range(table: str, time_col: str, start_iso: str, end_iso: str,
                 extra_filters: dict = None, limit: int = 10000) -> list:
    """
    Busca registros de uma tabela dentro de um intervalo de tempo.
    Pagina automaticamente em blocos de 1000 ate atingir o limite ou esgotar os dados.
    start_iso e end_iso: strings ISO 8601 (ex: "2026-03-01T00:00:00+00:00")
    Retorna lista de dicts ou lista vazia em caso de erro.
    """
    try:
        _check_config()
        from urllib.parse import quote

        start_enc = quote(start_iso, safe=":-T.")
        end_enc   = quote(end_iso,   safe=":-T.")

        extra = ""
        if extra_filters:
            for col, val in extra_filters.items():
                extra += f"&{col}=eq.{quote(str(val), safe='')}"

        headers  = {**_HEADERS, "Prefer": "count=none"}
        all_rows = []
        page_size = 1000
        offset    = 0

        while len(all_rows) < limit:
            url = (
                f"{SUPABASE_URL}/rest/v1/{table}"
                f"?{time_col}=gte.{start_enc}"
                f"&{time_col}=lte.{end_enc}"
                f"&limit={page_size}"
                f"&offset={offset}"
                f"{extra}"
            )
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                print(f"[SUPABASE] Erro ao buscar range {table}: {resp.status_code} {resp.text}")
                break
            page = resp.json()
            if not page:
                break
            all_rows.extend(page)
            if len(page) < page_size:
                break
            offset += page_size

        return all_rows[:limit]
    except Exception as e:
        print(f"[SUPABASE] Erro ao buscar range {table}: {e}")
        return []
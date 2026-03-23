# binance_auth.py
# Assinatura HMAC SHA256 para endpoints autenticados da Binance Futures
# Gattiboni Enterprises - claudinho_o_sabio
#
# Uso:
#   from binance_auth import signed_get
#   data = signed_get("/fapi/v1/income", {"incomeType": "REALIZED_PNL", "limit": 1000})

import os
import hmac
import hashlib
import requests
from urllib.parse import urlencode
from dotenv import load_dotenv

load_dotenv()

BINANCE_BASE_URL   = "https://fapi.binance.com"
BINANCE_API_KEY    = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")


def _server_time() -> int:
    """Busca timestamp do servidor da Binance para evitar erro de sincronia."""
    try:
        resp = requests.get(f"{BINANCE_BASE_URL}/fapi/v1/time", timeout=5)
        return resp.json()["serverTime"]
    except Exception:
        import time
        return int(time.time() * 1000)


def _sign(params: dict) -> str:
    """Gera assinatura HMAC SHA256 dos parametros."""
    query = urlencode(params)
    return hmac.new(
        BINANCE_API_SECRET.encode("utf-8"),
        query.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def signed_get(endpoint: str, params: dict = None) -> list | dict | None:
    """
    Executa GET autenticado na API privada da Binance Futures.
    Adiciona timestamp do servidor e assinatura automaticamente.
    Retorna o JSON da resposta ou None em caso de erro.
    """
    if not BINANCE_API_KEY or not BINANCE_API_SECRET:
        print("[BINANCE_AUTH] BINANCE_API_KEY ou BINANCE_API_SECRET nao configurados.")
        return None

    p = dict(params) if params else {}
    p["timestamp"]  = _server_time()
    p["recvWindow"] = 5000
    p["signature"]  = _sign(p)

    headers = {"X-MBX-APIKEY": BINANCE_API_KEY}

    try:
        resp = requests.get(
            f"{BINANCE_BASE_URL}{endpoint}",
            params=p,
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        print(f"[BINANCE_AUTH] HTTP erro em {endpoint}: {e} — {resp.text}")
        return None
    except Exception as e:
        print(f"[BINANCE_AUTH] Erro em {endpoint}: {e}")
        return None


if __name__ == "__main__":
    result = signed_get("/fapi/v3/balance")
    if result:
        for asset in result:
            if float(asset.get("balance", 0)) > 0:
                print(f"  {asset['asset']}: {asset['balance']}")
    else:
        print("Falha na autenticacao ou sem saldo.")
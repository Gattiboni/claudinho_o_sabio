# cryptopanic_client.py
# Cliente thin wrapper para CryptoPanic Developer API v2
# Gattiboni Enterprises - claudinho_o_sabio
#
# Plano: Developer
# Limite: ~1000 requests/mes — usar com parcimonia
# Endpoint base: https://cryptopanic.com/api/developer/v2

import os
import requests
from dotenv import load_dotenv

load_dotenv()

CRYPTOPANIC_BASE_URL = "https://cryptopanic.com/api/developer/v2"


def fetch_news(currencies=None, filter_type=None, kind="news", region="en"):
    api_key = os.getenv("CRYPTOPANIC_API_KEY", "")
    if not api_key:
        print("[CRYPTOPANIC] API key nao configurada")
        return []

    params = {
        "auth_token": api_key,
        "public":     "true",
        "kind":       kind,
        "regions":    region,
    }
    if currencies is not None:
        params["currencies"] = currencies
    if filter_type is not None:
        params["filter"] = filter_type

    try:
        resp = requests.get(
            CRYPTOPANIC_BASE_URL + "/posts/",
            params=params,
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"[CRYPTOPANIC] Erro: {resp.status_code} {resp.text}")
            return []
    except Exception as e:
        print(f"[CRYPTOPANIC] Erro: {e}")
        return []

    results = resp.json().get("results", [])
    news = []
    for item in results:
        news.append({
            "title":           item.get("title", ""),
            "published_at":    item.get("published_at", ""),
            "currencies":      [inst["code"] for inst in item.get("instruments", [])],
            "votes_important": item.get("votes", {}).get("important", 0),
            "source_domain":   item.get("source", {}).get("domain", ""),
            "url":             item.get("url", ""),
        })
    return news


def fetch_important_news():
    """Convenience wrapper: noticias importantes recentes."""
    return fetch_news(filter_type="important", kind="news")


if __name__ == "__main__":
    news = fetch_important_news()
    print(f"{len(news)} noticia(s) encontrada(s):")
    for n in news:
        print(f"  [{n['votes_important']} votos] {n['title']} ({n['source_domain']})")

# spark_universe.py
# Spark Protocol - mapeamento e pre-selecao do universo de ativos
# Gattiboni Enterprises - claudinho_o_sabio

import requests

BINANCE_BASE_URL = "https://fapi.binance.com"
VOLUME_MIN_24H_USD = 1_000_000   # Minimo para ter liquidez real
VOLUME_MAX_24H_USD = 50_000_000  # Teto: acima disso ja e major, nao esquecido
CHANGE_EXCLUDE_PCT = 8.0         # Exclui quem ja se moveu mais de 8% nas 24h


def get_all_perpetual_usdt():
    """
    Retorna todos os futuros perpetuos USDT-M em TRADING.
    Sem filtro de volume ainda — so lista o universo total.
    """
    resp = requests.get(f"{BINANCE_BASE_URL}/fapi/v1/exchangeInfo", timeout=10)
    resp.raise_for_status()
    data = resp.json()

    perpetuals = [
        s["symbol"] for s in data["symbols"]
        if s.get("status") == "TRADING"
        and s.get("marginAsset") == "USDT"
        and s.get("contractType") == "PERPETUAL"
    ]
    return perpetuals


def get_spark_universe():
    """
    Retorna o universo de ativos candidatos ao Spark:
    - Perpetuos USDT em TRADING
    - Volume 24h entre 1M e 500M USD (nem morto nem major)
    - Variacao 24h entre -8% e +8% (nao se moveu ainda)
    - Ordenado por volume crescente (os mais esquecidos primeiro)

    Esses sao os "esquecidos que buscam gloria" — comprimidos,
    fora do radar, com energia acumulada sem ter explodido ainda.
    """
    # Busca tickers 24h
    resp = requests.get(f"{BINANCE_BASE_URL}/fapi/v1/ticker/24hr", timeout=10)
    resp.raise_for_status()
    tickers = resp.json()

    # Busca lista de perpetuos validos
    perpetuals = set(get_all_perpetual_usdt())

    candidates = []
    for t in tickers:
        symbol = t.get("symbol", "")
        if symbol not in perpetuals:
            continue

        try:
            volume = float(t["quoteVolume"])
            change = abs(float(t["priceChangePercent"]))
        except Exception:
            continue

        if volume < VOLUME_MIN_24H_USD:
            continue
        if volume > VOLUME_MAX_24H_USD:
            continue
        if change > CHANGE_EXCLUDE_PCT:
            continue

        candidates.append({
            "symbol":     symbol,
            "volume_24h": volume,
            "change_pct": float(t["priceChangePercent"]),
        })

    # Ordena por volume crescente — os mais esquecidos primeiro
    candidates.sort(key=lambda x: x["volume_24h"])
    return candidates


if __name__ == "__main__":
    print("Mapeando universo Spark...\n")

    all_perps = get_all_perpetual_usdt()
    print(f"Total de perpetuos USDT-M em TRADING: {len(all_perps)}")

    universe = get_spark_universe()
    print(f"Candidatos Spark (esquecidos, sem movimento): {len(universe)}")
    print(f"\nCriterios de selecao:")
    print(f"  Volume 24h:   entre $1M e $500M USD")
    print(f"  Variacao 24h: entre -{CHANGE_EXCLUDE_PCT}% e +{CHANGE_EXCLUDE_PCT}%")
    print(f"  Tipo:         apenas perpetuos USDT-M")
    print(f"\nTop 10 mais esquecidos (menor volume):")

    for i, c in enumerate(universe[:10], 1):
        print(f"  {i:2}. {c['symbol']:20s} | vol: ${c['volume_24h']:>15,.0f} | {c['change_pct']:+.2f}%")

    print(f"\nTop 10 com mais volume (teto do universo):")
    for i, c in enumerate(universe[-10:], 1):
        print(f"  {i:2}. {c['symbol']:20s} | vol: ${c['volume_24h']:>15,.0f} | {c['change_pct']:+.2f}%")

# analyzer.py
# Analise de performance de trades por periodo
# Gattiboni Enterprises - claudinho_o_sabio
#
# Logica:
#   1. Busca trades do Supabase no periodo solicitado
#   2. Busca notificacoes do Supabase no mesmo periodo
#   3. Cruza trades com notificacoes por simbolo e janela de tempo
#   4. Classifica cada trade como "claudinho_confirm", "claudinho_loop", "rescue" ou "olho"
#   5. Calcula KPIs por categoria e geral
#   6. Retorna relatorio formatado para Telegram
#
# Uso programatico:
#   from analyzer import run_analysis
#   report = run_analysis(days=7)

from datetime import datetime, timedelta, timezone

import pytz

from supabase_client import select_range

TIMEZONE = pytz.timezone("America/Sao_Paulo")


# -----------------------------------------------------------------------
# CONFIGURACAO
# -----------------------------------------------------------------------

NOTIFICATION_WINDOW_MINUTES = 5


# -----------------------------------------------------------------------
# CLASSIFICACAO
# -----------------------------------------------------------------------

def _classify_trades(trades: list, notifications: list, scan_results: list) -> list:
    """
    Classifica cada trade em uma de quatro categorias (mais flag ignorou_veto):
      - claudinho_confirm : notificacao de confirm nos 5 min anteriores ao trade
      - claudinho_loop    : notificacao de loop nos 10 min anteriores (sem confirm no simbolo)
      - rescue            : notificacao de rescue nos 60 min anteriores (sem confirm ou loop)
      - olho              : nenhuma correspondencia
      - ignorou_veto      : flag adicional, subconjunto de olho
    """
    WINDOW_CONFIRM = timedelta(minutes=5)
    WINDOW_LOOP    = timedelta(minutes=10)
    WINDOW_RESCUE  = timedelta(minutes=60)
    WINDOW_VETO    = timedelta(minutes=10)

    LOOP_PROTOCOLS = {"top5", "cascade", "spark", "roar"}

    classified = []

    for trade in trades:
        try:
            trade_time = datetime.fromisoformat(trade["time"])
            if trade_time.tzinfo is None:
                trade_time = trade_time.replace(tzinfo=timezone.utc)

            symbol       = trade["symbol"]
            category     = "olho"
            ignorou_veto = False

            # 1. Confirm nos 5 min anteriores (prioridade maxima)
            for notif in notifications:
                if notif["symbol"] != symbol:
                    continue
                if notif.get("protocol") != "confirm":
                    continue
                ntime = datetime.fromisoformat(notif["created_at"])
                if ntime.tzinfo is None:
                    ntime = ntime.replace(tzinfo=timezone.utc)
                if trade_time - WINDOW_CONFIRM <= ntime <= trade_time:
                    category = "claudinho_confirm"
                    break

            # 2. Loop nos 10 min anteriores
            if category == "olho":
                for notif in notifications:
                    if notif["symbol"] != symbol:
                        continue
                    if notif.get("protocol") not in LOOP_PROTOCOLS:
                        continue
                    ntime = datetime.fromisoformat(notif["created_at"])
                    if ntime.tzinfo is None:
                        ntime = ntime.replace(tzinfo=timezone.utc)
                    if trade_time - WINDOW_LOOP <= ntime <= trade_time:
                        category = "claudinho_loop"
                        break

            # 3. Rescue nos 60 min anteriores
            # Janela mais larga: o trader pode agir sobre o conselho com alguma demora
            if category == "olho":
                for notif in notifications:
                    if notif["symbol"] != symbol:
                        continue
                    if notif.get("protocol") != "rescue":
                        continue
                    ntime = datetime.fromisoformat(notif["created_at"])
                    if ntime.tzinfo is None:
                        ntime = ntime.replace(tzinfo=timezone.utc)
                    if trade_time - WINDOW_RESCUE <= ntime <= trade_time:
                        category = "rescue"
                        break

            # 4. Verifica se ignorou veto (flag, nao muda categoria)
            if category == "olho":
                for sr in scan_results:
                    if sr["symbol"] != symbol:
                        continue
                    if not sr.get("details_json", {}).get("vetoed"):
                        continue
                    srtime = datetime.fromisoformat(sr["created_at"])
                    if srtime.tzinfo is None:
                        srtime = srtime.replace(tzinfo=timezone.utc)
                    if trade_time - WINDOW_VETO <= srtime <= trade_time:
                        ignorou_veto = True
                        break

            classified.append({**trade, "category": category, "ignorou_veto": ignorou_veto})

        except Exception as e:
            print(f"[ANALYZER] Erro ao classificar trade: {e} | {trade}")

    return classified


# -----------------------------------------------------------------------
# KPIs
# -----------------------------------------------------------------------

def _calc_kpis(trades: list) -> dict:
    if not trades:
        return {
            "total":       0,
            "winners":     0,
            "losers":      0,
            "win_rate":    0.0,
            "pnl_bruto":   0.0,
            "pnl_liquido": 0.0,
            "maior_ganho": 0.0,
            "maior_perda": 0.0,
            "media_ganho": 0.0,
            "media_perda": 0.0,
        }

    pnls       = [float(t["realized_pnl"]) for t in trades]
    comissions = [float(t.get("commission") or 0) for t in trades]

    winners = [p for p in pnls if p > 0]
    losers  = [p for p in pnls if p < 0]

    pnl_bruto   = sum(pnls)
    pnl_liquido = pnl_bruto - sum(comissions)
    win_rate    = len(winners) / len(pnls) * 100 if pnls else 0.0

    return {
        "total":       len(pnls),
        "winners":     len(winners),
        "losers":      len(losers),
        "win_rate":    round(win_rate, 1),
        "pnl_bruto":   round(pnl_bruto, 2),
        "pnl_liquido": round(pnl_liquido, 2),
        "maior_ganho": round(max(winners), 2) if winners else 0.0,
        "maior_perda": round(min(losers),  2) if losers  else 0.0,
        "media_ganho": round(sum(winners) / len(winners), 2) if winners else 0.0,
        "media_perda": round(sum(losers)  / len(losers),  2) if losers  else 0.0,
    }


# -----------------------------------------------------------------------
# FORMATACAO DO RELATORIO
# -----------------------------------------------------------------------

def _format_report(days: int, all_kpis: dict, claudinho_kpis: dict, rescue_kpis: dict,
                   ignorou_kpis: dict, olho_kpis: dict,
                   total_trades: int, carteira: str) -> str:
    ts    = datetime.now(TIMEZONE).strftime("%d/%m/%Y %H:%M")
    label = "ultimas 24h" if days == 1 else f"ultimos {days} dias"

    def fmt_pnl(v):
        return f"{v:+.2f}" if v != 0 else "0.00"

    def fmt_pct(v):
        return f"{v:.1f}%"

    def col(val, width):
        return str(val).rjust(width)

    w = 10

    header = (
        f"{'':14}"
        f"{col('Geral', w)}"
        f"{col('Claudinho', w)}"
        f"{col('Rescue', w)}"
        f"{col('Ig.Veto', w)}"
        f"{col('Olho', w)}"
    )
    sep = "-" * (14 + w * 5)

    def row(label_str, g, c, r, iv, o):
        return (
            f"{label_str:<14}"
            f"{col(g, w)}"
            f"{col(c, w)}"
            f"{col(r, w)}"
            f"{col(iv, w)}"
            f"{col(o, w)}"
        )

    def kval(kpis, key, fmt_fn):
        return fmt_fn(kpis[key]) if kpis["total"] > 0 else "-"

    g  = all_kpis
    c  = claudinho_kpis
    r  = rescue_kpis
    iv = ignorou_kpis
    o  = olho_kpis

    lines = [
        f"[ANALISE] {ts}",
        f"Periodo: {label}",
        f"Carteira: {carteira} USDT",
        "",
        header,
        sep,
        row("Trades",
            g["total"],
            c["total"]  if c["total"]  > 0 else "-",
            r["total"]  if r["total"]  > 0 else "-",
            iv["total"] if iv["total"] > 0 else "-",
            o["total"]  if o["total"]  > 0 else "-"),
        row("W / L",
            f"{g['winners']}W/{g['losers']}L",
            f"{c['winners']}W/{c['losers']}L"   if c["total"]  > 0 else "-",
            f"{r['winners']}W/{r['losers']}L"   if r["total"]  > 0 else "-",
            f"{iv['winners']}W/{iv['losers']}L" if iv["total"] > 0 else "-",
            f"{o['winners']}W/{o['losers']}L"   if o["total"]  > 0 else "-"),
        row("Win rate",    kval(g,"win_rate",fmt_pct),    kval(c,"win_rate",fmt_pct),    kval(r,"win_rate",fmt_pct),    kval(iv,"win_rate",fmt_pct),    kval(o,"win_rate",fmt_pct)),
        row("PnL bruto",   kval(g,"pnl_bruto",fmt_pnl),   kval(c,"pnl_bruto",fmt_pnl),   kval(r,"pnl_bruto",fmt_pnl),   kval(iv,"pnl_bruto",fmt_pnl),   kval(o,"pnl_bruto",fmt_pnl)),
        row("Maior ganho", kval(g,"maior_ganho",fmt_pnl), kval(c,"maior_ganho",fmt_pnl), kval(r,"maior_ganho",fmt_pnl), kval(iv,"maior_ganho",fmt_pnl), kval(o,"maior_ganho",fmt_pnl)),
        row("Maior perda", kval(g,"maior_perda",fmt_pnl), kval(c,"maior_perda",fmt_pnl), kval(r,"maior_perda",fmt_pnl), kval(iv,"maior_perda",fmt_pnl), kval(o,"maior_perda",fmt_pnl)),
        row("Media ganho", kval(g,"media_ganho",fmt_pnl), kval(c,"media_ganho",fmt_pnl), kval(r,"media_ganho",fmt_pnl), kval(iv,"media_ganho",fmt_pnl), kval(o,"media_ganho",fmt_pnl)),
        row("Media perda", kval(g,"media_perda",fmt_pnl), kval(c,"media_perda",fmt_pnl), kval(r,"media_perda",fmt_pnl), kval(iv,"media_perda",fmt_pnl), kval(o,"media_perda",fmt_pnl)),
    ]

    # Comparativos
    comparativos = []
    if c["total"] > 0 and o["total"] > 0:
        diff = c["win_rate"] - o["win_rate"]
        comparativos.append(f"Claudinho vs Olho: {diff:+.1f}% em win rate")
    if r["total"] > 0 and o["total"] > 0:
        diff = r["win_rate"] - o["win_rate"]
        comparativos.append(f"Rescue vs Olho:    {diff:+.1f}% em win rate")
    if comparativos:
        lines.append("")
        lines.extend(comparativos)

    lines.append("")
    lines.append("Rescue = trade fechado/aberto ate 60min apos pedido E agora.")
    lines.append("Ig.Veto = subconjunto de Olho. Entrou contra o veto do 1h.")

    return "\n".join(lines)


# -----------------------------------------------------------------------
# INTERFACE PRINCIPAL
# -----------------------------------------------------------------------

def run_analysis(days: int) -> str:
    now       = datetime.now(timezone.utc)
    start     = now - timedelta(days=days)
    start_iso = start.isoformat()
    end_iso   = now.isoformat()

    print(f"[ANALYZER] Buscando trades dos ultimos {days} dias...")
    trades = select_range("trades", "time", start_iso, end_iso, limit=5000)

    if not trades:
        return f"Nenhum trade encontrado nos ultimos {'24h' if days == 1 else str(days) + ' dias'}."

    print(f"[ANALYZER] {len(trades)} trades encontrados. Buscando notificacoes e scan_results...")
    notifications = select_range(
        "notifications_sent", "created_at", start_iso, end_iso, limit=5000
    )
    scan_results_raw = select_range(
        "scan_results", "created_at", start_iso, end_iso, limit=5000
    )
    print(f"[ANALYZER] {len(notifications)} notificacoes | {len(scan_results_raw)} scan_results.")

    classified       = _classify_trades(trades, notifications, scan_results_raw)
    claudinho_trades = [t for t in classified if t["category"].startswith("claudinho")]
    rescue_trades    = [t for t in classified if t["category"] == "rescue"]
    ignorou_trades   = [t for t in classified if t["ignorou_veto"]]
    olho_trades      = [t for t in classified if t["category"] == "olho"]

    all_kpis       = _calc_kpis(classified)
    claudinho_kpis = _calc_kpis(claudinho_trades)
    rescue_kpis    = _calc_kpis(rescue_trades)
    ignorou_kpis   = _calc_kpis(ignorou_trades)
    olho_kpis      = _calc_kpis(olho_trades)

    carteira = "indisponivel"
    try:
        from binance_auth import signed_get
        balances = signed_get("/fapi/v2/balance", {})
        if balances:
            for asset in balances:
                if asset.get("asset") == "USDT":
                    carteira = f"{float(asset['availableBalance']):.2f}"
                    break
    except Exception as e:
        print(f"[ANALYZER] Erro ao buscar saldo: {e}")

    report = _format_report(
        days, all_kpis, claudinho_kpis, rescue_kpis,
        ignorou_kpis, olho_kpis, len(trades), carteira
    )
    return report


# -----------------------------------------------------------------------
# ENTRYPOINT
# -----------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    print(run_analysis(days=days))

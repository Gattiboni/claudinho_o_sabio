# analyzer.py
# Analise de performance de trades por periodo
# Gattiboni Enterprises - claudinho_o_sabio
#
# Logica:
#   1. Busca trades do Supabase no periodo solicitado
#   2. Busca notificacoes do Supabase no mesmo periodo
#   3. Cruza trades com notificacoes por simbolo e janela de 5 minutos
#   4. Classifica cada trade como "claudinho" ou "olho"
#   5. Calcula KPIs por categoria e geral
#   6. Retorna relatorio formatado para Telegram
#
# Uso programatico:
#   from analyzer import run_analysis
#   report = run_analysis(days=7)

from datetime import datetime, timedelta, timezone

from supabase_client import select_range


# -----------------------------------------------------------------------
# CONFIGURACAO
# -----------------------------------------------------------------------

NOTIFICATION_WINDOW_MINUTES = 5


# -----------------------------------------------------------------------
# CLASSIFICACAO
# -----------------------------------------------------------------------

def _classify_trades(trades: list, notifications: list) -> list:
    """
    Classifica cada trade como 'claudinho' ou 'olho'.
    Um trade e 'claudinho' se existe notificacao para o mesmo simbolo
    nos 5 minutos anteriores ao trade.
    """
    classified = []

    for trade in trades:
        try:
            trade_time = datetime.fromisoformat(trade["time"])
            if trade_time.tzinfo is None:
                trade_time = trade_time.replace(tzinfo=timezone.utc)

            symbol   = trade["symbol"]
            category = "olho"

            window_start = trade_time - timedelta(minutes=NOTIFICATION_WINDOW_MINUTES)

            for notif in notifications:
                if notif["symbol"] != symbol:
                    continue
                notif_time = datetime.fromisoformat(notif["created_at"])
                if notif_time.tzinfo is None:
                    notif_time = notif_time.replace(tzinfo=timezone.utc)
                if window_start <= notif_time <= trade_time:
                    category = "claudinho"
                    break

            classified.append({**trade, "category": category})
        except Exception as e:
            print(f"[ANALYZER] Erro ao classificar trade: {e} | {trade}")

    return classified


# -----------------------------------------------------------------------
# KPIs
# -----------------------------------------------------------------------

def _calc_kpis(trades: list) -> dict:
    """
    Calcula KPIs para uma lista de trades classificados.
    """
    if not trades:
        return {
            "total":        0,
            "winners":      0,
            "losers":       0,
            "win_rate":     0.0,
            "pnl_bruto":    0.0,
            "pnl_liquido":  0.0,
            "maior_ganho":  0.0,
            "maior_perda":  0.0,
            "media_ganho":  0.0,
            "media_perda":  0.0,
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
        "pnl_bruto":   round(pnl_bruto, 4),
        "pnl_liquido": round(pnl_liquido, 4),
        "maior_ganho": round(max(winners), 4) if winners else 0.0,
        "maior_perda": round(min(losers),  4) if losers  else 0.0,
        "media_ganho": round(sum(winners) / len(winners), 4) if winners else 0.0,
        "media_perda": round(sum(losers)  / len(losers),  4) if losers  else 0.0,
    }


# -----------------------------------------------------------------------
# FORMATACAO DO RELATORIO
# -----------------------------------------------------------------------

def _format_kpis(label: str, kpis: dict) -> list:
    """Formata bloco de KPIs para uma categoria."""
    if kpis["total"] == 0:
        return [f"{label}: nenhum trade no periodo."]

    lines = [
        f"{label}",
        f"  Trades:      {kpis['total']}  ({kpis['winners']}W / {kpis['losers']}L)",
        f"  Win rate:    {kpis['win_rate']}%",
        f"  PnL bruto:   {kpis['pnl_bruto']:+.4f} USDT",
        f"  PnL liquido: {kpis['pnl_liquido']:+.4f} USDT",
        f"  Maior ganho: {kpis['maior_ganho']:+.4f} USDT",
        f"  Maior perda: {kpis['maior_perda']:+.4f} USDT",
        f"  Media ganho: {kpis['media_ganho']:+.4f} USDT",
        f"  Media perda: {kpis['media_perda']:+.4f} USDT",
    ]
    return lines


def _format_report(days: int, all_kpis: dict, claudinho_kpis: dict,
                   olho_kpis: dict, total_trades: int) -> str:
    """Monta o relatorio completo."""
    ts    = datetime.now().strftime("%d/%m/%Y %H:%M")
    label = f"ultimas 24h" if days == 1 else f"ultimos {days} dias"

    lines = [
        f"[ANALISE] {ts}",
        f"Periodo: {label}",
        f"Total de registros: {total_trades}",
        "",
    ]

    lines += _format_kpis("Geral", all_kpis)
    lines.append("")
    lines += _format_kpis("Com sinal do Claudinho", claudinho_kpis)
    lines.append("")
    lines += _format_kpis("No olho (sem sinal)", olho_kpis)

    # Comparativo so aparece se ambas as categorias tiverem trades
    if claudinho_kpis["total"] > 0 and olho_kpis["total"] > 0:
        diff = claudinho_kpis["win_rate"] - olho_kpis["win_rate"]
        diff_str = f"+{diff:.1f}%" if diff >= 0 else f"{diff:.1f}%"
        lines.append("")
        lines.append(f"Claudinho vs olho: {diff_str} de diferenca em win rate")

    return "\n".join(lines)


# -----------------------------------------------------------------------
# INTERFACE PRINCIPAL
# -----------------------------------------------------------------------

def run_analysis(days: int) -> str:
    """
    Executa a analise completa para os ultimos N dias.
    Retorna o relatorio formatado para envio no Telegram.
    """
    now      = datetime.now(timezone.utc)
    start    = now - timedelta(days=days)
    start_iso = start.isoformat()
    end_iso   = now.isoformat()

    print(f"[ANALYZER] Buscando trades dos ultimos {days} dias...")
    trades = select_range("trades", "time", start_iso, end_iso, limit=5000)

    if not trades:
        return f"Nenhum trade encontrado nos ultimos {'24h' if days == 1 else str(days) + ' dias'}."

    print(f"[ANALYZER] {len(trades)} trades encontrados. Buscando notificacoes...")
    notifications = select_range(
        "notifications_sent", "created_at", start_iso, end_iso, limit=5000
    )
    print(f"[ANALYZER] {len(notifications)} notificacoes encontradas.")

    classified      = _classify_trades(trades, notifications)
    claudinho_trades = [t for t in classified if t["category"] == "claudinho"]
    olho_trades      = [t for t in classified if t["category"] == "olho"]

    all_kpis       = _calc_kpis(classified)
    claudinho_kpis = _calc_kpis(claudinho_trades)
    olho_kpis      = _calc_kpis(olho_trades)

    report = _format_report(days, all_kpis, claudinho_kpis, olho_kpis, len(trades))
    return report


# -----------------------------------------------------------------------
# ENTRYPOINT
# -----------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    print(run_analysis(days=days))

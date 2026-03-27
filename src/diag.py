from supabase_client import select_range
from datetime import datetime, timedelta, timezone

now   = datetime.now(timezone.utc)
start = (now - timedelta(days=1)).isoformat()
end   = now.isoformat()

notifs = select_range("notifications_sent", "created_at", start, end, limit=100)
trades = select_range("trades", "time", start, end, limit=100)

for t in trades:
    tsym  = t.get("symbol")
    ttime = datetime.fromisoformat(t.get("time"))
    if ttime.tzinfo is None:
        ttime = ttime.replace(tzinfo=timezone.utc)

    for n in notifs:
        if n.get("symbol") != tsym:
            continue
        ntime = datetime.fromisoformat(n.get("created_at"))
        if ntime.tzinfo is None:
            ntime = ntime.replace(tzinfo=timezone.utc)
        diff = (ttime - ntime).total_seconds()
        print(f"{tsym} | trade={ttime.strftime('%H:%M:%S')} notif={ntime.strftime('%H:%M:%S')} diff={diff:.0f}s")

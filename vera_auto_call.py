"""Owner opt-in, bounded automatic work calls. No secrets or task text in policy."""
from datetime import datetime
from zoneinfo import ZoneInfo

from vera_push import FCM_TTL

TAIPEI = ZoneInfo("Asia/Taipei")
DAILY_LIMIT = 2
# Reserve enough time for the FCM request and notification TTL before midnight.
MIDNIGHT_MARGIN = FCM_TTL + 15


def schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS vera_auto_policy (
        singleton INTEGER PRIMARY KEY CHECK(singleton=1), enabled INTEGER NOT NULL,
        device TEXT NOT NULL, deliver INTEGER NOT NULL, changed INTEGER NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS vera_auto_calls (
        task TEXT PRIMARY KEY, event TEXT NOT NULL UNIQUE, device TEXT NOT NULL,
        due INTEGER NOT NULL, local_day TEXT NOT NULL, created INTEGER NOT NULL)""")
    db.execute("CREATE INDEX IF NOT EXISTS vera_auto_calls_day ON vera_auto_calls(local_day)")


def local_day(stamp):
    return datetime.fromtimestamp(stamp, TAIPEI).date().isoformat()


def allowed_time(stamp):
    local = datetime.fromtimestamp(stamp, TAIPEI)
    seconds = local.hour * 3600 + local.minute * 60 + local.second
    return 10 * 3600 <= seconds < 86400 - MIDNIGHT_MARGIN


def policy(db):
    row = db.execute("SELECT enabled,device,deliver FROM vera_auto_policy WHERE singleton=1").fetchone()
    return {"enabled": bool(row[0]) if row else False, "device_id": row[1] if row else "",
            "return_result": bool(row[2]) if row else False, "timezone": "Asia/Taipei",
            "start": "10:00", "end": "24:00", "daily_limit": DAILY_LIMIT}


def delivery_allowed(db, event, now):
    # Existing manual calls and pre-feature databases retain their current behavior.
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='vera_auto_calls'").fetchone():
        return True
    row = db.execute("SELECT device,due FROM vera_auto_calls WHERE event=?", (event,)).fetchone()
    if not row:
        return True
    setting = policy(db)
    return (setting["enabled"] and setting["device_id"] == row[0]
            and local_day(now) == local_day(row[1]) and allowed_time(now))

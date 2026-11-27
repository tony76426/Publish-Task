"""Owner-controlled opt-in for source-requested VERA calls (Taiwan local time)."""
from datetime import datetime, timezone, timedelta

TW = timezone(timedelta(hours=8))
MAX_DAILY = 2


def auto_schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS vera_auto_policy (
        id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL,
        device TEXT NOT NULL, deliver INTEGER NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS vera_auto_requests (
        task TEXT PRIMARY KEY, event TEXT NOT NULL UNIQUE,
        due INTEGER NOT NULL, device TEXT NOT NULL)""")


def auto_policy(db):
    auto_schema(db)
    row = db.execute("SELECT enabled,device,deliver FROM vera_auto_policy WHERE id=1").fetchone()
    return (bool(row[0]), row[1], bool(row[2])) if row else (False, "", False)


def permitted(stamp):
    local = datetime.fromtimestamp(stamp, TW)
    # Leave one minute before midnight for the existing 45-second FCM TTL.
    return 10 <= local.hour and (local.hour, local.minute) < (23, 59)


def day_bounds(stamp):
    local = datetime.fromtimestamp(stamp, TW)
    first = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(first.timestamp()), int((first + timedelta(days=1)).timestamp())


def dispatch_allowed(db, event, device, now):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='vera_auto_requests'").fetchone():
        return True
    row = db.execute("SELECT device FROM vera_auto_requests WHERE event=?", (event,)).fetchone()
    if not row:
        return True
    enabled, chosen, _ = auto_policy(db)
    return enabled and device == chosen == row[0] and permitted(now)

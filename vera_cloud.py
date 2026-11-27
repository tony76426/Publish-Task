"""Cloud-call queue, authenticated diagnostics, and device receipts."""

import os
import re
import time
from uuid import uuid4

from flask import jsonify, request

from vera_push import DEVICE_LIFETIME, FCM_TTL, PROJECT_ID, DeviceUnregistered
from vera_push import credentials_configured, registry, send_fcm, valid_id
from vera_auto_call import delivery_allowed

VERSION = "0.3.0"
TERMINAL = frozenset({"accepted", "declined", "missed", "quiet", "busy", "blocked", "failed", "cancelled"})
DEVICE_STATES = TERMINAL - {"cancelled"} | {"received", "ringing"}
DAY = 86400


def schema(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS cloud_calls (
            id TEXT PRIMARY KEY, device TEXT NOT NULL, due INTEGER NOT NULL,
            purpose TEXT NOT NULL, task TEXT NOT NULL, test INTEGER NOT NULL,
            retry INTEGER NOT NULL, retry_of TEXT UNIQUE, state TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT '', changed INTEGER NOT NULL
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS cloud_calls_due ON cloud_calls(state,due)")
    db.execute("CREATE INDEX IF NOT EXISTS cloud_calls_device ON cloud_calls(device,due)")
    db.execute("""CREATE TABLE IF NOT EXISTS cloud_call_history (
                    id TEXT NOT NULL, state TEXT NOT NULL, at INTEGER NOT NULL,
                    PRIMARY KEY(id,state), FOREIGN KEY(id) REFERENCES cloud_calls(id)
                  )""")


def record(db, event, state, at):
    db.execute("INSERT OR IGNORE INTO cloud_call_history VALUES(?,?,?)", (event, state, at))


def finish_dispatch(event, state, reason=""):
    with registry() as db:
        # A phone receipt can arrive before FCM returns its acknowledgement.
        now = int(time.time())
        db.execute("UPDATE cloud_calls SET state=?,reason=?,changed=? WHERE id=? AND state='sending'",
                   (state, reason, now, event))
        record(db, event, state, now)


def dispatch_due(log, now=None):
    now = int(time.time()) if now is None else now
    with registry() as db:
        schema(db)
        db.execute("DELETE FROM cloud_call_history WHERE id IN (SELECT id FROM cloud_calls WHERE changed < ?)",
                   (now - 30 * DAY,))
        db.execute("DELETE FROM cloud_calls WHERE changed < ?", (now - 30 * DAY,))
        db.execute("UPDATE cloud_calls SET state='failed',reason='expired',changed=? WHERE state='queued' AND due < ?",
                   (now, now - FCM_TTL))
        db.execute("UPDATE cloud_calls SET state='unconfirmed',reason='no_receipt',changed=? WHERE state IN ('sending','fcm_accepted','received','ringing','send_unknown') AND due < ?",
                   (now, now - 120))
        row = db.execute("""
            UPDATE cloud_calls SET state='sending', changed=?
            WHERE id=(SELECT id FROM cloud_calls WHERE state='queued' AND due<=? ORDER BY due,id LIMIT 1)
            RETURNING id,device,test,task
        """, (now, now)).fetchone()
        if not row:
            return False
        event, device, test, task = row
        if not delivery_allowed(db, event, now):
            db.execute("UPDATE cloud_calls SET state='cancelled',reason='auto_quiet_or_revoked',changed=? WHERE id=?", (now, event))
            record(db, event, "cancelled", now)
            return True
        record(db, event, "sending", now)
        registration = db.execute("SELECT token FROM devices WHERE id=? AND updated>=?",
                                  (device, now - DEVICE_LIFETIME)).fetchone()
    if not registration:
        finish_dispatch(event, "failed", "device_unregistered")
        return True
    if not credentials_configured():
        finish_dispatch(event, "failed", "sender_not_configured")
        return True
    token, = registration
    payload = {
        "type": "vera_call", "event_id": event, "test": str(bool(test)).lower(),
        "expires_at": str((now + FCM_TTL) * 1000),
    }
    if task and not test:
        payload["task_id"] = task
    try:
        send_fcm(token, payload)
    except DeviceUnregistered:
        with registry() as db:
            db.execute("DELETE FROM devices WHERE id=? AND token=?", (device, token))
        finish_dispatch(event, "failed", "device_unregistered")
    except Exception as exc:
        log.warning("Cloud call send failed: %s", type(exc).__name__)
        finish_dispatch(event, "send_unknown", "firebase_send_error")
    else:
        finish_dispatch(event, "fcm_accepted")
    return True


def run_scheduler(stop, log):
    while not stop.is_set():
        try:
            for _ in range(5):
                if stop.is_set() or not dispatch_due(log):
                    break
        except Exception as exc:
            log.warning("Cloud call scheduler error: %s", type(exc).__name__)
        stop.wait(4)


def install_cloud_routes(app, guard, throttle, work_context=None):
    def device_body():
        body = request.get_json(silent=True)
        return body if isinstance(body, dict) and valid_id(body.get("device_id")) else None

    @app.post("/api/cloud/status")
    def cloud_status():
        error = guard()
        if error:
            return error
        body = request.get_json(silent=True)
        device = body.get("device_id") if isinstance(body, dict) else None
        now = int(time.time())
        registered, rows, trail = False, [], {}
        if valid_id(device):
            with registry() as db:
                schema(db)
                registered = db.execute("SELECT 1 FROM devices WHERE id=? AND updated>=?",
                                        (device, now - DEVICE_LIFETIME)).fetchone() is not None
                rows = db.execute("""SELECT id,due,state,reason,test,retry_of,changed FROM cloud_calls
                                     WHERE device=? ORDER BY changed DESC LIMIT 50""", (device,)).fetchall()
                if rows:
                    ids = [row[0] for row in rows]
                    placeholders = ",".join("?" for _ in ids)
                    for call_id, state, at in db.execute(
                            f"SELECT id,state,at FROM cloud_call_history WHERE id IN ({placeholders}) ORDER BY rowid", ids):
                        trail.setdefault(call_id, []).append({"state": state, "at": at})
        fields = ("event_id", "due", "state", "reason", "test", "retry_of", "changed")
        return jsonify(project_id=PROJECT_ID, version=VERSION, registered=registered,
                       credentials_configured=credentials_configured(), storage_configured=bool(os.getenv("VERA_PUSH_DB")),
                       events=[dict(zip(fields, row), trail=trail.get(row[0], [])) for row in rows])

    @app.route("/api/cloud/calls", methods=["POST", "DELETE"])
    def cloud_calls():
        error = guard()
        if error:
            return error
        if not throttle("cloud_calls", 15, 60):
            return jsonify(error="雲端來電操作過於頻繁"), 429
        body = device_body()
        if not body or not valid_id(body.get("event_id")):
            return jsonify(error="裝置或來電 ID 無效"), 400
        device, event = body["device_id"], body["event_id"]
        now = int(time.time())
        if request.method == "DELETE":
            with registry() as db:
                schema(db)
                n = db.execute("""UPDATE cloud_calls SET state='cancelled',changed=?
                                  WHERE id=? AND device=? AND state='queued'""", (now, event, device)).rowcount
                if n:
                    record(db, event, "cancelled", now)
            return (jsonify(status="cancelled"), 200) if n else (jsonify(error="來電已開始或不在排程中"), 409)

        test, retry = body.get("test", False), body.get("retry", False)
        due = body.get("due", now + 1)
        task, purpose = body.get("task_id", ""), body.get("purpose", "")
        if (type(test) is not bool or type(retry) is not bool or type(due) is not int
                or not now <= due <= now + 30 * DAY or not isinstance(purpose, str) or len(purpose) > 240
                or not isinstance(task, str) or (task and not re.fullmatch(r"[A-Za-z0-9-]{1,80}", task))):
            return jsonify(error="請輸入有效的來電內容及 30 天內的時間"), 400
        if not credentials_configured():
            return jsonify(error="Render 尚未設定 Firebase 發送憑證"), 503
        with registry() as db:
            schema(db)
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM devices WHERE id=? AND updated>=?", (device, now - DEVICE_LIFETIME)).fetchone():
                return jsonify(error="裝置尚未註冊或已取消"), 404
            if db.execute("SELECT 1 FROM cloud_calls WHERE id=?", (event,)).fetchone():
                return jsonify(error="來電事件已存在"), 409
            if db.execute("SELECT COUNT(*) FROM cloud_calls WHERE device=? AND state='queued'", (device,)).fetchone()[0] >= 30:
                return jsonify(error="此裝置最多可保留 30 通待發來電"), 409
            db.execute("""
                INSERT INTO cloud_calls (id,device,due,purpose,task,test,retry,state,changed)
                VALUES(?,?,?,?,?,?,?,'queued',?)
            """, (event, device, due, "" if test else purpose.strip(), "" if test else task, test, retry and not test, now))
            record(db, event, "queued", now)
        return jsonify(status="queued", event_id=event), 202

    @app.put("/api/cloud/receipt")
    def cloud_receipt():
        error = guard()
        if error:
            return error
        if not throttle("cloud_receipts", 120, 60):
            return jsonify(error="狀態回報過於頻繁"), 429
        body = device_body()
        state = body.get("state") if body else None
        if not body or not valid_id(body.get("event_id")) or not isinstance(state, str) or state not in DEVICE_STATES:
            return jsonify(error="來電狀態無效"), 400
        event, device = body["event_id"], body["device_id"]
        now = int(time.time())
        with registry() as db:
            schema(db)
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("""SELECT due, purpose, task, test, retry, state FROM cloud_calls
                                WHERE id=? AND device=?""", (event, device)).fetchone()
            if not row or not db.execute("SELECT 1 FROM devices WHERE id=?", (device,)).fetchone():
                return jsonify(error="查無來電事件或裝置已撤銷"), 404
            due, purpose, task, test, retry, previous = row
            if previous == "queued":
                return jsonify(error="尚未發出此事件"), 409
            if previous in TERMINAL or (previous == "ringing" and state == "received"):
                return "", 204
            db.execute("UPDATE cloud_calls SET state=?,reason='',changed=? WHERE id=?", (state, now, event))
            record(db, event, state, now)
            if state == "missed" and retry and not test and now <= due + 180:
                retry_id = str(uuid4())
                n = db.execute("""
                    INSERT OR IGNORE INTO cloud_calls (id,device,due,purpose,task,test,retry,retry_of,state,changed)
                    VALUES (?,?,?,?,?,0,0,?,'queued',?)
                """, (retry_id, device, now + 300, purpose, task, event, now)).rowcount
                if n:
                    record(db, retry_id, "queued", now)
        return "", 204

    @app.post("/api/cloud/context")
    def cloud_context():
        error = guard()
        if error:
            return error
        body = device_body()
        if not body or not valid_id(body.get("event_id")):
            return jsonify(error="來電識別碼無效"), 400
        now = int(time.time())
        with registry() as db:
            schema(db)
            row = db.execute("""SELECT purpose, task, test, COALESCE(retry_of,id) FROM cloud_calls
                                WHERE id=? AND device=? AND state='accepted' AND changed>=?
                                AND EXISTS(SELECT 1 FROM devices WHERE id=?)""",
                             (body["event_id"], body["device_id"], now-300, body["device_id"])).fetchone()
            if not row:
                return jsonify(error="尚未收到接聽確認，或來電內容已到期"), 404
            if work_context and row[1] and not row[2]:
                context = work_context(db, row[3])
                if context:
                    return jsonify(context)
            return jsonify(purpose=row[0], task_id=row[1], test=bool(row[2]))

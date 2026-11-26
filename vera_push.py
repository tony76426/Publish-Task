"""FCM device enrollment and on-demand dispatch for the private VERA backend."""

import contextlib
import os
import re
import sqlite3
import tempfile
import time
from datetime import timedelta
from pathlib import Path
from threading import Lock
from uuid import UUID

from flask import jsonify, request

PROJECT_ID = "vera-nexus-e5119"
RENDER_CREDENTIAL_FILE = "/etc/secrets/vera-firebase.json"
DEVICE_LIFETIME = 30 * 24 * 60 * 60
EVENT_LIFETIME = 24 * 60 * 60
FCM_TTL = 45
firebase_lock = Lock()


class PushUnavailable(Exception):
    pass


class DeviceUnregistered(Exception):
    pass


def credentials_configured():
    return Path(os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or RENDER_CREDENTIAL_FILE).is_file()


def send_fcm(token, data):
    if not credentials_configured():
        raise PushUnavailable
    import firebase_admin
    from firebase_admin import messaging

    with firebase_lock:
        try:
            app = firebase_admin.get_app()
        except ValueError:
            path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or RENDER_CREDENTIAL_FILE
            app = firebase_admin.initialize_app(firebase_admin.credentials.Certificate(path),
                                                options={"projectId": PROJECT_ID, "httpTimeout": 10})
    try:
        messaging.send(
            messaging.Message(
                token=token,
                data=data,
                android=messaging.AndroidConfig(priority="high", ttl=timedelta(seconds=FCM_TTL)),
            ),
            app=app,
        )
    except messaging.UnregisteredError as exc:
        raise DeviceUnregistered from exc


@contextlib.contextmanager
def registry():
    path = Path(os.getenv("VERA_PUSH_DB") or Path(tempfile.gettempdir()) / "vera-nexus-push" / "push.sqlite3")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with contextlib.closing(sqlite3.connect(path, timeout=5)) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS devices (id TEXT PRIMARY KEY, token TEXT NOT NULL, updated INTEGER NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS dispatch (id TEXT PRIMARY KEY, device TEXT NOT NULL, state TEXT NOT NULL, created INTEGER NOT NULL)")
        yield db


def valid_id(value):
    if not isinstance(value, str) or len(value) != 36:
        return False
    try:
        return str(UUID(value, version=4)) == value
    except ValueError:
        return False


def install_push_routes(app, guard, throttle):
    @app.post("/api/push/status")
    def push_status():
        error = guard()
        if error:
            return error
        return jsonify(project_id=PROJECT_ID, credentials_configured=credentials_configured())

    @app.route("/api/push/device", methods=["PUT", "DELETE"])
    def push_device():
        error = guard()
        if error:
            return error
        if not throttle("push_device", 30, 60):
            return jsonify(error="裝置設定過於頻繁"), 429
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not valid_id(data.get("device_id")):
            return jsonify(error="裝置識別碼無效"), 400
        device = data["device_id"]
        if request.method == "DELETE":
            with registry() as db:
                db.execute("DELETE FROM devices WHERE id = ?", (device,))
            return "", 204
        token = data.get("token")
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9:_-]{20,1024}", token):
            return jsonify(error="推播裝置憑證格式無效"), 400
        now = int(time.time())
        with registry() as db:
            db.execute("DELETE FROM devices WHERE updated < ? OR (token = ? AND id <> ?)", (now - DEVICE_LIFETIME, token, device))
            db.execute(
                "INSERT INTO devices VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET token=excluded.token, updated=excluded.updated",
                (device, token, now),
            )
        return "", 204

    @app.post("/api/push/dispatch")
    def push_dispatch():
        error = guard()
        if error:
            return error
        if not throttle("push_dispatch", 12, 60):
            return jsonify(error="推播要求過於頻繁"), 429
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not all(valid_id(data.get(k)) for k in ("device_id", "event_id")):
            return jsonify(error="裝置或事件識別碼無效"), 400
        test = data.get("test", False)
        task = data.get("task_id", "")
        if type(test) is not bool or not isinstance(task, str) or (task and not re.fullmatch(r"[A-Za-z0-9-]{1,80}", task)):
            return jsonify(error="推播事件格式無效"), 400
        if not credentials_configured():
            return jsonify(error="Render 尚未設定 Firebase 發送憑證"), 503

        device, event = data["device_id"], data["event_id"]
        now = int(time.time())
        with registry() as db:
            # First write takes the SQLite transaction lock before we reserve an event.
            db.execute("DELETE FROM dispatch WHERE created < ?", (now - EVENT_LIFETIME,))
            if db.execute("SELECT 1 FROM dispatch WHERE id = ?", (event,)).fetchone():
                return jsonify(error="此事件已處理或正在發送", event_id=event), 409
            row = db.execute("SELECT token FROM devices WHERE id = ? AND updated >= ?", (device, now - DEVICE_LIFETIME)).fetchone()
            if not row:
                return jsonify(error="裝置尚未註冊、已到期或已取消"), 404
            db.execute("INSERT INTO dispatch VALUES (?, ?, 'pending', ?)", (event, device, now))
        token, = row
        payload = {
            "type": "vera_call",
            "event_id": event,
            "expires_at": str((now + FCM_TTL) * 1000),
            "test": "true" if test else "false",
        }
        if task and not test:
            payload["task_id"] = task
        # Network timeouts leave the outcome ambiguous. Keep the reservation to avoid ringing twice.
        try:
            send_fcm(token, payload)
        except DeviceUnregistered:
            with registry() as db:
                db.execute("DELETE FROM devices WHERE id = ? AND token = ?", (device, token))
                db.execute("UPDATE dispatch SET state = 'unregistered' WHERE id = ?", (event,))
            return jsonify(error="裝置推播憑證已失效，請重新開啟 App"), 410
        except Exception as exc:
            app.logger.warning("FCM dispatch failed: %s", type(exc).__name__)
            with registry() as db:
                db.execute("UPDATE dispatch SET state = 'unknown' WHERE id = ?", (event,))
            return jsonify(error="Firebase 發送未獲確認", event_id=event), 502
        with registry() as db:
            db.execute("UPDATE dispatch SET state = 'accepted' WHERE id = ?", (event,))
        return jsonify(status="accepted_by_fcm", event_id=event), 202

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from vera_app import app, limits
from vera_push import DeviceUnregistered, PROJECT_ID, registry


class VeraPushTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = patch.dict(os.environ, {
            "VERA_ACCESS_TOKEN": "mock-test-bearer-only",
            "VERA_PUSH_DB": str(Path(tmp.name) / "test.sqlite3"),
            "GOOGLE_APPLICATION_CREDENTIALS": "",
        })
        env.start()
        self.addCleanup(env.stop)
        limits.clear()
        self.client = app.test_client()
        self.auth = {"Authorization": "Bearer mock-test-bearer-only"}
        self.device = str(uuid4())
        self.event = str(uuid4())
        self.token = "mock-device-registration-token"

    def enroll(self, token=None):
        return self.client.put("/api/push/device", headers=self.auth, json={
            "device_id": self.device, "token": token or self.token,
        })

    def dispatch(self, **data):
        return self.client.post("/api/push/dispatch", headers=self.auth, json={
            "device_id": self.device, "event_id": self.event, **data,
        })

    def test_requires_existing_vera_auth(self):
        self.assertEqual(self.client.post("/api/push/status").status_code, 401)
        self.assertEqual(self.client.put("/api/push/device").status_code, 401)
        self.assertEqual(self.client.delete("/api/push/device").status_code, 401)
        self.assertEqual(self.client.post("/api/push/dispatch").status_code, 401)

    def test_reports_missing_credentials_with_no_send(self):
        status = self.client.post("/api/push/status", headers=self.auth)
        self.assertEqual(status.json, {"project_id": PROJECT_ID, "credentials_configured": False})
        with patch("vera_push.send_fcm") as send:
            self.assertEqual(self.dispatch().status_code, 503)
            send.assert_not_called()

    def test_validates_json_and_ids(self):
        self.assertEqual(self.client.put("/api/push/device", headers=self.auth, json=[]).status_code, 400)
        self.assertEqual(self.enroll("invalid token").status_code, 400)
        self.assertEqual(self.dispatch(event_id="invalid").status_code, 400)
        self.assertEqual(self.dispatch(test=1).status_code, 400)
        self.assertEqual(self.dispatch(task_id="contains whitespace").status_code, 400)

    @patch("vera_push.credentials_configured", return_value=True)
    @patch("vera_push.send_fcm")
    def test_sends_once_without_private_payload_and_updates_token(self, send, _configured):
        self.assertEqual(self.enroll().status_code, 204)
        self.assertEqual(self.enroll("rotated-device-registration-token").status_code, 204)
        response = self.dispatch(test=True, task_id="excluded-in-test", transcript="private")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json["status"], "accepted_by_fcm")
        self.assertEqual(self.dispatch().status_code, 409)
        send.assert_called_once()
        token, payload = send.call_args.args
        self.assertEqual(token, "rotated-device-registration-token")
        self.assertEqual(set(payload), {"type", "event_id", "expires_at", "test"})
        self.assertEqual(payload["event_id"], self.event)
        self.assertEqual(payload["test"], "true")

    @patch("vera_push.credentials_configured", return_value=True)
    @patch("vera_push.send_fcm")
    def test_revoked_device_does_not_receive_anything(self, send, _configured):
        self.assertEqual(self.enroll().status_code, 204)
        removed = self.client.delete("/api/push/device", headers=self.auth, json={"device_id": self.device})
        self.assertEqual(removed.status_code, 204)
        self.assertEqual(self.dispatch().status_code, 404)
        send.assert_not_called()

    @patch("vera_push.credentials_configured", return_value=True)
    @patch("vera_push.send_fcm", side_effect=DeviceUnregistered)
    def test_unregistered_token_is_removed(self, send, _configured):
        self.assertEqual(self.enroll().status_code, 204)
        self.assertEqual(self.dispatch().status_code, 410)
        with registry() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM devices").fetchone(), (0,))
        self.assertEqual(self.dispatch(event_id=str(uuid4())).status_code, 404)
        send.assert_called_once()

    @patch("vera_push.credentials_configured", return_value=True)
    @patch("vera_push.send_fcm", side_effect=TimeoutError)
    def test_ambiguous_timeout_preserves_duplicate_protection(self, send, _configured):
        self.assertEqual(self.enroll().status_code, 204)
        self.assertEqual(self.dispatch(task_id="task-1").status_code, 502)
        self.assertEqual(self.dispatch(task_id="task-1").status_code, 409)
        send.assert_called_once()
        self.assertEqual(send.call_args.args[1]["task_id"], "task-1")


if __name__ == "__main__":
    unittest.main()

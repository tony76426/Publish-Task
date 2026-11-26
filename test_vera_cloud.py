import logging
import time
from unittest import TestCase
from unittest.mock import Mock, patch
from uuid import uuid4

import test_vera_push
from vera_app import app, session
from vera_cloud import dispatch_due


class VeraCloudTest(TestCase):
    setUp = test_vera_push.VeraPushTest.setUp
    enroll = test_vera_push.VeraPushTest.enroll

    def call(self, **payload):
        return self.client.post("/api/cloud/calls", headers=self.auth, json={
            "device_id": self.device, "event_id": self.event, **payload,
        })

    def receipt(self, state, event=None, device=None):
        return self.client.put("/api/cloud/receipt", headers=self.auth, json={
            "device_id": device or self.device, "event_id": event or self.event, "state": state,
        })

    def status(self):
        return self.client.post("/api/cloud/status", headers=self.auth, json={"device_id": self.device}).json

    def context(self):
        return self.client.post("/api/cloud/context", headers=self.auth, json={
            "device_id": self.device, "event_id": self.event,
        })

    def test_cloud_api_is_private_and_fails_closed_without_sender(self):
        self.assertEqual(self.client.post("/api/cloud/status").status_code, 401)
        self.assertEqual(self.client.put("/api/cloud/receipt").status_code, 401)
        self.assertEqual(self.client.post("/api/cloud/context").status_code, 401)
        self.assertEqual(self.enroll().status_code, 204)
        self.assertEqual(self.call().status_code, 503)
        self.assertFalse(self.status()["credentials_configured"])
        self.assertEqual(self.status()["events"], [])

    @patch("vera_cloud.credentials_configured", return_value=True)
    @patch("vera_cloud.send_fcm")
    def test_schedule_fcm_and_reported_receipts(self, sender, _ready):
        self.assertEqual(self.enroll().status_code, 204)
        due = int(time.time()) + 60
        self.assertEqual(self.call(due=due, purpose="Private agenda", task_id="task-1").status_code, 202)
        self.assertEqual(self.call(due=due).status_code, 409)
        self.assertFalse(dispatch_due(logging.getLogger(), now=due-1))
        self.assertTrue(dispatch_due(logging.getLogger(), now=due))
        self.assertFalse(dispatch_due(logging.getLogger(), now=due))
        sender.assert_called_once()
        self.assertNotIn("Private agenda", str(sender.call_args))
        self.assertEqual(self.context().status_code, 404)
        self.assertEqual(self.receipt("received", device=str(uuid4())).status_code, 404)
        for state in ("received", "ringing", "accepted", "received"):
            self.assertEqual(self.receipt(state).status_code, 204)
        self.assertEqual(self.context().json["purpose"], "Private agenda")
        current = self.status()["events"][0]
        self.assertEqual(current["state"], "accepted")
        self.assertEqual([item["state"] for item in current["trail"]],
                         ["queued", "sending", "fcm_accepted", "received", "ringing", "accepted"])
        self.assertNotIn("Private agenda", str(current))

    @patch("vera_cloud.credentials_configured", return_value=True)
    @patch("vera_cloud.send_fcm")
    def test_cancel_and_expire_queued_calls(self, sender, _ready):
        self.enroll()
        now = int(time.time())
        self.assertEqual(self.call(due=now+30).status_code, 202)
        cancelled = self.client.delete("/api/cloud/calls", headers=self.auth, json={
            "device_id": self.device, "event_id": self.event,
        })
        self.assertEqual(cancelled.status_code, 200)
        self.event = str(uuid4())
        self.assertEqual(self.call(due=now+30).status_code, 202)
        self.assertFalse(dispatch_due(logging.getLogger(), now=now+200))
        sender.assert_not_called()
        states = {e["state"] for e in self.status()["events"]}
        self.assertEqual(states, {"cancelled", "failed"})

    @patch("vera_cloud.credentials_configured", return_value=True)
    @patch("vera_cloud.send_fcm")
    def test_only_one_retry_for_missed_calls_and_no_retry_for_test(self, sender, _ready):
        self.enroll()
        due = int(time.time())+30
        self.assertEqual(self.call(due=due, retry=True).status_code, 202)
        self.assertTrue(dispatch_due(logging.getLogger(), now=due))
        for _ in range(2):
            self.assertEqual(self.receipt("missed").status_code, 204)
        retries = [e for e in self.status()["events"] if e["retry_of"] == self.event]
        self.assertEqual(len(retries), 1)
        retry = retries[0]
        self.assertTrue(dispatch_due(logging.getLogger(), now=retry["due"]))
        self.assertEqual(self.receipt("missed", event=retry["event_id"]).status_code, 204)
        self.event = str(uuid4())
        self.assertEqual(self.call(due=due, test=True, retry=True).status_code, 202)
        self.assertTrue(dispatch_due(logging.getLogger(), now=due))
        self.assertEqual(self.receipt("missed").status_code, 204)
        self.assertEqual(sum(bool(e["retry_of"]) for e in self.status()["events"]), 1)
        self.assertEqual(sender.call_count, 3)

    @patch("vera_cloud.credentials_configured", return_value=True)
    @patch("vera_cloud.send_fcm")
    def test_device_revocation_prevents_scheduled_send(self, sender, _ready):
        self.enroll()
        due = int(time.time())+30
        self.assertEqual(self.call(due=due).status_code, 202)
        self.client.delete("/api/push/device", headers=self.auth, json={"device_id": self.device})
        self.assertTrue(dispatch_due(logging.getLogger(), now=due))
        sender.assert_not_called()
        self.assertEqual(self.status()["events"][0]["reason"], "device_unregistered")

    @patch("vera_cloud.credentials_configured", return_value=True)
    @patch("vera_cloud.send_fcm")
    def test_terminal_receipt_precedes_fcm_response_safely(self, sender, _ready):
        self.enroll()
        due = int(time.time())+30
        self.call(due=due)
        sender.side_effect = lambda _t, _d: self.receipt("declined")
        self.assertTrue(dispatch_due(logging.getLogger(), now=due))
        self.assertEqual(self.status()["events"][0]["state"], "declined")

    def test_cloud_voice_opens_with_reason(self):
        self.assertIn("聯繫原因", session("討論行程", source="cloud")["instructions"])
        self.assertNotIn("本次由 VERA 主動聯繫", session("手動通話")["instructions"])

    def test_latest_apk_only_links_expected_release(self):
        mock = Mock()
        mock.json.return_value = [
            {"tag_name": "wrong", "assets": [{"name": "VERA-Nexus.apk"}]},
            {"tag_name": "vera-nexus-v0.2.1-fcm-999-r1", "body": "Firebase client config absent.",
             "assets": [{"name": "VERA-Nexus.apk", "browser_download_url": "https://example.invalid/"}]},
        ]
        with patch("vera_app._apk_release", (0, None)), patch("vera_app.requests.get", return_value=mock):
            data = app.test_client().get("/api/apk/latest").json
        self.assertTrue(data["url"].startswith("https://github.com/tony76426/Publish-Task/"))
        self.assertFalse(data["android_firebase"])

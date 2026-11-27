import logging
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import test_vera_work
from vera_cloud import dispatch_due
from vera_work import work_db

TAIPEI = ZoneInfo("Asia/Taipei")
def ts(hour, minute=0):
    return int(datetime(2030, 1, 2, hour, minute, tzinfo=TAIPEI).timestamp())


class AutoCallTest(unittest.TestCase):
    setUp = test_vera_work.WorkTest.setUp
    submit = test_vera_work.WorkTest.submit
    enroll = test_vera_work.WorkTest.enroll
    source_base = "/api/v1/work"
    owner_base = "/api/v1/secretary"
    policy = owner_base + "/auto-call-policy"

    def configure(self, **overrides):
        return self.client.put(self.policy, headers=self.auth, json={
            "enabled":True, "consent":True, "device_id":self.device, "return_result":False, **overrides})

    def auto(self, task, due):
        with patch("vera_work.credentials_configured", return_value=True):
            return self.client.post(self.source_base+"/tasks/"+task["id"]+"/call",headers=self.source,json={"due_at":due})

    def test_opt_in_and_source_cannot_authorize(self):
        with patch("time.time", return_value=ts(8)):
            self.enroll()
            task=self.submit().json
            self.assertFalse(self.client.get(self.policy,headers=self.auth).json["enabled"])
            self.assertEqual(self.auto(task, ts(11)).status_code,403)
            self.assertEqual(self.client.put(self.policy,headers=self.source,json={"enabled":True}).status_code,401)
            self.assertEqual(self.configure(consent=False).status_code,400)
            self.assertEqual(self.configure().status_code,200)
            self.assertEqual(self.auto(task,ts(9,59)).status_code,400)
            self.assertEqual(self.auto(task,ts(23,59)).status_code,400)
            self.assertEqual(self.auto(task,ts(11)).status_code,202)

    def test_daily_limit_idempotency_and_disable_cancels_pending(self):
        with patch("time.time",return_value=ts(10)):
            self.enroll()
            self.assertEqual(self.configure().status_code,200)
            a,b,c=[self.submit("auto:"+str(i)).json for i in range(3)]
            first=self.auto(a,ts(11))
            self.assertEqual(first.status_code,202)
            self.assertEqual(self.auto(a,ts(11)).json["event_id"],first.json["event_id"])
            self.assertEqual(self.auto(a,ts(12)).status_code,409)
            self.assertEqual(self.auto(b,ts(15)).status_code,202)
            self.assertEqual(self.auto(c,ts(21)).status_code,429)
            self.assertEqual(self.configure(enabled=False).status_code,200)
            with work_db() as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM cloud_calls WHERE state='cancelled'").fetchone()[0],2)
            with patch("vera_cloud.send_fcm") as send:
                self.assertFalse(dispatch_due(logging.getLogger(),ts(11)))
                send.assert_not_called()

    def test_dispatch_enforces_consent_time_and_no_automatic_retry(self):
        with patch("time.time",return_value=ts(10)):
            self.enroll()
            self.assertEqual(self.configure().status_code,200)
            a=self.submit().json
            result=self.auto(a,ts(11))
            self.assertEqual(result.status_code,202)
            with work_db() as db:
                row=db.execute("SELECT retry FROM cloud_calls WHERE id=?",(result.json["event_id"],)).fetchone()
                self.assertEqual(row[0],0)
                self.assertEqual(db.execute("SELECT deliver FROM vera_work_links WHERE event=?",(result.json["event_id"],)).fetchone()[0],0)
            with patch("vera_cloud.credentials_configured",return_value=True), patch("vera_cloud.send_fcm") as send:
                self.assertTrue(dispatch_due(logging.getLogger(),ts(11)))
                self.assertEqual(send.call_count,1)
                self.assertNotIn("確認行程",str(send.call_args))
                self.assertFalse(dispatch_due(logging.getLogger(),ts(11)))

    def test_dispatch_suppresses_after_window_even_if_queued_due_was_valid(self):
        with patch("time.time",return_value=ts(10)):
            self.enroll()
            self.configure()
            a=self.submit().json
            event=self.auto(a,ts(23,58)).json["event_id"]
            # Dispatch can be delayed into the midnight safety margin but still within TTL.
            with work_db() as db:
                db.execute("UPDATE cloud_calls SET due=? WHERE id=?",(ts(23,59),event))
            with patch("vera_cloud.send_fcm") as send:
                self.assertTrue(dispatch_due(logging.getLogger(),ts(23,59)))
                send.assert_not_called()
            with work_db() as db:
                self.assertEqual(db.execute("SELECT state FROM cloud_calls WHERE id=?",(event,)).fetchone()[0],"cancelled")

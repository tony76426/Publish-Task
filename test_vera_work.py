import hashlib
import json
import logging
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

from cryptography.fernet import Fernet

import test_vera_push
from vera_app import app, session
from vera_cloud import dispatch_due
from vera_db_backup import snapshot, verify
from vera_release import release_info
from vera_work import cipher, process_summary, seal, work_db


class WorkTest(unittest.TestCase):
    owner_base = "/api/v1/secretary"
    source_base = "/api/v1/work"

    def setUp(self):
        test_vera_push.VeraPushTest.setUp(self)
        self.key = Fernet.generate_key().decode()
        self.source_token = "only-for-fixtures-not-a-production-credential"
        self.source = {"Authorization": "Bearer " + self.source_token}
        env = patch.dict(os.environ, {"VERA_DATA_KEY": self.key,
            "VERA_WORK_TOKEN_SHA256": hashlib.sha256(self.source_token.encode()).hexdigest(),
            "OPENAI_API_KEY": "mock-key"})
        env.start()
        self.addCleanup(env.stop)

    def submit(self, name="demo:task-1", **value):
        return self.client.post(self.source_base + "/tasks", headers=self.source,
                                json={"source_id": name, "title": "確認行程", "brief": "商議行程與備忘", **value})

    def enroll(self):
        self.assertEqual(test_vera_push.VeraPushTest.enroll(self).status_code, 204)

    def schedule(self, work, due, **overrides):
        with patch("vera_work.credentials_configured", return_value=True):
            return self.client.post(self.owner_base + "/tasks/" + work["id"] + "/call", headers=self.auth,
                json={"device_id":self.device, "event_id":self.event, "due_at":due,
                      "return_result":True, "retry":True, **overrides})

    def receive(self, state):
        return self.client.put("/api/cloud/receipt", headers=self.auth,
            json={"device_id":self.device, "event_id":self.event, "state":state})

    def fcm(self, due):
        with patch("vera_cloud.credentials_configured", return_value=True), patch("vera_cloud.send_fcm") as send:
            self.assertTrue(dispatch_due(logging.getLogger(), due))
            payload = send.call_args.args[1]
            self.assertNotIn("目的", str(payload))
            self.assertNotIn("確認行程", str(payload))

    def test_scoped_auth_conflict_and_idempotent_task_publish(self):
        self.assertEqual(self.client.get(self.source_base + "/tasks", headers=self.auth).status_code, 401)
        self.assertEqual(self.client.get(self.owner_base + "/tasks", headers=self.source).status_code, 401)
        first = self.submit()
        self.assertEqual(first.status_code, 201)
        task = first.json
        repeat = self.submit(title="忽略重送時的新增內容")
        self.assertEqual(repeat.status_code, 200)
        self.assertEqual(repeat.json, task)
        path = self.source_base + "/tasks/" + task["id"]
        updated = self.client.patch(path, headers=self.source, json={"revision":1, "title":"確認下一步"})
        self.assertEqual(updated.json["revision"], 2)
        self.assertEqual(self.client.patch(path, headers=self.source, json={"revision":1}).status_code, 409)
        file = Path(os.environ["VERA_PUSH_DB"]).read_bytes()
        self.assertNotIn("確認下一步".encode(), file)

    def test_end_to_end_summary_and_idempotent_consumer_cursor(self):
        self.enroll()
        task = self.submit().json
        due = int(time.time()) + 5
        self.assertEqual(self.schedule(task, due).status_code, 202)
        self.assertEqual(self.schedule(task, due).status_code, 202)
        self.fcm(due)
        self.assertEqual(self.receive("accepted").status_code, 204)
        context = self.client.post("/api/cloud/context", headers=self.auth,
                                   json={"device_id":self.device,"event_id":self.event})
        self.assertEqual(context.json["purpose"], "確認行程")
        self.assertEqual(context.json["work_context"], "商議行程與備忘")
        call = {
            "id":str(uuid4()), "device_id":self.device, "event_id":self.event, "topic":"確認行程",
            "rows":[{"role":"VERA","text":"需要調整行程嗎？"},{"role":"你","text":"明天保留上午的行程。"}],
        }
        route = self.owner_base + "/calls"
        self.assertEqual(self.client.post(route, headers=self.auth, json=call).status_code, 202)
        self.assertEqual(self.client.post(route, headers=self.auth, json=call).status_code, 200)
        self.assertFalse(self.client.get(self.source_base + "/results", headers=self.source).json["results"])
        result = {"summary":"保留上午行程","decisions":[{"text":"保留上午行程","evidence":"明天保留上午的行程"}],
                  "instructions":[{"text":"虛構指示","evidence":"使用者從未說過的內容"}]}
        upstream = Mock()
        upstream.json.return_value = {"output":[{"type":"message","content":[
            {"type":"output_text","text":json.dumps(result)}]}]}
        with patch("vera_work.requests.post", return_value=upstream) as summarize:
            self.assertTrue(process_summary(logging.getLogger(), due + 1))
            self.assertFalse(process_summary(logging.getLogger(), due + 1))
            self.assertEqual(summarize.call_count, 1)
            self.assertEqual(summarize.call_args.kwargs["json"]["text"]["format"]["type"], "json_schema")
        call_data = self.client.get(route + "/" + call["id"], headers=self.auth).json
        self.assertEqual(call_data["state"], "ready")
        self.assertEqual(call_data["result"]["instructions"], [])
        self.assertEqual(call_data["rows"], call["rows"])
        results = self.source_base + "/results"
        first = self.client.get(results + "?after=0", headers=self.source).json
        self.assertEqual(first["results"][0]["decisions"], ["保留上午行程"])
        self.assertNotIn("rows", first["results"][0])
        self.assertNotIn("summary", first["results"][0])
        self.assertEqual(self.client.get(results + "?after=0", headers=self.source).json, first)
        self.assertFalse(self.client.get(results + "?after=" + str(first["next_cursor"]), headers=self.source).json["results"])

    def test_cancel_includes_scheduled_retry(self):
        self.enroll()
        task = self.submit().json
        due = int(time.time()) + 5
        self.assertEqual(self.schedule(task, due).status_code, 202)
        self.fcm(due)
        self.assertEqual(self.receive("missed").status_code, 204)
        path = self.source_base + "/tasks/" + task["id"]
        self.assertEqual(self.client.delete(path, headers=self.source, json={"revision":2}).json["state"], "cancelled")
        status = self.client.post("/api/cloud/status", headers=self.auth, json={"device_id":self.device})
        retry = next(row for row in status.json["events"] if row["retry_of"])
        self.assertEqual(retry["state"], "cancelled")

    def test_opt_out_from_result_and_empty_transcript(self):
        self.enroll()
        work = self.submit().json
        due = int(time.time()) + 3
        self.assertEqual(self.schedule(work, due, return_result=False).status_code, 202)
        self.fcm(due)
        self.assertEqual(self.receive("accepted").status_code, 204)
        body = {"id":str(uuid4()),"event_id":self.event,"device_id":self.device,"topic":"確認行程","rows":[]}
        response = self.client.post(self.owner_base + "/calls", headers=self.auth, json=body)
        self.assertEqual(response.json["state"], "ready")
        self.assertFalse(process_summary(logging.getLogger(), due + 1))
        self.assertFalse(self.client.get(self.source_base + "/results", headers=self.source).json["results"])

    def test_old_sqlite_snapshot_and_additive_migration(self):
        self.enroll()
        due = int(time.time()) + 10
        with patch("vera_cloud.credentials_configured", return_value=True):
            self.assertEqual(self.client.post("/api/cloud/calls", headers=self.auth,
                json={"device_id":self.device, "event_id":self.event, "due":due, "purpose":"舊版來電"}).status_code, 202)
        path = Path(os.environ["VERA_PUSH_DB"])
        old, restored = path.with_name("old.sqlite3"), path.with_name("restored.sqlite3")
        initial = snapshot(path, old)
        self.assertEqual(initial["devices"], 1)
        self.assertEqual(initial["cloud_calls"], 1)
        self.assertEqual(self.submit().status_code, 201)
        self.assertEqual(verify(path), initial)
        self.assertEqual(snapshot(old, restored), initial)
        with patch.dict(os.environ, {"VERA_PUSH_DB": str(restored)}):
            self.fcm(due)
            self.assertEqual(self.receive("accepted").status_code, 204)
            response = self.client.post("/api/cloud/context", headers=self.auth,
                                        json={"device_id":self.device, "event_id":self.event})
            self.assertEqual(response.json, {"purpose":"舊版來電","task_id":"","test":False})

    def test_memory_backup_and_authenticated_merge(self):
        memory = self.owner_base + "/memory"
        record = {"id":str(uuid4()), "kind":"decision", "project":"行程", "title":"待決定",
                  "note":"行程內容"}
        self.assertEqual(self.client.post(memory, headers=self.auth, json=record).status_code, 200)
        backup = self.owner_base + "/backup"
        saved = self.client.get(backup, headers=self.auth).json
        self.assertNotIn("行程內容", saved["archive"])
        item = memory + "/" + record["id"]
        self.assertEqual(self.client.delete(item, headers=self.auth, json={"revision":1}).status_code, 204)
        self.assertEqual(self.client.post(backup, headers=self.auth, json=saved).json["imported"], 1)
        self.assertEqual(self.client.post(backup, headers=self.auth, json=saved).json["imported"], 0)
        self.assertEqual(self.client.get(memory, headers=self.auth).json["entries"][0]["note"], "行程內容")
        with patch.dict(os.environ, {"VERA_DATA_KEY": Fernet.generate_key().decode()}):
            self.assertEqual(self.client.post(backup, headers=self.auth, json=saved).status_code, 400)

    def test_upgrade_rejects_mismatched_certificate(self):
        sha, fingerprint = "a"*64, "b"*64
        listing = Mock()
        listing.json.return_value = [{"tag_name":"vera-nexus-v0.3.0-fcm-32-r1", "assets":[
            {"name":"vera-release.json","size":190},{"name":"VERA-Nexus.apk","digest":"sha256:"+sha}]}]
        metadata = Mock(content=b"{}")
        metadata.json.return_value = {"package":"tw.vera.nexus", "version":"0.3.0",
            "version_code":10, "firebase":True, "signer_sha256":fingerprint, "apk_sha256":sha}
        with patch("vera_release.requests.get", side_effect=[listing,metadata]):
            self.assertFalse(release_info("c"*64)["available"])
        with patch("vera_release.requests.get", side_effect=[listing,metadata]):
            self.assertEqual(release_info(fingerprint)["version_code"], 10)

    def test_separate_model_defaults_and_realtime_route(self):
        self.assertEqual(session()["model"], os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime"))
        self.assertEqual(session(secretary=True)["model"], "gpt-realtime-2.1")
        self.assertEqual(session(secretary=True)["audio"]["input"]["transcription"]["model"], "gpt-transcribe")
        mock = Mock(ok=True, text="v=0\r\n")
        with patch("vera_app.requests.post", return_value=mock) as upstream:
            result = self.client.post(self.owner_base + "/realtime", headers=self.auth,
                                      json={"sdp":"v=0\r\n","source":"cloud","work_context":"測試工作"})
            self.assertEqual(result.json["model"], "gpt-realtime-2.1")
            self.assertIn("測試工作", upstream.call_args.kwargs["files"]["session"][1])

    def test_ui_routes_preserve_legacy_home(self):
        with self.client.get("/app") as old, self.client.get("/app/v3") as current:
            self.assertNotIn(b'/assets/vera-v3.js', old.data)
            self.assertIn(b'/assets/vera-v3.js', current.data)
            self.assertIn(b'class="secretary"', current.data)
        with self.client.get("/assets/vera-v3.css") as stylesheet:
            self.assertEqual(stylesheet.status_code, 200)

    def test_work_inbox_resumes_after_restart_and_rejects_skipped_results(self):
        task = self.submit().json
        now = int(time.time())
        with work_db() as db:
            for cursor in (3, 6, 9):
                db.execute("""INSERT INTO vera_work_results(cursor,task,call,created,body)
                              VALUES(?,?,?,?,?)""",
                           (cursor, task["id"], str(uuid4()), now,
                            seal(cipher(), {"decisions": ["同意測試"], "instructions": [], "status": "awaiting_chatgpt"})))
        path = self.source_base + "/inbox/work-qa"
        initial = self.client.get(path, headers=self.source).json
        self.assertEqual([row["cursor"] for row in initial["results"]], [3, 6, 9])
        self.assertEqual(self.client.put(path, headers=self.source, json={"after":0,"cursors":[6]}).status_code, 409)
        first = self.client.put(path, headers=self.source, json={"after":0,"cursors":[3,6]})
        self.assertEqual(first.json, {"consumer":"work-qa","acknowledged":6,"replayed":False})
        other_request = app.test_client()
        retry = other_request.put(path, headers=self.source, json={"after":0,"cursors":[3,6]})
        self.assertTrue(retry.json["replayed"])
        self.assertEqual(other_request.put(path, headers=self.source, json={"after":0,"cursors":[3]}).status_code, 409)
        result = other_request.get(path, headers=self.source).json
        self.assertEqual([row["cursor"] for row in result["results"]], [9])
        self.assertEqual(other_request.put(path, headers=self.source, json={"after":6,"cursors":[9]}).json["acknowledged"],9)
        self.assertEqual(other_request.get(path, headers=self.source).json["results"], [])
        untouched = self.client.get(self.source_base+"/inbox/other",headers=self.source).json
        self.assertEqual(untouched["acknowledged"],0)
        self.assertEqual(self.client.get(path,headers=self.auth).status_code,401)


if __name__ == "__main__":
    unittest.main()

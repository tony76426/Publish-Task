import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vera_db_backup import verify
from vera_release_gate import rehearse_migration, production_release_gate, RELEASE_CHECKPOINT


class ReleaseGateTest(unittest.TestCase):
    def test_migration_preserves_original_and_rollback_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = Path(tmp) / "db.sqlite3"
            backups = Path(tmp) / "backups"
            with sqlite3.connect(original) as db:
                for name in ("devices", "dispatch", "cloud_calls", "cloud_call_history"):
                    db.execute("CREATE TABLE " + name + " (id INTEGER PRIMARY KEY)")
                    db.execute("INSERT INTO " + name + " VALUES(1)")
            before = original.read_bytes()
            self.assertEqual(rehearse_migration(original, backups), "created")
            self.assertEqual(original.read_bytes(), before)
            self.assertEqual(verify(backups / RELEASE_CHECKPOINT), verify(original))
            self.assertEqual(rehearse_migration(original, backups), "existing")
            self.assertEqual(list(backups.iterdir()), [backups / RELEASE_CHECKPOINT])

    def test_gate_fails_before_database_access_without_key(self):
        with patch.dict("os.environ", {"VERA_PUSH_DB": "/var/data/vera-push.sqlite3"}, clear=True):
            with patch("vera_release_gate.rehearse_migration") as rehearsal:
                with self.assertRaises(KeyError):
                    production_release_gate()
                rehearsal.assert_not_called()

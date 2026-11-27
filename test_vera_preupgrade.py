import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vera_db_backup import verify
from vera_preupgrade import checkpoint, production_checkpoint


class PreupgradeCheckpointTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.src = Path(self.tmp.name) / "source.sqlite3"
        self.dest = Path(self.tmp.name) / "private"
        with sqlite3.connect(self.src) as conn:
            for name in ("devices", "dispatch", "cloud_calls", "cloud_call_history"):
                conn.execute("CREATE TABLE " + name + " (id INTEGER PRIMARY KEY)")
                conn.execute("INSERT INTO " + name + " VALUES (1)")

    def test_copy_is_consistent_and_existing_copy_is_not_overwritten(self):
        self.assertEqual(checkpoint(self.src, self.dest), "created")
        target = next(self.dest.iterdir())
        saved = target.read_bytes()
        self.assertEqual(verify(target)["devices"], 1)
        with sqlite3.connect(self.src) as conn:
            conn.execute("INSERT INTO devices VALUES (2)")
        self.assertEqual(checkpoint(self.src, self.dest), "existing")
        self.assertEqual(target.read_bytes(), saved)
        self.assertEqual(verify(self.src)["devices"], 2)

    def test_rejects_insecure_backup_directory(self):
        self.dest.mkdir(mode=0o755)
        with self.assertRaises(ValueError):
            checkpoint(self.src, self.dest)

    def test_missing_production_configuration_does_not_change_database(self):
        with patch.dict(os.environ, {"VERA_PUSH_DB": str(self.src)}):
            self.assertFalse(production_checkpoint())
        self.assertEqual(verify(self.src)["devices"], 1)

    def test_corrupt_existing_checkpoint_is_not_overwritten(self):
        self.dest.mkdir(mode=0o700)
        target = self.dest / "pre-v030-52c9a3c.sqlite3"
        target.write_bytes(b"not a database")
        target.chmod(0o600)
        with self.assertRaises(Exception):
            checkpoint(self.src, self.dest)
        self.assertEqual(target.read_bytes(), b"not a database")

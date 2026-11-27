"""Verify a protected rollback copy and rehearse the v0.3 schema before startup."""
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from cryptography.fernet import Fernet
from vera_db_backup import snapshot, verify
from vera_preupgrade import checkpoint, PRODUCTION_DB, CHECKPOINT_DIR
from vera_work import migrate

RELEASE_CHECKPOINT = "pre-v030-first-release.sqlite3"


def rehearse_migration(source, directory):
    source = Path(source)
    directory = Path(directory)
    status = checkpoint(source, directory, name=RELEASE_CHECKPOINT)
    saved = directory / RELEASE_CHECKPOINT
    before = verify(saved)
    with tempfile.TemporaryDirectory(prefix="rehearse-", dir=directory) as tmp:
        copy = Path(tmp) / "rehearsal.sqlite3"
        snapshot(saved, copy)
        with closing(sqlite3.connect(copy)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            migrate(db)
            if db.execute("SELECT version FROM vera_work_schema").fetchone() != (1,):
                raise RuntimeError("Migration schema version mismatch")
        if verify(copy) != before or verify(saved) != before:
            raise RuntimeError("Existing table counts changed during rehearsal")
    return status


def production_release_gate():
    if os.getenv("VERA_PUSH_DB") != str(PRODUCTION_DB):
        raise ValueError("Unexpected persistent database path")
    # Validate the secret without emitting it, before loading the app.
    Fernet(os.environ["VERA_DATA_KEY"].encode("ascii"))
    status = rehearse_migration(PRODUCTION_DB, CHECKPOINT_DIR)
    print("VERA v0.3 release gate: " + status + "; SQLite integrity OK; migration rehearsal OK", flush=True)

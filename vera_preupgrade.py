"""Create a local, verified rollback checkpoint before any v0.3 migration."""
import os
import shutil
import stat
from pathlib import Path

from vera_db_backup import snapshot, verify

PRODUCTION_DB = Path("/var/data/vera-push.sqlite3")
CHECKPOINT_DIR = Path("/var/data/vera-upgrade-backups")
CHECKPOINT_NAME = "pre-v030-52c9a3c.sqlite3"


def checkpoint(source, directory, name=CHECKPOINT_NAME):
    source = Path(source).resolve(strict=True)
    directory = Path(directory)
    directory.mkdir(mode=0o700, exist_ok=True)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Unsafe backup directory")
    if stat.S_IMODE(directory.stat().st_mode) & 0o077:
        raise ValueError("Backup directory permissions are too broad")
    target = directory / name
    if target.is_symlink():
        raise ValueError("Unsafe backup path")
    if target.exists():
        if not target.is_file() or stat.S_IMODE(target.stat().st_mode) & 0o077:
            raise ValueError("Unsafe existing checkpoint")
        verify(target)
        return "existing"
    wal = source.with_name(source.name + "-wal")
    size = source.stat().st_size + (wal.stat().st_size if wal.exists() else 0)
    if shutil.disk_usage(directory).free < size * 2 + 16 * 1024 * 1024:
        raise RuntimeError("Insufficient disk space for checkpoint")
    snapshot(source, target)
    verify(target)
    return "created"


def production_checkpoint():
    """Leave the existing v0.2.1 app running even when a checkpoint fails."""
    try:
        if os.getenv("VERA_PUSH_DB") != str(PRODUCTION_DB):
            raise ValueError("Unexpected production database path")
        result = checkpoint(PRODUCTION_DB, CHECKPOINT_DIR)
        print("VERA pre-v030 checkpoint: " + result + "; SQLite integrity OK", flush=True)
        return True
    except Exception as exc:
        # No database content, credentials, or paths in app logs.
        print("VERA pre-v030 checkpoint: FAILED (" + type(exc).__name__ + ")", flush=True)
        return False

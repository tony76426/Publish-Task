"""Create or restore a consistent SQLite copy without overwriting a database."""

import argparse
import os
import sqlite3
from contextlib import closing
from pathlib import Path

TABLES = frozenset({"devices", "dispatch", "cloud_calls", "cloud_call_history"})


def verify(path):
    uri = Path(path).resolve(strict=True).as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as db:
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("SQLite integrity check failed")
        tables = {name for name, in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not TABLES <= tables:
            raise ValueError("File is not the VERA push database")
        return {name: db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                for name in sorted(TABLES)}


def snapshot(source, destination):
    uri = Path(source).resolve(strict=True).as_uri() + "?mode=ro"
    destination = Path(destination).resolve()
    # Never replace an existing database or leave an unchecked backup in place.
    os.close(os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    try:
        with closing(sqlite3.connect(uri, uri=True)) as original, closing(sqlite3.connect(destination)) as copy:
            original.backup(copy, pages=128, sleep=0.05)
        return verify(destination)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    parser.add_argument("destination", nargs="?")
    args = parser.parse_args()
    counts = snapshot(args.source, args.destination) if args.destination else verify(args.source)
    print("SQLite integrity OK. " + ", ".join(f"{name}={count}" for name, count in counts.items()))


if __name__ == "__main__":
    main()

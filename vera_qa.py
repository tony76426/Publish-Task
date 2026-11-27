"""Run a separate loopback backend with the production scheduling code for USB QA."""

import argparse
import os
from pathlib import Path
from threading import Event, Thread

from werkzeug.serving import run_simple

from vera_app import app
from vera_cloud import run_scheduler
from vera_work import run_summary_worker


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path, help="Separate local QA SQLite database")
    parser.add_argument("--port", type=int, default=18730)
    settings = parser.parse_args()
    db = settings.db.resolve()
    if not db.name.endswith(".qa.sqlite3"):
        parser.error("Use a separate file ending in .qa.sqlite3")
    if not 1024 <= settings.port <= 65535:
        parser.error("Port must be between 1024 and 65535")
    os.environ["VERA_PUSH_DB"] = str(db)
    stop = Event()
    for target in (run_scheduler, run_summary_worker):
        Thread(target=target, args=(stop, app.logger), daemon=True).start()
    try:
        run_simple("127.0.0.1", settings.port, app, threaded=True, use_reloader=False, use_debugger=False)
    finally:
        stop.set()


if __name__ == "__main__":
    main()

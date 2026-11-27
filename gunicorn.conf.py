from threading import Event, Thread

from vera_cloud import run_scheduler
from vera_work import run_summary_worker


def post_worker_init(worker):
    worker.vera_scheduler_stop = Event()
    Thread(target=run_scheduler, args=(worker.vera_scheduler_stop, worker.log),
           name="vera-cloud-scheduler", daemon=True).start()
    Thread(target=run_summary_worker, args=(worker.vera_scheduler_stop, worker.log),
           name="vera-summary-worker", daemon=True).start()
    worker.log.info("VERA cloud call scheduler started")


def worker_exit(server, worker):
    stop = getattr(worker, "vera_scheduler_stop", None)
    if stop is not None:
        stop.set()

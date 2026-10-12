"""In-process job queue with crash recovery and retention purge.

For horizontal scale, replace JobQueue with a broker-backed implementation
(Azure Service Bus, RabbitMQ, Redis) and run `python -m app.worker` in separate,
sandboxed worker containers — the `process()` contract is unchanged.
"""
import logging
import queue
import threading
from datetime import timedelta

from sqlalchemy import select

from . import storage
from .config import get_settings
from .db import SessionLocal
from .models import Analysis, MediaObject, utcnow
from .pipeline import process

log = logging.getLogger("deepshield.worker")


class JobQueue:
    def __init__(self, threads: int):
        self.q: queue.Queue[str | None] = queue.Queue()
        self.threads = threads
        self._workers: list[threading.Thread] = []
        self._stop = threading.Event()

    def start(self) -> None:
        if self._workers:
            return
        self._stop.clear()
        for i in range(self.threads):
            t = threading.Thread(target=self._loop, name=f"ds-worker-{i}", daemon=True)
            t.start()
            self._workers.append(t)
        threading.Thread(target=self._janitor, name="ds-janitor", daemon=True).start()
        self.recover()

    def stop(self) -> None:
        self._stop.set()
        for _ in self._workers:
            self.q.put(None)
        for t in self._workers:
            t.join(timeout=5)
        self._workers.clear()

    def enqueue(self, analysis_id: str) -> None:
        self.q.put(analysis_id)

    def wait_idle(self, timeout: float = 60) -> bool:
        done = threading.Event()

        def waiter():
            self.q.join()
            done.set()
        threading.Thread(target=waiter, daemon=True).start()
        return done.wait(timeout)

    def recover(self) -> None:
        """Re-queue jobs that were pending when the process last stopped."""
        with SessionLocal() as db:
            ids = db.scalars(select(Analysis.id).where(Analysis.status.in_(("queued", "running")))).all()
            for a in db.scalars(select(Analysis).where(Analysis.status == "running")):
                a.status = "queued"
            db.commit()
        for i in ids:
            self.enqueue(i)

    def _loop(self) -> None:
        while not self._stop.is_set():
            job = self.q.get()
            try:
                if job is None:
                    return
                process(job, enqueue=self.enqueue)
            except Exception:
                log.exception("worker failure")
            finally:
                self.q.task_done()

    def _janitor(self) -> None:
        while not self._stop.wait(600):
            try:
                purge_expired()
            except Exception:
                log.exception("retention purge failed")


def purge_expired() -> int:
    """Delete original media older than the retention window. Analysis records and
    derived evidence stay until the user deletes them."""
    cutoff = utcnow() - timedelta(hours=get_settings().retention_hours)
    n = 0
    with SessionLocal() as db:
        for m in db.scalars(select(MediaObject).where(MediaObject.purged_at.is_(None), MediaObject.created_at < cutoff)):
            pending = db.scalar(select(Analysis.id).where(Analysis.media_id == m.id,
                                                          Analysis.status.in_(("queued", "running"))))
            if pending:
                continue
            storage.delete_original(m.storage_path)
            m.storage_path, m.purged_at = None, utcnow()
            n += 1
        db.commit()
    if n:
        log.info("purged %d originals past retention", n)
    return n


jobs = JobQueue(get_settings().worker_threads)

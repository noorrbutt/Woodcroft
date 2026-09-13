"""The background worker.

No Redis, no Celery, no broker of any kind is available here, so jobs live in
the ``job_queue`` table and this worker polls it. That sounds fragile but is
not, because the claim is a single atomic statement:

    UPDATE job_queue SET status='claimed' ... WHERE id IN (
        SELECT id FROM job_queue WHERE status='pending' ...
        FOR UPDATE SKIP LOCKED LIMIT n
    ) RETURNING *

``FOR UPDATE SKIP LOCKED`` means two workers racing for the same row simply do
not collide; one takes it, the other moves to the next. So a job runs exactly
once even if this is ever scaled to several processes.

Failures retry with exponential backoff by pushing ``run_after`` forward, and a
job that exhausts ``max_attempts`` is parked as failed for an admin to look at
rather than retried forever.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.enums import JobStatus
from app.models.ops import JobQueue

log = logging.getLogger("woodcroft.worker")

#: job_type -> handler. Handlers take (db, payload) and must be idempotent:
#: a crash between doing the work and marking the job done means it runs again.
HANDLERS: dict[str, Callable[[Session, dict[str, Any]], None]] = {}

WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"
BATCH_SIZE = 5
#: A claimed job whose worker died is reclaimed after this long.
LEASE_MINUTES = 10


def handler(job_type: str) -> Callable:
    """Register a job handler."""

    def decorator(fn: Callable[[Session, dict[str, Any]], None]):
        HANDLERS[job_type] = fn
        return fn

    return decorator


def enqueue(
    db: Session,
    job_type: str,
    payload: dict[str, Any] | None = None,
    *,
    run_after: datetime | None = None,
    priority: int = 100,
    dedupe_key: str | None = None,
    max_attempts: int = 3,
) -> JobQueue | None:
    """Schedule a job.

    Returns None when ``dedupe_key`` matches a job already pending or claimed,
    which is how "one reminder per cart" is enforced without a separate table.
    """
    if dedupe_key:
        existing = db.scalar(
            select(JobQueue.id).where(
                JobQueue.dedupe_key == dedupe_key,
                JobQueue.status.in_([JobStatus.PENDING, JobStatus.CLAIMED]),
            )
        )
        if existing:
            return None

    job = JobQueue(
        job_type=job_type,
        payload=payload or {},
        run_after=run_after or datetime.now(UTC),
        priority=priority,
        dedupe_key=dedupe_key,
        max_attempts=max_attempts,
    )
    db.add(job)
    return job


CLAIM_SQL = text(
    """
    UPDATE job_queue SET
        status = 'claimed',
        claimed_at = now(),
        claimed_by = :worker,
        attempts = attempts + 1
    WHERE id IN (
        SELECT id FROM job_queue
        WHERE (status = 'pending' AND run_after <= now())
           OR (status = 'claimed' AND claimed_at < now() - make_interval(mins => :lease))
        ORDER BY priority ASC, run_after ASC
        FOR UPDATE SKIP LOCKED
        LIMIT :batch
    )
    RETURNING id
    """
)


def claim_batch(db: Session) -> list[JobQueue]:
    """Atomically take up to BATCH_SIZE runnable jobs."""
    ids = db.execute(
        CLAIM_SQL,
        {"worker": WORKER_ID, "batch": BATCH_SIZE, "lease": LEASE_MINUTES},
    ).scalars().all()
    db.commit()

    if not ids:
        return []
    return list(db.scalars(select(JobQueue).where(JobQueue.id.in_(ids))).all())


def _backoff(attempts: int) -> timedelta:
    """1 min, then 5, then 25. Enough to ride out a transient failure."""
    return timedelta(minutes=min(60, 5 ** max(0, attempts - 1)))


def run_job(db: Session, job: JobQueue) -> None:
    fn = HANDLERS.get(job.job_type)
    if fn is None:
        job.status = JobStatus.FAILED
        job.last_error = f"No handler registered for '{job.job_type}'"
        job.completed_at = datetime.now(UTC)
        return

    try:
        fn(db, job.payload or {})
        job.status = JobStatus.SUCCEEDED
        job.completed_at = datetime.now(UTC)
        job.last_error = None
    except Exception as exc:
        db.rollback()
        # Re-read: the rollback detached our changes to the row.
        fresh = db.get(JobQueue, job.id)
        if fresh is None:
            return
        fresh.last_error = f"{type(exc).__name__}: {exc}"
        if fresh.attempts >= fresh.max_attempts:
            fresh.status = JobStatus.FAILED
            fresh.completed_at = datetime.now(UTC)
            log.error("job %s (%s) failed permanently: %s", fresh.id, fresh.job_type, exc)
        else:
            fresh.status = JobStatus.PENDING
            fresh.run_after = datetime.now(UTC) + _backoff(fresh.attempts)
            fresh.claimed_at = None
            fresh.claimed_by = None
            log.warning("job %s (%s) failed, will retry: %s", fresh.id, fresh.job_type, exc)


def tick() -> int:
    """Run one polling cycle. Returns how many jobs were processed."""
    db = SessionLocal()
    try:
        jobs = claim_batch(db)
        for job in jobs:
            run_job(db, job)
            db.commit()
        return len(jobs)
    finally:
        db.close()


async def run_worker() -> None:
    """Poll forever. Cancelled by the app lifespan on shutdown."""
    # Import for the side effect of registering every handler.
    from app.workers import jobs  # noqa: F401

    log.info("worker %s polling every %ss", WORKER_ID, settings.WORKER_POLL_SECONDS)

    while True:
        try:
            processed = await asyncio.to_thread(tick)
            # Drain a backlog quickly instead of sleeping between each batch.
            if processed == BATCH_SIZE:
                continue
        except asyncio.CancelledError:
            raise
        except Exception:
            # The worker must survive anything, including the database being
            # briefly unreachable. Log and keep polling.
            log.exception("worker tick failed")

        await asyncio.sleep(settings.WORKER_POLL_SECONDS)

"""Background jobs stored in Postgres (app.job), run by a worker loop inside the API process.

Add a job kind:

    @handler("transcribe_audio")
    async def transcribe(ctx: JobContext) -> dict:
        await ctx.progress(50)
        return {"transcript_id": "..."}

then `await enqueue(db, ws, user_id, "transcribe_audio", {...})` from a route.

A running job beats (`job.updated_at`) every `JOB_HEARTBEAT_SECONDS`. On startup, and every minute
in the worker loop, running jobs whose heartbeat is older than `JOB_STALE_SECONDS` (their process
died) go back to the queue; a job already claimed `JOB_MAX_ATTEMPTS` times fails instead, with an
error that says so. A failed job is never retried by itself; « Relancer » resets its attempts.
"""

import asyncio
import logging
import traceback
import uuid
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.models import Job
from app.realtime.server import emit

log = logging.getLogger("checky.jobs")

POLL_SECONDS = 2.0
SWEEP_SECONDS = 60.0
_wake = asyncio.Event()


@dataclass
class JobContext:
    job_id: uuid.UUID
    workspace_id: uuid.UUID
    created_by: str
    input: dict[str, Any]

    async def progress(self, percent: int) -> None:
        percent = max(0, min(100, int(percent)))
        async with SessionLocal() as db:
            await db.execute(update(Job).where(Job.id == self.job_id).values(progress=percent))
            await db.commit()
        await emit(self.workspace_id, "job.progress", {"id": str(self.job_id), "progress": percent})


Handler = Callable[[JobContext], Awaitable[dict[str, Any] | None]]
HANDLERS: dict[str, Handler] = {}


def handler(kind: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        HANDLERS[kind] = fn
        return fn

    return register


def job_payload(job: Job) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "kind": job.kind,
        "status": job.status,
        "progress": job.progress,
        "result": job.result,
        "error": job.error,
    }


async def enqueue(
    db: AsyncSession, ws: uuid.UUID, user_id: str, kind: str, input: dict[str, Any]
) -> Job:
    if kind not in HANDLERS:
        raise ValueError(f"Unknown job kind: {kind}")
    job = Job(workspace_id=ws, created_by=user_id, kind=kind, input=input)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    _wake.set()
    return job


_CLAIM = text(
    """
    UPDATE app.job SET status = 'running', attempts = attempts + 1,
           started_at = now(), updated_at = now()
    WHERE id = (
        SELECT id FROM app.job WHERE status = 'queued'
        ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1
    )
    RETURNING id
    """
)


async def run_once() -> bool:
    """Claim and run one queued job. Returns False when the queue is empty."""
    async with SessionLocal() as db:
        job_id = await db.scalar(_CLAIM)
        await db.commit()
        if job_id is None:
            return False
        job = await db.get(Job, job_id)
        ctx = JobContext(job.id, job.workspace_id, job.created_by, dict(job.input))
        kind = job.kind

    beat = asyncio.create_task(_heartbeat(job_id))
    try:
        result = await HANDLERS[kind](ctx)
        values = {"status": "done", "progress": 100, "result": result or {}, "error": None}
        event = "job.done"
    except Exception as e:  # noqa: BLE001 - a failing job must never kill the worker
        log.warning("job %s (%s) failed: %s", job_id, kind, e)
        values = {"status": "failed", "error": f"{type(e).__name__}: {e}"}
        log.debug(traceback.format_exc())
        event = "job.failed"
    finally:
        beat.cancel()
        with suppress(asyncio.CancelledError):
            await beat

    async with SessionLocal() as db:
        await db.execute(
            update(Job).where(Job.id == job_id).values(**values, finished_at=datetime.now(UTC))
        )
        await db.commit()
        job = await db.get(Job, job_id)
    await emit(ctx.workspace_id, event, job_payload(job))
    return True


async def _heartbeat(job_id: uuid.UUID) -> None:
    """Refresh `updated_at` while the job runs, so no other process takes it back."""
    every = get_settings().job_heartbeat_seconds
    while True:
        await asyncio.sleep(every)
        try:
            async with SessionLocal() as db:
                await db.execute(
                    update(Job)
                    .where(Job.id == job_id, Job.status == "running")
                    .values(updated_at=datetime.now(UTC))
                )
                await db.commit()
        except Exception:  # noqa: BLE001 - a missed beat only makes the job look stale sooner
            log.warning("heartbeat of job %s failed", job_id)


async def requeue_interrupted() -> int:
    """Running jobs whose heartbeat stopped (a crash, a Render spin-down) go back to the queue.

    Jobs still beating belong to a live process and are left alone. One that has already been
    claimed `JOB_MAX_ATTEMPTS` times fails with a clear error instead of being run again.
    Returns how many were requeued.
    """
    s = get_settings()
    stale = datetime.now(UTC) - timedelta(seconds=s.job_stale_seconds)
    running = (Job.status == "running", Job.updated_at < stale)
    async with SessionLocal() as db:
        await db.execute(
            update(Job)
            .where(*running, Job.attempts >= s.job_max_attempts)
            .values(
                status="failed",
                error=f"Interrupted {s.job_max_attempts} times; not run again "
                "(raise JOB_MAX_ATTEMPTS or retry it by hand)",
                finished_at=datetime.now(UTC),
            )
        )
        res = await db.execute(
            update(Job)
            .where(*running, Job.attempts < s.job_max_attempts)
            .values(status="queued", progress=0)
        )
        await db.commit()
        if res.rowcount:
            _wake.set()
        return res.rowcount


async def worker_loop() -> None:
    loop = asyncio.get_running_loop()
    swept = loop.time()
    while True:
        try:
            if loop.time() - swept > SWEEP_SECONDS:
                swept = loop.time()
                await requeue_interrupted()
            while await run_once():
                pass
        except Exception:
            log.exception("worker loop error")
        _wake.clear()
        try:
            await asyncio.wait_for(_wake.wait(), POLL_SECONDS)
        except TimeoutError:
            pass


async def get_job(db: AsyncSession, ws: uuid.UUID, job_id: uuid.UUID) -> Job | None:
    return await db.scalar(select(Job).where(Job.id == job_id, Job.workspace_id == ws))

import asyncio
import uuid

import pytest

from app.core.db import SessionLocal
from app.workers import queue
from tests.test_workspaces import _workspace

calls: list[str] = []


@queue.handler("test_ok")
async def _ok(ctx: queue.JobContext) -> dict:
    await ctx.progress(50)
    calls.append(ctx.input["n"])
    return {"echo": ctx.input["n"]}


@queue.handler("test_fail")
async def _fail(ctx: queue.JobContext) -> dict:
    if ctx.input.get("fixed"):
        return {"ok": True}
    raise RuntimeError("provider timeout")


def _enqueue(ws: str, kind: str, payload: dict) -> str:
    async def go():
        async with SessionLocal() as db:
            return str((await queue.enqueue(db, uuid.UUID(ws), "alice", kind, payload)).id)

    return asyncio.run(go())


def test_job_runs_to_done(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    job_id = _enqueue(ws, "test_ok", {"n": "a"})
    assert alice.get(f"/api/v1/workspaces/{ws}/jobs/{job_id}").json()["status"] == "queued"
    assert asyncio.run(queue.run_once()) is True
    job = alice.get(f"/api/v1/workspaces/{ws}/jobs/{job_id}").json()
    assert (job["status"], job["progress"], job["result"]) == ("done", 100, {"echo": "a"})
    assert asyncio.run(queue.run_once()) is False


def test_failure_is_recorded_and_retryable(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    job_id = _enqueue(ws, "test_fail", {})
    asyncio.run(queue.run_once())
    url = f"/api/v1/workspaces/{ws}/jobs/{job_id}"
    job = alice.get(url).json()
    assert job["status"] == "failed"
    assert "provider timeout" in job["error"]
    assert alice.post(f"{url}/retry").json()["status"] == "queued"
    assert alice.post(f"{url}/retry").status_code == 409


def test_concurrent_workers_never_run_a_job_twice(as_user):
    ws = _workspace(as_user("alice"))
    calls.clear()
    for n in "abcdef":
        _enqueue(ws, "test_ok", {"n": n})

    async def drain():
        async def worker():
            while await queue.run_once():
                pass

        await asyncio.gather(*(worker() for _ in range(4)))

    asyncio.run(drain())
    assert sorted(calls) == list("abcdef")


def test_jobs_are_workspace_scoped(as_user):
    alice, mallory = as_user("alice"), as_user("mallory")
    ws = _workspace(alice)
    ws_m = _workspace(mallory, "Other")
    job_id = _enqueue(ws, "test_ok", {"n": "x"})
    assert mallory.get(f"/api/v1/workspaces/{ws_m}/jobs/{job_id}").status_code == 404


def test_unknown_kind_is_rejected(as_user):
    ws = _workspace(as_user("alice"))
    with pytest.raises(ValueError):
        _enqueue(ws, "nope", {})


def _set_running(job_id: str, *, age_s: float, attempts: int) -> None:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from app.core.models import Job

    async def go():
        async with SessionLocal() as db:
            await db.execute(
                update(Job)
                .where(Job.id == uuid.UUID(job_id))
                .values(
                    status="running",
                    attempts=attempts,
                    updated_at=datetime.now(UTC) - timedelta(seconds=age_s),
                )
            )
            await db.commit()

    asyncio.run(go())


def test_requeue_takes_back_only_jobs_whose_heartbeat_stopped(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    stale = _enqueue(ws, "test_ok", {"n": "stale"})
    alive = _enqueue(ws, "test_ok", {"n": "alive"})
    _set_running(stale, age_s=600, attempts=1)
    _set_running(alive, age_s=1, attempts=1)
    assert asyncio.run(queue.requeue_interrupted()) == 1
    url = f"/api/v1/workspaces/{ws}/jobs"
    assert alice.get(f"{url}/{stale}").json()["status"] == "queued"
    # Another process is still running this one: it must not be run twice.
    assert alice.get(f"{url}/{alive}").json()["status"] == "running"


def test_a_job_interrupted_too_often_fails_with_a_clear_error(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    job_id = _enqueue(ws, "test_ok", {"n": "crashy"})
    _set_running(job_id, age_s=600, attempts=3)
    assert asyncio.run(queue.requeue_interrupted()) == 0
    url = f"/api/v1/workspaces/{ws}/jobs/{job_id}"
    job = alice.get(url).json()
    assert job["status"] == "failed"
    assert "Interrupted 3 times" in job["error"]
    # « Relancer » starts the count again.
    assert alice.post(f"{url}/retry").json()["status"] == "queued"
    calls.clear()
    assert asyncio.run(queue.run_once()) is True
    assert calls == ["crashy"]


def test_a_running_job_keeps_beating(as_user, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "job_heartbeat_seconds", 0.05)
    seen: list = []

    @queue.handler("test_slow")
    async def _slow(ctx: queue.JobContext) -> dict:
        from app.core.models import Job

        async with SessionLocal() as db:
            before = (await db.get(Job, ctx.job_id)).updated_at
        await asyncio.sleep(0.3)
        async with SessionLocal() as db:
            seen.append((await db.get(Job, ctx.job_id)).updated_at > before)
        return {}

    ws = _workspace(as_user("alice"))
    _enqueue(ws, "test_slow", {})
    asyncio.run(queue.run_once())
    assert seen == [True]

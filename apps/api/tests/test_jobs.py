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

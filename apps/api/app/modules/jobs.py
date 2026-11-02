import uuid

from fastapi import APIRouter
from sqlalchemy import update

from app.core.access import AnyMember, Db
from app.core.errors import ApiError
from app.core.models import Job
from app.workers import queue

router = APIRouter(tags=["jobs"])


@router.get("/workspaces/{ws}/jobs/{job_id}")
async def get_job(job_id: uuid.UUID, member: AnyMember, db: Db) -> dict:
    job = await queue.get_job(db, member.workspace_id, job_id)
    if job is None:
        raise ApiError(404, "not_found", "Job not found")
    return queue.job_payload(job)


@router.post("/workspaces/{ws}/jobs/{job_id}/retry")
async def retry_job(job_id: uuid.UUID, member: AnyMember, db: Db) -> dict:
    job = await queue.get_job(db, member.workspace_id, job_id)
    if job is None:
        raise ApiError(404, "not_found", "Job not found")
    if job.status != "failed":
        raise ApiError(409, "not_failed", "Only failed jobs can be retried")
    await db.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(status="queued", progress=0, error=None, finished_at=None)
    )
    await db.commit()
    await db.refresh(job)
    queue._wake.set()
    return queue.job_payload(job)

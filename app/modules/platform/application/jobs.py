from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.auth import audit
from app.infrastructure.tenant_context import set_tenant_context
from app.modules.platform.infrastructure.models import JobModel


def sanitize_job_error(error: Exception) -> str:
    return f"{type(error).__name__}: {error}"[:500]


async def claim_jobs(
    db: AsyncSession,
    tenant_id: UUID,
    worker: str,
    *,
    limit: int = 10,
    lease_seconds: int = 60,
) -> list[JobModel]:
    await set_tenant_context(db, tenant_id)
    now = datetime.now(UTC)
    jobs = list((await db.scalars(
        select(JobModel).where(
            JobModel.tenant_id == tenant_id,
            JobModel.status.in_(("queued", "running")),
            JobModel.scheduled_at <= now,
            or_(JobModel.status == "queued", JobModel.lock_expires_at < now),
        ).order_by(JobModel.scheduled_at).with_for_update(skip_locked=True).limit(limit)
    )).all())
    for job in jobs:
        job.status = "running"
        job.lock_owner = worker
        job.lock_expires_at = now + timedelta(seconds=lease_seconds)
        job.started_at = job.started_at or now
        job.attempts += 1
    await db.commit()
    return jobs


async def complete_job(db: AsyncSession, tenant_id: UUID, job_id: UUID, worker: str) -> bool:
    await set_tenant_context(db, tenant_id)
    job = await db.scalar(select(JobModel).where(JobModel.tenant_id == tenant_id, JobModel.id == job_id, JobModel.status == "running", JobModel.lock_owner == worker).with_for_update())
    if job is None:
        return False
    job.status = "succeeded"
    job.completed_at = datetime.now(UTC)
    job.lock_owner = None
    job.lock_expires_at = None
    await db.commit()
    return True


async def fail_job(db: AsyncSession, tenant_id: UUID, job_id: UUID, worker: str, error: Exception) -> bool:
    await set_tenant_context(db, tenant_id)
    job = await db.scalar(select(JobModel).where(JobModel.tenant_id == tenant_id, JobModel.id == job_id, JobModel.status == "running", JobModel.lock_owner == worker).with_for_update())
    if job is None:
        return False
    job.last_error = sanitize_job_error(error)
    job.lock_owner = None
    job.lock_expires_at = None
    if job.attempts >= job.max_attempts:
        job.status = "dead_letter"
        job.completed_at = datetime.now(UTC)
    else:
        job.status = "queued"
        job.scheduled_at = datetime.now(UTC) + timedelta(seconds=min(300, 2 ** job.attempts))
    await audit(db, "platform.job_retry_failed", "denied", tenant_id=tenant_id, resource=str(job.id), metadata={"attempts": job.attempts, "status": job.status, "correlation_id": str(job.correlation_id)})
    if job.status == "dead_letter":
        await audit(db, "platform.job_dead_letter", "denied", tenant_id=tenant_id, resource=str(job.id), metadata={"correlation_id": str(job.correlation_id)})
    await db.commit()
    return True

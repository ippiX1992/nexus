"""Claim and process pending catalog.variant_generation Jobs.

Manual, periodic invocation -- Nexus has no autonomous job dispatcher yet
(same known gap already documented for the rest of the Platform Kernel's
jobs, see docs/modules/03-catalog-foundation.md section 12). Mirrors
scripts/cleanup_rate_limits.py: a script to run on a schedule until real
supervision exists, not a background daemon.
"""

import argparse
import asyncio

from sqlalchemy import select

from app.infrastructure.database import SessionFactory
from app.modules.catalog.application.generation import JOB_TYPE, run_variant_generation_job
from app.modules.platform.application.jobs import claim_jobs, complete_job, fail_job
from app.modules.platform.infrastructure.runtime_models import JobModel


async def _tenants_with_pending_jobs() -> list:
    async with SessionFactory() as db:
        rows = await db.scalars(
            select(JobModel.tenant_id)
            .where(JobModel.job_type == JOB_TYPE, JobModel.status.in_(("queued", "running")))
            .distinct()
        )
        return list(rows.all())


async def run_once(*, worker: str) -> dict[str, int]:
    processed = 0
    failed = 0
    for tenant_id in await _tenants_with_pending_jobs():
        async with SessionFactory() as db:
            jobs = await claim_jobs(db, tenant_id, worker)
        for job in jobs:
            if job.job_type != JOB_TYPE:
                continue
            async with SessionFactory() as db:
                try:
                    await run_variant_generation_job(db, job)
                    await complete_job(db, tenant_id, job.id, worker)
                    processed += 1
                except Exception as exc:  # noqa: BLE001 -- reported through fail_job's retry/dead-letter path
                    await db.rollback()
                    async with SessionFactory() as fail_db:
                        await fail_job(fail_db, tenant_id, job.id, worker, exc)
                    failed += 1
    return {"processed": processed, "failed": failed}


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", default="catalog-generation-worker-1")
    args = parser.parse_args()
    result = await run_once(worker=args.worker)
    print(f"Variant generation jobs processed: {result['processed']}, failed: {result['failed']}")


if __name__ == "__main__":
    asyncio.run(main())

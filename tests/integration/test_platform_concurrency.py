import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.infrastructure.database import SessionFactory
from app.infrastructure.tenant_context import set_tenant_context
from app.main import app
from app.modules.platform.application.jobs import claim_jobs, complete_job, fail_job
from app.modules.platform.application.messaging import DurableOperationConsumer
from app.modules.platform.application.services import PlatformActor, PlatformService
from app.modules.platform.infrastructure.models import JobModel, OperationModel, OutboxEventModel, StoreModel
from app.modules.platform.infrastructure.repositories import SqlAlchemyPlatformRepository
from tests.integration.test_platform_api import platform_context, store_payload

pytestmark = pytest.mark.integration


async def test_concurrent_idempotent_store_creation_has_one_effect(client, registration):
    headers, tenant = await platform_context(client, registration)
    key = str(uuid4())
    async def create():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as caller:
            return await caller.post("/api/v1/stores", headers={**headers, "Idempotency-Key": key}, json=store_payload())
    first, second = await asyncio.gather(create(), create())
    assert sorted([first.status_code, second.status_code]) in ([201, 201], [201, 409])
    async with SessionFactory() as db:
        await set_tenant_context(db, UUID(tenant["id"]))
        stores = (await db.scalars(select(StoreModel))).all()
        assert len(stores) == 1


async def test_job_claim_retry_expired_lock_and_completion(client, registration):
    _, tenant = await platform_context(client, registration)
    tenant_id = UUID(tenant["id"])
    job_id = uuid4()
    async with SessionFactory() as db:
        await set_tenant_context(db, tenant_id)
        db.add(JobModel(id=job_id, tenant_id=tenant_id, job_type="platform.maintenance", payload={}, status="queued", attempts=0, max_attempts=2, scheduled_at=datetime.now(UTC), correlation_id=uuid4()))
        await db.commit()
    async with SessionFactory() as db:
        claimed = await claim_jobs(db, tenant_id, "worker-a")
        assert [job.id for job in claimed] == [job_id]
        assert await fail_job(db, tenant_id, job_id, "worker-a", RuntimeError("temporary"))
    async with SessionFactory() as db:
        await set_tenant_context(db, tenant_id)
        job = await db.get(JobModel, job_id)
        assert job is not None
        job.scheduled_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()
        claimed = await claim_jobs(db, tenant_id, "worker-b")
        assert len(claimed) == 1
        assert await complete_job(db, tenant_id, job_id, "worker-b")
    async with SessionFactory() as db:
        await set_tenant_context(db, tenant_id)
        expired_id = uuid4()
        db.add(JobModel(id=expired_id, tenant_id=tenant_id, job_type="platform.expired", payload={}, status="running", attempts=1, max_attempts=3, scheduled_at=datetime.now(UTC) - timedelta(minutes=2), lock_owner="dead-worker", lock_expires_at=datetime.now(UTC) - timedelta(minutes=1), correlation_id=uuid4()))
        await db.commit()
        recovered = await claim_jobs(db, tenant_id, "worker-c")
        assert any(job.id == expired_id for job in recovered)


async def test_transaction_rollback_has_no_orphan_event_and_inbox_is_idempotent(client, registration):
    headers, tenant = await platform_context(client, registration)
    tenant_id = UUID(tenant["id"])
    async with SessionFactory() as db:
        await set_tenant_context(db, tenant_id)
        service = PlatformService(SqlAlchemyPlatformRepository(db), PlatformActor(UUID((await client.get("/api/v1/me", headers=headers)).json()["id"]), None, tenant_id, uuid4()), db)
        await service.create_store(store_payload(code="rollback", slug="rollback"))
        await db.rollback()
    async with SessionFactory() as db:
        await set_tenant_context(db, tenant_id)
        assert await db.scalar(select(StoreModel).where(StoreModel.code == "rollback")) is None
        assert await db.scalar(select(OutboxEventModel).where(OutboxEventModel.aggregate_type == "store")) is None
    created = await client.post("/api/v1/stores", headers={**headers, "Idempotency-Key": str(uuid4())}, json=store_payload())
    assert created.status_code == 201
    async with SessionFactory() as db:
        await set_tenant_context(db, tenant_id)
        event = await db.scalar(select(OutboxEventModel))
        assert event is not None
        consumer = DurableOperationConsumer(db)
        assert await consumer.consume(event)
        assert not await consumer.consume(event)
        await db.commit()
        await set_tenant_context(db, tenant_id)
        operations = (await db.scalars(select(OperationModel))).all()
        assert len(operations) == 1

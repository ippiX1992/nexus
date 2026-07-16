"""Durable variant combination generation: Operation + Job, no cartesian product
inside the HTTP request. A worker claims and runs the Job later -- see
scripts/run_catalog_generation_worker.py, which reuses the same claim/complete/
fail primitives the Platform Kernel already uses for other job types
(app/modules/platform/application/jobs.py). No new job-runner infrastructure is
introduced here.
"""

from datetime import UTC, datetime
from itertools import product as cartesian_product
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.auth import audit
from app.infrastructure.tenant_context import set_tenant_context
from app.modules.catalog.application.services import CatalogActor, CatalogService
from app.modules.catalog.domain.policies import CatalogPolicyError
from app.modules.catalog.domain.values import derive_variant_sku
from app.modules.catalog.infrastructure.repositories import SqlAlchemyCatalogRepository
from app.modules.platform.contracts.events import EventActor, EventEnvelope
from app.modules.platform.infrastructure.runtime_models import JobModel, OperationModel

JOB_TYPE = "catalog.variant_generation"


async def create_generation_operation(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    product_id: UUID,
    correlation_id: UUID,
    idempotency_key: str,
) -> OperationModel:
    operation = OperationModel(
        tenant_id=tenant_id,
        operation_type=JOB_TYPE,
        status="queued",
        progress=0,
        correlation_id=correlation_id,
        actor_id=actor_id,
    )
    db.add(operation)
    await db.flush()
    repository = SqlAlchemyCatalogRepository(db)
    db.add(
        JobModel(
            tenant_id=tenant_id,
            operation_id=operation.id,
            job_type=JOB_TYPE,
            payload={"product_id": str(product_id), "actor_id": str(actor_id)},
            scheduled_at=datetime.now(UTC),
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        )
    )
    await repository.add_event(
        EventEnvelope.create(
            event_type="catalog.variant_generation.requested.v1",
            tenant_id=tenant_id,
            store_id=None,
            aggregate_type="catalog.product",
            aggregate_id=product_id,
            correlation_id=correlation_id,
            actor=EventActor(actor_id, None),
            data={"operation_id": str(operation.id)},
        )
    )
    return operation


async def _pending_option_values(
    repository: SqlAlchemyCatalogRepository, tenant_id: UUID, product_id: UUID
) -> list[list[tuple[UUID, UUID, str]]]:
    product_options = [
        item for item in await repository.list_product_options(tenant_id, product_id) if item.archived_at is None
    ]
    groups: list[list[tuple[UUID, UUID, str]]] = []
    for po in product_options:
        values = [
            value
            for value in await repository.list_option_values(tenant_id, po.option_id)
            if value.status != "archived"
        ]
        groups.append([(po.option_id, value.id, value.code) for value in values])
    return groups


async def _create_one_combination(
    db: AsyncSession, service: CatalogService, repository: SqlAlchemyCatalogRepository, product: Any, combo: tuple[tuple[UUID, UUID, str], ...]
) -> dict[str, Any]:
    """Runs inside its own SAVEPOINT so one bad combination cannot poison the batch."""
    value_ids = [value_id for _, value_id, _ in combo]
    base_code = product.code or str(product.id)[:8]
    sku, sku_normalized = derive_variant_sku(base_code, [code for *_rest, code in combo])
    try:
        async with db.begin_nested():
            row = await repository.create_variant(
                service.actor.tenant_id,
                service.actor.user_id,
                {
                    "product_id": product.id,
                    "sku": sku,
                    "sku_normalized": sku_normalized,
                    "is_default": False,
                    "status": "active",
                },
            )
            await repository.flush()
            await service._apply_combination(row, product, value_ids)  # noqa: SLF001 -- generation.py and services.py are one cohesive unit
            await repository.flush()
        return {"outcome": "created", "sku": sku}
    except (IntegrityError, CatalogPolicyError) as exc:
        return {"outcome": "skipped_already_exists", "sku": sku, "message": str(exc)[:200]}


async def run_variant_generation_job(db: AsyncSession, job: JobModel) -> dict[str, Any]:
    """Process one catalog.variant_generation Job.

    Each candidate combination is attempted inside its own SAVEPOINT (same
    isolation technique M3.0's bulk import already uses per row), so one
    duplicate or quota-exceeded candidate never poisons the rest of the batch.
    Idempotent under retry: combinations already created are detected via the
    unique fingerprint index (IntegrityError) and reported as skipped, never
    duplicated. Nothing here generates the whole cartesian product inside an
    HTTP request -- this function is only ever invoked by a worker after
    claim_jobs(), see scripts/run_catalog_generation_worker.py.
    """
    tenant_id = job.tenant_id
    product_id = UUID(job.payload["product_id"])
    actor_id = UUID(job.payload["actor_id"])
    await set_tenant_context(db, tenant_id)
    operation = await db.get(OperationModel, job.operation_id) if job.operation_id else None
    if operation is not None:
        operation.status = "running"
        operation.started_at = operation.started_at or datetime.now(UTC)
        await db.flush()
    repository = SqlAlchemyCatalogRepository(db)
    product = await repository.get_product(tenant_id, product_id)
    if product is None:
        result = {"created": 0, "skipped": 0, "failed": 1, "results": [{"outcome": "failed", "message": "Product not found"}]}
        if operation is not None:
            operation.status = "failed"
            operation.error = "Product not found"
            operation.completed_at = datetime.now(UTC)
        await db.commit()
        return result
    groups = await _pending_option_values(repository, tenant_id, product_id)
    if not groups or any(len(group) == 0 for group in groups):
        result = {"created": 0, "skipped": 0, "failed": 0, "results": []}
        if operation is not None:
            operation.status = "succeeded"
            operation.progress = 100
            operation.result = result
            operation.completed_at = datetime.now(UTC)
        await db.commit()
        return result
    per_operation_limit = await repository.entitlement_limit(tenant_id, "catalog.combination_generation.max_per_operation")
    combination_limit = await repository.entitlement_limit(tenant_id, "catalog.variant_combinations.max_per_product")
    existing_count = await repository.count_variant_combinations(tenant_id, product_id)
    actor = CatalogActor(user_id=actor_id, session_id=None, tenant_id=tenant_id, correlation_id=job.correlation_id)
    service = CatalogService(repository, actor, db)
    created = 0
    results: list[dict[str, Any]] = []
    candidates = list(cartesian_product(*groups))
    for index, combo in enumerate(candidates, start=1):
        if created >= per_operation_limit or existing_count + created >= combination_limit:
            results.append({"outcome": "skipped", "message": "Operation or product combination limit reached"})
        else:
            outcome = await _create_one_combination(db, service, repository, product, combo)
            results.append(outcome)
            if outcome["outcome"] == "created":
                created += 1
        if operation is not None:
            operation.progress = int(index / len(candidates) * 100)
            await db.commit()
            # app.current_tenant_id is SET LOCAL (transaction-scoped, see
            # app/infrastructure/tenant_context.py) -- committing above ends
            # the transaction and drops it, so every subsequent RLS-checked
            # write in this loop would silently start failing without
            # re-establishing it here.
            await set_tenant_context(db, tenant_id)
    skipped = sum(1 for r in results if r["outcome"].startswith("skipped"))
    failed = sum(1 for r in results if r["outcome"] == "failed")
    result = {"created": created, "skipped": skipped, "failed": failed, "results": results}
    if operation is not None:
        operation.status = "succeeded" if failed == 0 else "failed"
        operation.progress = 100
        operation.result = result
        operation.completed_at = datetime.now(UTC)
    await audit(
        db,
        "catalog.variant_generation_processed",
        "success",
        actor_id,
        tenant_id,
        resource=str(product_id),
        metadata={"created": created, "skipped": skipped, "failed": failed, "correlation_id": str(job.correlation_id)},
    )
    await db.commit()
    return result

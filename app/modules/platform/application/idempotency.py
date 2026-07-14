import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.platform.infrastructure.models import IdempotencyRecordModel


class IdempotencyConflict(ValueError):
    pass


class IdempotencyInProgress(ValueError):
    pass


@dataclass(slots=True)
class IdempotencyResult:
    record: IdempotencyRecordModel
    replay_body: dict[str, Any] | None = None
    replay_code: int | None = None


def request_fingerprint(method: str, endpoint: str, payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(f"{method.upper()}\n{endpoint}\n{canonical}".encode()).hexdigest()


async def begin_idempotent(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    method: str,
    endpoint: str,
    key: str,
    payload: dict[str, Any],
) -> IdempotencyResult:
    if not key or len(key) > 200:
        raise IdempotencyConflict("Idempotency-Key must contain 1 to 200 characters")
    fingerprint = request_fingerprint(method, endpoint, payload)
    record_id = uuid4()
    statement = insert(IdempotencyRecordModel).values(
        id=record_id,
        tenant_id=tenant_id,
        actor_id=actor_id,
        key=key,
        method=method.upper(),
        endpoint=endpoint,
        request_fingerprint=fingerprint,
        status="processing",
        expires_at=datetime.now(UTC) + timedelta(hours=24),
    ).on_conflict_do_nothing(
        constraint="uq_platform_idempotency_operation"
    ).returning(IdempotencyRecordModel.id)
    inserted = await db.scalar(statement)
    if inserted:
        record = await db.get(IdempotencyRecordModel, inserted)
        assert record is not None
        return IdempotencyResult(record)
    record = await db.scalar(select(IdempotencyRecordModel).where(
        IdempotencyRecordModel.tenant_id == tenant_id,
        IdempotencyRecordModel.actor_id == actor_id,
        IdempotencyRecordModel.method == method.upper(),
        IdempotencyRecordModel.endpoint == endpoint,
        IdempotencyRecordModel.key == key,
    ).with_for_update())
    if record is None:
        raise IdempotencyInProgress("Idempotent request is being initialized")
    if record.request_fingerprint != fingerprint:
        raise IdempotencyConflict("Idempotency-Key was already used with a different request")
    if record.status == "completed" and record.response_body is not None and record.response_code is not None:
        return IdempotencyResult(record, record.response_body, record.response_code)
    if record.expires_at <= datetime.now(UTC):
        record.status = "processing"
        record.response_body = None
        record.response_code = None
        record.request_fingerprint = fingerprint
        record.expires_at = datetime.now(UTC) + timedelta(hours=24)
        return IdempotencyResult(record)
    raise IdempotencyInProgress("A request with this Idempotency-Key is still processing")


def complete_idempotent(record: IdempotencyRecordModel, body: dict[str, Any], code: int) -> None:
    record.status = "completed"
    record.response_body = body
    record.response_code = code

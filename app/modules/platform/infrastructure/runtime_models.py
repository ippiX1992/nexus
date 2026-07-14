from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.models import Base


class OutboxEventModel(Base):
    __tablename__ = "platform_outbox_events"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "store_id"], ["platform_stores.tenant_id", "platform_stores.id"], ondelete="CASCADE"),
        CheckConstraint("status IN ('pending','processing','published','failed','dead_letter')", name="ck_platform_outbox_status"),
        Index("ix_platform_outbox_claim", "tenant_id", "status", "available_at"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    store_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    aggregate_type: Mapped[str] = mapped_column(String(64))
    aggregate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    event_type: Mapped[str] = mapped_column(String(160))
    event_version: Mapped[int] = mapped_column(Integer, default=1)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    correlation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    causation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="pending")


class InboxEventModel(Base):
    __tablename__ = "platform_inbox_events"
    __table_args__ = (
        UniqueConstraint("consumer_name", "event_id", name="uq_platform_inbox_consumer_event"),
        CheckConstraint("status IN ('processing','processed','failed')", name="ck_platform_inbox_status"),
        Index("ix_platform_inbox_tenant_status", "tenant_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    consumer_name: Mapped[str] = mapped_column(String(120))
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    event_type: Mapped[str] = mapped_column(String(160))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="processing")
    attempt_count: Mapped[int] = mapped_column(Integer, default=1)
    last_error: Mapped[str | None] = mapped_column(String(500))


class IdempotencyRecordModel(Base):
    __tablename__ = "platform_idempotency_records"
    __table_args__ = (
        UniqueConstraint("tenant_id", "actor_id", "method", "endpoint", "key", name="uq_platform_idempotency_operation"),
        CheckConstraint("status IN ('processing','completed','failed')", name="ck_platform_idempotency_status"),
        Index("ix_platform_idempotency_tenant_expiry", "tenant_id", "expires_at"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    key: Mapped[str] = mapped_column(String(200))
    method: Mapped[str] = mapped_column(String(10))
    endpoint: Mapped[str] = mapped_column(String(300))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="processing")
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    response_code: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OperationModel(Base):
    __tablename__ = "platform_operations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_platform_operations_tenant_id"),
        CheckConstraint("status IN ('queued','running','succeeded','failed','cancelled')", name="ck_platform_operation_status"),
        CheckConstraint("progress BETWEEN 0 AND 100", name="ck_platform_operation_progress"),
        Index("ix_platform_operations_tenant_created", "tenant_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    operation_type: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(String(500))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(String(500))
    correlation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class JobModel(Base):
    __tablename__ = "platform_jobs"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "operation_id"], ["platform_operations.tenant_id", "platform_operations.id"], ondelete="SET NULL"),
        CheckConstraint("status IN ('queued','running','succeeded','failed','cancelled','dead_letter')", name="ck_platform_job_status"),
        CheckConstraint("max_attempts > 0 AND attempts >= 0", name="ck_platform_job_attempts"),
        Index("ix_platform_jobs_claim", "tenant_id", "status", "scheduled_at", "lock_expires_at"),
        Index("uq_platform_jobs_idempotency", "tenant_id", "job_type", "idempotency_key", unique=True, postgresql_where=text("idempotency_key IS NOT NULL")),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    operation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    job_type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(500))
    lock_owner: Mapped[str | None] = mapped_column(String(120))
    lock_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str | None] = mapped_column(String(200))
    correlation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class EntitlementDefinitionModel(Base):
    __tablename__ = "platform_entitlement_definitions"
    __table_args__ = (CheckConstraint("default_value >= 0", name="ck_platform_entitlement_default"),)
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    default_value: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(300))


class EntitlementOverrideModel(Base):
    __tablename__ = "platform_entitlement_overrides"
    __table_args__ = (
        CheckConstraint("value >= 0", name="ck_platform_entitlement_override"),
        Index("ix_platform_entitlement_overrides_tenant", "tenant_id", "key"),
    )
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True)
    key: Mapped[str] = mapped_column(ForeignKey("platform_entitlement_definitions.key", ondelete="CASCADE"), primary_key=True)
    value: Mapped[int] = mapped_column(Integer)
    updated_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

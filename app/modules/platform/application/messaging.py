from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.auth import audit
from app.infrastructure.tenant_context import set_tenant_context
from app.modules.platform.infrastructure.models import InboxEventModel, OperationModel, OutboxEventModel


class EventPublisher(Protocol):
    async def publish(self, event: OutboxEventModel) -> None: ...


class DurableOperationConsumer:
    """Useful internal consumer proving inbox idempotency without business logic."""

    name = "platform.operation-recorder.v1"

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def consume(self, event: OutboxEventModel) -> bool:
        inbox_id = uuid4()
        inserted = await self.db.scalar(
            insert(InboxEventModel).values(
                id=inbox_id,
                tenant_id=event.tenant_id,
                consumer_name=self.name,
                event_id=event.id,
                event_type=event.event_type,
                status="processing",
                attempt_count=1,
            ).on_conflict_do_nothing(
                constraint="uq_platform_inbox_consumer_event"
            ).returning(InboxEventModel.id)
        )
        if not inserted:
            return False
        self.db.add(OperationModel(
            tenant_id=event.tenant_id,
            operation_type="outbox.event.processed",
            status="succeeded",
            progress=100,
            message=f"Processed {event.event_type}",
            result={"event_id": str(event.id), "event_type": event.event_type},
            correlation_id=event.correlation_id,
            completed_at=datetime.now(UTC),
        ))
        inbox = await self.db.get(InboxEventModel, inbox_id)
        assert inbox is not None
        inbox.status = "processed"
        inbox.processed_at = datetime.now(UTC)
        return True


class InternalEventPublisher:
    def __init__(self, consumer: DurableOperationConsumer) -> None:
        self.consumer = consumer

    async def publish(self, event: OutboxEventModel) -> None:
        await self.consumer.consume(event)


class OutboxDispatcher:
    def __init__(self, db: AsyncSession, publisher: EventPublisher, *, max_attempts: int = 5) -> None:
        self.db = db
        self.publisher = publisher
        self.max_attempts = max_attempts

    async def dispatch(self, tenant_id: UUID, *, limit: int = 50) -> int:
        await set_tenant_context(self.db, tenant_id)
        rows = (await self.db.scalars(
            select(OutboxEventModel).where(
                OutboxEventModel.tenant_id == tenant_id,
                OutboxEventModel.status.in_(("pending", "failed")),
                OutboxEventModel.available_at <= datetime.now(UTC),
            ).order_by(OutboxEventModel.occurred_at).with_for_update(skip_locked=True).limit(limit)
        )).all()
        published = 0
        for event in rows:
            event.status = "processing"
            event.attempt_count += 1
            try:
                await self.publisher.publish(event)
                event.status = "published"
                event.published_at = datetime.now(UTC)
                event.last_error = None
                published += 1
            except Exception as exc:
                event.last_error = str(exc)[:500]
                event.status = "dead_letter" if event.attempt_count >= self.max_attempts else "failed"
                if event.status == "dead_letter":
                    await audit(self.db, "platform.event_dead_letter", "denied", tenant_id=tenant_id, resource=str(event.id), metadata={"event_type": event.event_type, "correlation_id": str(event.correlation_id)})
        await self.db.commit()
        return published

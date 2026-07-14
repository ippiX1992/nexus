from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class EventActor:
    user_id: UUID | None
    session_id: UUID | None


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    event_id: UUID
    event_type: str
    event_version: int
    occurred_at: datetime
    tenant_id: UUID
    store_id: UUID | None
    aggregate_type: str
    aggregate_id: UUID
    correlation_id: UUID
    causation_id: UUID | None
    actor: EventActor
    data: dict[str, Any]

    @classmethod
    def create(
        cls,
        *,
        event_type: str,
        tenant_id: UUID,
        store_id: UUID | None,
        aggregate_type: str,
        aggregate_id: UUID,
        correlation_id: UUID,
        actor: EventActor,
        data: dict[str, Any],
        causation_id: UUID | None = None,
    ) -> "EventEnvelope":
        if not event_type.endswith(".v1"):
            raise ValueError("Platform events must declare their v1 contract")
        return cls(
            uuid4(), event_type, 1, datetime.now(UTC), tenant_id, store_id,
            aggregate_type, aggregate_id, correlation_id, causation_id, actor, data,
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        uuid_fields = ("event_id", "tenant_id", "store_id", "aggregate_id", "correlation_id", "causation_id")
        for key in uuid_fields:
            value[key] = str(value[key]) if value[key] is not None else None
        value["occurred_at"] = self.occurred_at.isoformat()
        value["actor"] = {
            key: str(item) if item is not None else None
            for key, item in value["actor"].items()
        }
        return value

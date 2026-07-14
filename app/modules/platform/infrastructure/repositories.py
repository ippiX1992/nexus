from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.platform.contracts.events import EventEnvelope
from app.modules.platform.infrastructure.models import (
    ChannelModel,
    EntitlementDefinitionModel,
    EntitlementOverrideModel,
    EnvironmentModel,
    MarketModel,
    OutboxEventModel,
    ResourceScopeModel,
    SiteModel,
    StoreModel,
)

RESOURCE_MODELS: dict[str, Any] = {
    "store": StoreModel,
    "site": SiteModel,
    "channel": ChannelModel,
    "environment": EnvironmentModel,
    "market": MarketModel,
}


class SqlAlchemyPlatformRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_store(self, tenant_id: UUID, store_id: UUID, *, lock: bool = False) -> StoreModel | None:
        statement = select(StoreModel).where(StoreModel.tenant_id == tenant_id, StoreModel.id == store_id)
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def get_resource(self, kind: str, tenant_id: UUID, resource_id: UUID) -> Any | None:
        model = RESOURCE_MODELS[kind]
        return await self.session.scalar(select(model).where(model.tenant_id == tenant_id, model.id == resource_id))

    async def list_resources(self, kind: str, tenant_id: UUID, store_id: UUID | None = None) -> list[Any]:
        model = RESOURCE_MODELS[kind]
        statement = select(model).where(model.tenant_id == tenant_id)
        if store_id is not None and kind != "store":
            statement = statement.where(model.store_id == store_id)
        statement = statement.order_by(model.created_at.desc())
        return list((await self.session.scalars(statement)).all())

    async def count_resources(self, kind: str, tenant_id: UUID, store_id: UUID | None = None) -> int:
        model = RESOURCE_MODELS[kind]
        statement = select(func.count()).select_from(model).where(model.tenant_id == tenant_id, model.status != "archived")
        if store_id is not None and kind != "store":
            statement = statement.where(model.store_id == store_id)
        return int(await self.session.scalar(statement) or 0)

    async def add(self, value: Any) -> None:
        self.session.add(value)

    async def flush(self) -> None:
        await self.session.flush()

    async def add_scope(self, tenant_id: UUID, scope_type: str, resource_id: UUID, parent_scope_id: UUID | None) -> None:
        self.session.add(ResourceScopeModel(tenant_id=tenant_id, scope_type=scope_type, resource_id=resource_id, parent_scope_id=parent_scope_id))

    async def get_scope(self, tenant_id: UUID, scope_type: str, resource_id: UUID) -> ResourceScopeModel | None:
        return await self.session.scalar(select(ResourceScopeModel).where(ResourceScopeModel.tenant_id == tenant_id, ResourceScopeModel.scope_type == scope_type, ResourceScopeModel.resource_id == resource_id, ResourceScopeModel.status == "active"))

    async def add_event(self, envelope: EventEnvelope) -> None:
        self.session.add(OutboxEventModel(
            id=envelope.event_id,
            tenant_id=envelope.tenant_id,
            store_id=envelope.store_id,
            aggregate_type=envelope.aggregate_type,
            aggregate_id=envelope.aggregate_id,
            event_type=envelope.event_type,
            event_version=envelope.event_version,
            payload=envelope.to_dict(),
            metadata_json={"actor": envelope.to_dict()["actor"]},
            correlation_id=envelope.correlation_id,
            causation_id=envelope.causation_id,
            occurred_at=envelope.occurred_at,
            available_at=envelope.occurred_at,
        ))

    async def entitlement_limit(self, tenant_id: UUID, key: str) -> int:
        value = await self.session.scalar(
            select(func.coalesce(EntitlementOverrideModel.value, EntitlementDefinitionModel.default_value))
            .select_from(EntitlementDefinitionModel)
            .outerjoin(EntitlementOverrideModel, (EntitlementOverrideModel.key == EntitlementDefinitionModel.key) & (EntitlementOverrideModel.tenant_id == tenant_id))
            .where(EntitlementDefinitionModel.key == key)
        )
        if value is None:
            raise KeyError(f"Unknown entitlement {key}")
        return int(value)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.infrastructure.models import ProductVariantModel
from app.modules.platform.contracts.events import EventEnvelope
from app.modules.platform.infrastructure.models import OutboxEventModel
from app.modules.pricing.infrastructure.models import (
    PriceHistoryModel,
    PriceListAssignmentModel,
    PriceListEntryModel,
    PriceListModel,
    VariantPriceOverrideModel,
)

_ENTRY_SNAPSHOT_FIELDS = ("unit_amount", "compare_at_amount", "msrp_amount", "cost_amount")


class SqlAlchemyPricingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _get(self, model: Any, tenant_id: UUID, resource_id: UUID, lock: bool) -> Any | None:
        statement = select(model).where(model.tenant_id == tenant_id, model.id == resource_id)
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    @staticmethod
    def _after_cursor(statement: Any, model: Any, cursor: tuple[datetime, UUID] | None) -> Any:
        if cursor is None:
            return statement
        created_at, resource_id = cursor
        return statement.where(
            or_(model.created_at < created_at, and_(model.created_at == created_at, model.id < resource_id))
        )

    async def _list(
        self,
        model: Any,
        tenant_id: UUID,
        *,
        limit: int,
        cursor: tuple[datetime, UUID] | None,
        extra_filters: tuple[Any, ...] = (),
    ) -> tuple[list[Any], bool]:
        statement = select(model).where(model.tenant_id == tenant_id, *extra_filters)
        statement = (
            self._after_cursor(statement, model, cursor).order_by(model.created_at.desc(), model.id.desc()).limit(limit + 1)
        )
        rows = list((await self.session.scalars(statement)).all())
        return rows[:limit], len(rows) > limit

    # --- Price Lists ---

    async def get_price_list(self, tenant_id: UUID, resource_id: UUID, *, lock: bool = False) -> PriceListModel | None:
        return await self._get(PriceListModel, tenant_id, resource_id, lock)

    async def get_price_list_by_code(self, tenant_id: UUID, code: str) -> PriceListModel | None:
        return await self.session.scalar(
            select(PriceListModel).where(PriceListModel.tenant_id == tenant_id, PriceListModel.code == code)
        )

    async def get_default_price_list(self, tenant_id: UUID) -> PriceListModel | None:
        return await self.session.scalar(
            select(PriceListModel).where(
                PriceListModel.tenant_id == tenant_id,
                PriceListModel.is_default.is_(True),
                PriceListModel.status != "archived",
            )
        )

    async def list_price_lists(
        self, tenant_id: UUID, *, limit: int, cursor: tuple[datetime, UUID] | None, status: str | None = None
    ) -> tuple[list[Any], bool]:
        extra = (PriceListModel.status == status,) if status else ()
        return await self._list(PriceListModel, tenant_id, limit=limit, cursor=cursor, extra_filters=extra)

    async def create_price_list(self, tenant_id: UUID, actor_id: UUID, data: dict[str, Any]) -> PriceListModel:
        row = PriceListModel(tenant_id=tenant_id, created_by=actor_id, updated_by=actor_id, **data)
        self.session.add(row)
        return row

    # --- Price List Entries ---

    async def get_price_list_entry(
        self, tenant_id: UUID, resource_id: UUID, *, lock: bool = False
    ) -> PriceListEntryModel | None:
        return await self._get(PriceListEntryModel, tenant_id, resource_id, lock)

    async def get_price_list_entry_by_variant(
        self, tenant_id: UUID, price_list_id: UUID, variant_id: UUID, *, lock: bool = False
    ) -> PriceListEntryModel | None:
        statement = select(PriceListEntryModel).where(
            PriceListEntryModel.tenant_id == tenant_id,
            PriceListEntryModel.price_list_id == price_list_id,
            PriceListEntryModel.variant_id == variant_id,
        )
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def list_price_list_entries(
        self, tenant_id: UUID, price_list_id: UUID, *, limit: int, cursor: tuple[datetime, UUID] | None
    ) -> tuple[list[Any], bool]:
        return await self._list(
            PriceListEntryModel,
            tenant_id,
            limit=limit,
            cursor=cursor,
            extra_filters=(PriceListEntryModel.price_list_id == price_list_id,),
        )

    async def list_entries_for_variant_in_lists(
        self, tenant_id: UUID, variant_id: UUID, price_list_ids: list[UUID]
    ) -> list[Any]:
        if not price_list_ids:
            return []
        rows = await self.session.scalars(
            select(PriceListEntryModel).where(
                PriceListEntryModel.tenant_id == tenant_id,
                PriceListEntryModel.variant_id == variant_id,
                PriceListEntryModel.price_list_id.in_(price_list_ids),
                PriceListEntryModel.status == "active",
            )
        )
        return list(rows.all())

    async def upsert_price_list_entry(
        self, tenant_id: UUID, actor_id: UUID, price_list_id: UUID, variant_id: UUID, data: dict[str, Any]
    ) -> tuple[PriceListEntryModel, dict[str, Any] | None]:
        row = await self.get_price_list_entry_by_variant(tenant_id, price_list_id, variant_id, lock=True)
        if row is None:
            row = PriceListEntryModel(
                tenant_id=tenant_id,
                price_list_id=price_list_id,
                variant_id=variant_id,
                created_by=actor_id,
                updated_by=actor_id,
                **data,
            )
            self.session.add(row)
            return row, None
        previous = {field: getattr(row, field) for field in _ENTRY_SNAPSHOT_FIELDS}
        for key, value in data.items():
            setattr(row, key, value)
        row.updated_by = actor_id
        return row, previous

    # --- Assignments ---

    async def get_assignment(
        self, tenant_id: UUID, resource_id: UUID, *, lock: bool = False
    ) -> PriceListAssignmentModel | None:
        return await self._get(PriceListAssignmentModel, tenant_id, resource_id, lock)

    async def list_assignments(
        self,
        tenant_id: UUID,
        *,
        limit: int,
        cursor: tuple[datetime, UUID] | None,
        price_list_id: UUID | None = None,
        status: str | None = None,
    ) -> tuple[list[Any], bool]:
        extra: tuple[Any, ...] = ()
        if price_list_id:
            extra = (*extra, PriceListAssignmentModel.price_list_id == price_list_id)
        if status:
            extra = (*extra, PriceListAssignmentModel.status == status)
        return await self._list(PriceListAssignmentModel, tenant_id, limit=limit, cursor=cursor, extra_filters=extra)

    async def list_active_assignments_for_scope(
        self, tenant_id: UUID, scope_type: str, scope_id: UUID
    ) -> list[Any]:
        scope_column = {
            "store": PriceListAssignmentModel.store_id,
            "channel": PriceListAssignmentModel.channel_id,
            "market": PriceListAssignmentModel.market_id,
        }[scope_type]
        rows = await self.session.scalars(
            select(PriceListAssignmentModel).where(
                PriceListAssignmentModel.tenant_id == tenant_id,
                PriceListAssignmentModel.scope_type == scope_type,
                scope_column == scope_id,
                PriceListAssignmentModel.status == "active",
            )
        )
        return list(rows.all())

    async def create_assignment(self, tenant_id: UUID, actor_id: UUID, data: dict[str, Any]) -> PriceListAssignmentModel:
        row = PriceListAssignmentModel(tenant_id=tenant_id, created_by=actor_id, updated_by=actor_id, **data)
        self.session.add(row)
        return row

    # --- Variant Price Overrides ---

    async def get_override(
        self, tenant_id: UUID, resource_id: UUID, *, lock: bool = False
    ) -> VariantPriceOverrideModel | None:
        return await self._get(VariantPriceOverrideModel, tenant_id, resource_id, lock)

    async def list_overrides(
        self,
        tenant_id: UUID,
        *,
        limit: int,
        cursor: tuple[datetime, UUID] | None,
        variant_id: UUID | None = None,
        status: str | None = None,
    ) -> tuple[list[Any], bool]:
        extra: tuple[Any, ...] = ()
        if variant_id:
            extra = (*extra, VariantPriceOverrideModel.variant_id == variant_id)
        if status:
            extra = (*extra, VariantPriceOverrideModel.status == status)
        return await self._list(VariantPriceOverrideModel, tenant_id, limit=limit, cursor=cursor, extra_filters=extra)

    async def list_active_overrides_for_variant_scope(
        self, tenant_id: UUID, variant_id: UUID, scope_type: str, scope_id: UUID
    ) -> list[Any]:
        scope_column = {
            "store": VariantPriceOverrideModel.store_id,
            "channel": VariantPriceOverrideModel.channel_id,
            "market": VariantPriceOverrideModel.market_id,
        }[scope_type]
        rows = await self.session.scalars(
            select(VariantPriceOverrideModel).where(
                VariantPriceOverrideModel.tenant_id == tenant_id,
                VariantPriceOverrideModel.variant_id == variant_id,
                VariantPriceOverrideModel.scope_type == scope_type,
                scope_column == scope_id,
                VariantPriceOverrideModel.status == "active",
            )
        )
        return list(rows.all())

    async def create_override(self, tenant_id: UUID, actor_id: UUID, data: dict[str, Any]) -> VariantPriceOverrideModel:
        row = VariantPriceOverrideModel(tenant_id=tenant_id, created_by=actor_id, updated_by=actor_id, **data)
        self.session.add(row)
        return row

    # --- History ---

    async def add_history_entry(self, tenant_id: UUID, data: dict[str, Any]) -> PriceHistoryModel:
        row = PriceHistoryModel(tenant_id=tenant_id, **data)
        self.session.add(row)
        return row

    async def list_history(
        self,
        tenant_id: UUID,
        *,
        limit: int,
        cursor: tuple[datetime, UUID] | None,
        variant_id: UUID | None = None,
        price_list_id: UUID | None = None,
    ) -> tuple[list[Any], bool]:
        statement = select(PriceHistoryModel).where(PriceHistoryModel.tenant_id == tenant_id)
        if variant_id:
            statement = statement.where(PriceHistoryModel.variant_id == variant_id)
        if price_list_id:
            statement = statement.where(
                PriceHistoryModel.entity_type == "price_list_entry",
                PriceHistoryModel.entity_id.in_(
                    select(PriceListEntryModel.id).where(
                        PriceListEntryModel.tenant_id == tenant_id,
                        PriceListEntryModel.price_list_id == price_list_id,
                    )
                ),
            )
        if cursor is not None:
            changed_at, resource_id = cursor
            statement = statement.where(
                or_(
                    PriceHistoryModel.changed_at < changed_at,
                    and_(PriceHistoryModel.changed_at == changed_at, PriceHistoryModel.id < resource_id),
                )
            )
        statement = statement.order_by(PriceHistoryModel.changed_at.desc(), PriceHistoryModel.id.desc()).limit(limit + 1)
        rows = list((await self.session.scalars(statement)).all())
        return rows[:limit], len(rows) > limit

    # --- Catalog cross-references ---

    async def variant_exists(self, tenant_id: UUID, variant_id: UUID) -> bool:
        row = await self.session.scalar(
            select(ProductVariantModel.id).where(
                ProductVariantModel.tenant_id == tenant_id, ProductVariantModel.id == variant_id
            )
        )
        return row is not None

    # --- Outbox / persistence ---

    async def add_event(self, envelope: EventEnvelope) -> None:
        payload = envelope.to_dict()
        self.session.add(
            OutboxEventModel(
                id=envelope.event_id,
                tenant_id=envelope.tenant_id,
                store_id=envelope.store_id,
                aggregate_type=envelope.aggregate_type,
                aggregate_id=envelope.aggregate_id,
                event_type=envelope.event_type,
                event_version=envelope.event_version,
                payload=payload,
                metadata_json={"actor": payload["actor"]},
                correlation_id=envelope.correlation_id,
                causation_id=envelope.causation_id,
                occurred_at=envelope.occurred_at,
                available_at=envelope.occurred_at,
            )
        )

    async def flush(self) -> None:
        await self.session.flush()

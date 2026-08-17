from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.infrastructure.models import ProductVariantModel
from app.modules.inventory.infrastructure.models import (
    FulfillmentScopeModel,
    LocationModel,
    ReservationModel,
    StockLedgerEntryModel,
    StockLevelModel,
    TransferModel,
    WarehouseModel,
)
from app.modules.platform.contracts.events import EventEnvelope
from app.modules.platform.infrastructure.models import OutboxEventModel


class SqlAlchemyInventoryRepository:
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

    # --- Warehouses ---

    async def get_warehouse(self, tenant_id: UUID, resource_id: UUID, *, lock: bool = False) -> WarehouseModel | None:
        return await self._get(WarehouseModel, tenant_id, resource_id, lock)

    async def get_warehouse_by_code(self, tenant_id: UUID, code: str) -> WarehouseModel | None:
        return await self.session.scalar(
            select(WarehouseModel).where(WarehouseModel.tenant_id == tenant_id, WarehouseModel.code == code)
        )

    async def list_warehouses(
        self, tenant_id: UUID, *, limit: int, cursor: tuple[datetime, UUID] | None, status: str | None = None
    ) -> tuple[list[Any], bool]:
        extra = (WarehouseModel.status == status,) if status else ()
        return await self._list(WarehouseModel, tenant_id, limit=limit, cursor=cursor, extra_filters=extra)

    async def create_warehouse(self, tenant_id: UUID, actor_id: UUID, data: dict[str, Any]) -> WarehouseModel:
        row = WarehouseModel(tenant_id=tenant_id, created_by=actor_id, updated_by=actor_id, **data)
        self.session.add(row)
        return row

    # --- Locations ---

    async def get_location(self, tenant_id: UUID, resource_id: UUID, *, lock: bool = False) -> LocationModel | None:
        return await self._get(LocationModel, tenant_id, resource_id, lock)

    async def list_locations(
        self, tenant_id: UUID, *, limit: int, cursor: tuple[datetime, UUID] | None, warehouse_id: UUID | None = None
    ) -> tuple[list[Any], bool]:
        extra = (LocationModel.warehouse_id == warehouse_id,) if warehouse_id else ()
        return await self._list(LocationModel, tenant_id, limit=limit, cursor=cursor, extra_filters=extra)

    async def create_location(self, tenant_id: UUID, actor_id: UUID, data: dict[str, Any]) -> LocationModel:
        row = LocationModel(tenant_id=tenant_id, created_by=actor_id, updated_by=actor_id, **data)
        self.session.add(row)
        return row

    # --- Stock levels ---

    async def get_stock_level(self, tenant_id: UUID, resource_id: UUID, *, lock: bool = False) -> StockLevelModel | None:
        return await self._get(StockLevelModel, tenant_id, resource_id, lock)

    async def get_stock_level_by_location_variant(
        self, tenant_id: UUID, location_id: UUID, variant_id: UUID, *, lock: bool = False
    ) -> StockLevelModel | None:
        statement = select(StockLevelModel).where(
            StockLevelModel.tenant_id == tenant_id,
            StockLevelModel.location_id == location_id,
            StockLevelModel.variant_id == variant_id,
        )
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def get_or_create_stock_level(
        self, tenant_id: UUID, actor_id: UUID, location_id: UUID, variant_id: UUID
    ) -> StockLevelModel:
        row = await self.get_stock_level_by_location_variant(tenant_id, location_id, variant_id, lock=True)
        if row is None:
            row = StockLevelModel(
                tenant_id=tenant_id,
                location_id=location_id,
                variant_id=variant_id,
                on_hand=0,
                reserved=0,
                incoming=0,
                created_by=actor_id,
                updated_by=actor_id,
            )
            self.session.add(row)
            await self.session.flush()
        return row

    async def list_stock_levels(
        self,
        tenant_id: UUID,
        *,
        limit: int,
        cursor: tuple[datetime, UUID] | None,
        variant_id: UUID | None = None,
        location_id: UUID | None = None,
    ) -> tuple[list[Any], bool]:
        extra: tuple[Any, ...] = ()
        if variant_id:
            extra = (*extra, StockLevelModel.variant_id == variant_id)
        if location_id:
            extra = (*extra, StockLevelModel.location_id == location_id)
        return await self._list(StockLevelModel, tenant_id, limit=limit, cursor=cursor, extra_filters=extra)

    async def list_available_candidates(
        self, tenant_id: UUID, variant_id: UUID, location_ids: list[UUID]
    ) -> list[Any]:
        if not location_ids:
            return []
        rows = await self.session.scalars(
            select(StockLevelModel).where(
                StockLevelModel.tenant_id == tenant_id,
                StockLevelModel.variant_id == variant_id,
                StockLevelModel.location_id.in_(location_ids),
                StockLevelModel.available > 0,
            )
        )
        return list(rows.all())

    # --- Ledger ---

    async def add_ledger_entry(self, tenant_id: UUID, data: dict[str, Any]) -> StockLedgerEntryModel:
        row = StockLedgerEntryModel(tenant_id=tenant_id, **data)
        self.session.add(row)
        return row

    async def list_ledger(
        self,
        tenant_id: UUID,
        *,
        limit: int,
        cursor: tuple[datetime, UUID] | None,
        variant_id: UUID | None = None,
        location_id: UUID | None = None,
    ) -> tuple[list[Any], bool]:
        statement = select(StockLedgerEntryModel).where(StockLedgerEntryModel.tenant_id == tenant_id)
        if variant_id:
            statement = statement.where(StockLedgerEntryModel.variant_id == variant_id)
        if location_id:
            statement = statement.where(StockLedgerEntryModel.location_id == location_id)
        if cursor is not None:
            created_at, resource_id = cursor
            statement = statement.where(
                or_(
                    StockLedgerEntryModel.created_at < created_at,
                    and_(StockLedgerEntryModel.created_at == created_at, StockLedgerEntryModel.id < resource_id),
                )
            )
        statement = statement.order_by(
            StockLedgerEntryModel.created_at.desc(), StockLedgerEntryModel.id.desc()
        ).limit(limit + 1)
        rows = list((await self.session.scalars(statement)).all())
        return rows[:limit], len(rows) > limit

    # --- Transfers ---

    async def get_transfer(self, tenant_id: UUID, resource_id: UUID, *, lock: bool = False) -> TransferModel | None:
        return await self._get(TransferModel, tenant_id, resource_id, lock)

    async def list_transfers(
        self, tenant_id: UUID, *, limit: int, cursor: tuple[datetime, UUID] | None, status: str | None = None
    ) -> tuple[list[Any], bool]:
        extra = (TransferModel.status == status,) if status else ()
        return await self._list(TransferModel, tenant_id, limit=limit, cursor=cursor, extra_filters=extra)

    async def create_transfer(self, tenant_id: UUID, actor_id: UUID, data: dict[str, Any]) -> TransferModel:
        row = TransferModel(tenant_id=tenant_id, created_by=actor_id, updated_by=actor_id, **data)
        self.session.add(row)
        return row

    # --- Reservations ---

    async def get_reservation(self, tenant_id: UUID, resource_id: UUID, *, lock: bool = False) -> ReservationModel | None:
        return await self._get(ReservationModel, tenant_id, resource_id, lock)

    async def list_reservations(
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
            extra = (*extra, ReservationModel.variant_id == variant_id)
        if status:
            extra = (*extra, ReservationModel.status == status)
        return await self._list(ReservationModel, tenant_id, limit=limit, cursor=cursor, extra_filters=extra)

    async def create_reservation(self, tenant_id: UUID, actor_id: UUID, data: dict[str, Any]) -> ReservationModel:
        row = ReservationModel(tenant_id=tenant_id, created_by=actor_id, updated_by=actor_id, **data)
        self.session.add(row)
        return row

    async def list_reservations_by_reference(
        self,
        tenant_id: UUID,
        reference_type: str,
        reference_id: UUID,
        *,
        status: str | None = None,
        lock: bool = False,
    ) -> list[ReservationModel]:
        """Every reservation a downstream document (e.g. a storefront order)
        placed. Locking is needed when we are about to commit/release them so a
        concurrent worker can't act on the same holds."""
        statement = select(ReservationModel).where(
            ReservationModel.tenant_id == tenant_id,
            ReservationModel.reference_type == reference_type,
            ReservationModel.reference_id == reference_id,
        )
        if status:
            statement = statement.where(ReservationModel.status == status)
        if lock:
            statement = statement.with_for_update()
        return list((await self.session.scalars(statement)).all())

    async def list_due_reservations(
        self, tenant_id: UUID, now: datetime, *, limit: int = 100
    ) -> list[ReservationModel]:
        """Held reservations past their expiry, locked with SKIP LOCKED so
        several sweeper workers can run at once without ever touching the same
        row twice."""
        statement = (
            select(ReservationModel)
            .where(
                ReservationModel.tenant_id == tenant_id,
                ReservationModel.status == "held",
                ReservationModel.expires_at.is_not(None),
                ReservationModel.expires_at <= now,
            )
            .order_by(ReservationModel.expires_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list((await self.session.scalars(statement)).all())

    # --- Fulfillment scopes ---

    async def get_fulfillment_scope(
        self, tenant_id: UUID, resource_id: UUID, *, lock: bool = False
    ) -> FulfillmentScopeModel | None:
        return await self._get(FulfillmentScopeModel, tenant_id, resource_id, lock)

    async def list_fulfillment_scopes(
        self, tenant_id: UUID, *, limit: int, cursor: tuple[datetime, UUID] | None, warehouse_id: UUID | None = None
    ) -> tuple[list[Any], bool]:
        extra = (FulfillmentScopeModel.warehouse_id == warehouse_id,) if warehouse_id else ()
        return await self._list(FulfillmentScopeModel, tenant_id, limit=limit, cursor=cursor, extra_filters=extra)

    async def list_active_scopes_for(self, tenant_id: UUID, scope_type: str, scope_id: UUID) -> list[Any]:
        scope_column = {
            "store": FulfillmentScopeModel.store_id,
            "channel": FulfillmentScopeModel.channel_id,
            "market": FulfillmentScopeModel.market_id,
        }[scope_type]
        rows = await self.session.scalars(
            select(FulfillmentScopeModel).where(
                FulfillmentScopeModel.tenant_id == tenant_id,
                FulfillmentScopeModel.scope_type == scope_type,
                scope_column == scope_id,
                FulfillmentScopeModel.status == "active",
            )
        )
        return list(rows.all())

    async def create_fulfillment_scope(
        self, tenant_id: UUID, actor_id: UUID, data: dict[str, Any]
    ) -> FulfillmentScopeModel:
        row = FulfillmentScopeModel(tenant_id=tenant_id, created_by=actor_id, updated_by=actor_id, **data)
        self.session.add(row)
        return row

    # --- Cross-references ---

    async def variant_exists(self, tenant_id: UUID, variant_id: UUID) -> bool:
        row = await self.session.scalar(
            select(ProductVariantModel.id).where(
                ProductVariantModel.tenant_id == tenant_id, ProductVariantModel.id == variant_id
            )
        )
        return row is not None

    async def active_location_ids(self, tenant_id: UUID) -> list[UUID]:
        """Every active location of the tenant, for reservations that aren't
        tied to a fulfillment scope (e.g. a single-store storefront checkout)."""
        rows = await self.session.scalars(
            select(LocationModel.id).where(
                LocationModel.tenant_id == tenant_id,
                LocationModel.status == "active",
            )
        )
        return list(rows.all())

    async def active_location_ids_for_warehouses(self, tenant_id: UUID, warehouse_ids: list[UUID]) -> list[UUID]:
        if not warehouse_ids:
            return []
        rows = await self.session.scalars(
            select(LocationModel.id).where(
                LocationModel.tenant_id == tenant_id,
                LocationModel.warehouse_id.in_(warehouse_ids),
                LocationModel.status == "active",
            )
        )
        return list(rows.all())

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

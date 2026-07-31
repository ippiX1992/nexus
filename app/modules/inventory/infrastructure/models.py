from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.models import Base


class InventoryResourceMixin:
    """Same shape as pricing/catalog resource mixins -- tenant ownership,
    optimistic version, audit timestamps -- shared by every tenant-owned,
    versioned resource in Nexus regardless of module."""

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


_SCOPE_COLUMNS_CHECK = (
    "(scope_type = 'store' AND store_id IS NOT NULL AND channel_id IS NULL AND market_id IS NULL) OR "
    "(scope_type = 'channel' AND channel_id IS NOT NULL AND store_id IS NULL AND market_id IS NULL) OR "
    "(scope_type = 'market' AND market_id IS NOT NULL AND store_id IS NULL AND channel_id IS NULL)"
)


class WarehouseModel(InventoryResourceMixin, Base):
    """A physical or logical facility that holds stock. Tenant-owned; its link
    to selling scopes (Store/Channel/Market) is expressed separately through
    FulfillmentScopeModel so a single warehouse can serve many scopes and the
    allocation engine can order them by priority."""

    __tablename__ = "inventory_warehouses"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_inventory_warehouses_tenant_id"),
        UniqueConstraint("tenant_id", "code", name="uq_inventory_warehouses_tenant_code"),
        CheckConstraint("status IN ('active','archived')", name="ck_inventory_warehouse_status"),
        CheckConstraint("version > 0", name="ck_inventory_warehouse_version"),
        Index("ix_inventory_warehouses_tenant_status", "tenant_id", "status", "id"),
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    country_code: Mapped[str | None] = mapped_column(String(2))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")


class LocationModel(InventoryResourceMixin, Base):
    """A subdivision inside a Warehouse (bin, shelf, zone). Stock levels and
    ledger entries are always recorded against a Location, never a bare
    Warehouse, so a warehouse-level total is always the sum of its locations."""

    __tablename__ = "inventory_locations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["inventory_warehouses.tenant_id", "inventory_warehouses.id"],
            ondelete="RESTRICT",
            name="fk_inventory_locations_tenant_warehouse",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_inventory_locations_tenant_id"),
        UniqueConstraint("tenant_id", "warehouse_id", "code", name="uq_inventory_location_warehouse_code"),
        CheckConstraint(
            "location_type IN ('storage','picking','staging','returns','quarantine')",
            name="ck_inventory_location_type",
        ),
        CheckConstraint("status IN ('active','archived')", name="ck_inventory_location_status"),
        CheckConstraint("version > 0", name="ck_inventory_location_version"),
        Index("ix_inventory_locations_tenant_warehouse_status", "tenant_id", "warehouse_id", "status", "id"),
    )
    warehouse_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    location_type: Mapped[str] = mapped_column(String(20), nullable=False, default="storage")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")


class StockLevelModel(InventoryResourceMixin, Base):
    """The materialized balance for one Variant at one Location. `available` is
    a Postgres STORED generated column (on_hand - reserved), so the core
    inventory invariant is enforced by the database itself and can never drift
    from the projection the way an application-maintained column could. The
    append-only ledger remains the source of truth; this table is the fast
    read model the allocation/reservation engines lock and read."""

    __tablename__ = "inventory_stock_levels"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "location_id"],
            ["inventory_locations.tenant_id", "inventory_locations.id"],
            ondelete="RESTRICT",
            name="fk_inventory_stock_levels_tenant_location",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["catalog_product_variants.tenant_id", "catalog_product_variants.id"],
            ondelete="RESTRICT",
            name="fk_inventory_stock_levels_tenant_variant",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_inventory_stock_levels_tenant_id"),
        UniqueConstraint("tenant_id", "location_id", "variant_id", name="uq_inventory_stock_level_location_variant"),
        CheckConstraint("on_hand >= 0", name="ck_inventory_stock_on_hand_nonneg"),
        CheckConstraint("reserved >= 0", name="ck_inventory_stock_reserved_nonneg"),
        CheckConstraint("incoming >= 0", name="ck_inventory_stock_incoming_nonneg"),
        CheckConstraint("reserved <= on_hand", name="ck_inventory_stock_reserved_le_on_hand"),
        CheckConstraint("version > 0", name="ck_inventory_stock_version"),
        Index("ix_inventory_stock_levels_tenant_variant", "tenant_id", "variant_id", "location_id"),
    )
    location_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    variant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    on_hand: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    reserved: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    incoming: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    available: Mapped[int] = mapped_column(BigInteger, Computed("on_hand - reserved", persisted=True))


class StockLedgerEntryModel(Base):
    """Append-only, immutable record of every stock movement. Never updated or
    deleted; a correction is a new compensating entry. This is the audited
    source of truth from which stock_levels is derived -- deliberately
    separate from AuditLogModel (a security trail) and the outbox (transient
    dispatcher state)."""

    __tablename__ = "inventory_ledger_entries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "location_id"],
            ["inventory_locations.tenant_id", "inventory_locations.id"],
            ondelete="RESTRICT",
            name="fk_inventory_ledger_tenant_location",
        ),
        CheckConstraint(
            "entry_type IN ('receipt','adjustment','transfer_in','transfer_out',"
            "'reservation_hold','reservation_release','reservation_commit','recount')",
            name="ck_inventory_ledger_entry_type",
        ),
        Index("ix_inventory_ledger_tenant_variant_created", "tenant_id", "variant_id", "created_at"),
        Index("ix_inventory_ledger_tenant_location_created", "tenant_id", "location_id", "created_at"),
        Index("ix_inventory_ledger_tenant_reference", "tenant_id", "reference_type", "reference_id"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    location_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    variant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    entry_type: Mapped[str] = mapped_column(String(30), nullable=False)
    quantity_delta: Mapped[int] = mapped_column(BigInteger, nullable=False)
    on_hand_after: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500))
    reference_type: Mapped[str | None] = mapped_column(String(50))
    reference_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TransferModel(InventoryResourceMixin, Base):
    """Moves stock of one Variant between two Locations. While `in_transit` the
    quantity is decremented from the source's on_hand and counted as
    `incoming` at the destination; on `completed` it lands in the
    destination's on_hand. Each state transition writes ledger entries, so the
    ledger fully explains any in-flight stock."""

    __tablename__ = "inventory_transfers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "from_location_id"],
            ["inventory_locations.tenant_id", "inventory_locations.id"],
            ondelete="RESTRICT",
            name="fk_inventory_transfers_tenant_from_location",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "to_location_id"],
            ["inventory_locations.tenant_id", "inventory_locations.id"],
            ondelete="RESTRICT",
            name="fk_inventory_transfers_tenant_to_location",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["catalog_product_variants.tenant_id", "catalog_product_variants.id"],
            ondelete="RESTRICT",
            name="fk_inventory_transfers_tenant_variant",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_inventory_transfers_tenant_id"),
        CheckConstraint("quantity > 0", name="ck_inventory_transfer_quantity_positive"),
        CheckConstraint("from_location_id <> to_location_id", name="ck_inventory_transfer_distinct_locations"),
        CheckConstraint(
            "status IN ('in_transit','completed','cancelled')", name="ck_inventory_transfer_status"
        ),
        CheckConstraint("version > 0", name="ck_inventory_transfer_version"),
        Index("ix_inventory_transfers_tenant_status", "tenant_id", "status", "id"),
    )
    from_location_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    to_location_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    variant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    quantity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="in_transit")


class ReservationModel(InventoryResourceMixin, Base):
    """A hold on available stock for a downstream demand (cart/order), optionally
    tagged with the selling scope it was placed for. `held` decrements
    available (increments reserved); `released` returns it; `committed`
    consumes it (converts the hold into an on_hand decrement at fulfillment).
    expires_at lets a future sweeper release stale holds."""

    __tablename__ = "inventory_reservations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "location_id"],
            ["inventory_locations.tenant_id", "inventory_locations.id"],
            ondelete="RESTRICT",
            name="fk_inventory_reservations_tenant_location",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["catalog_product_variants.tenant_id", "catalog_product_variants.id"],
            ondelete="RESTRICT",
            name="fk_inventory_reservations_tenant_variant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "store_id"],
            ["platform_stores.tenant_id", "platform_stores.id"],
            ondelete="RESTRICT",
            name="fk_inventory_reservations_tenant_store",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "channel_id"],
            ["platform_channels.tenant_id", "platform_channels.id"],
            ondelete="RESTRICT",
            name="fk_inventory_reservations_tenant_channel",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "market_id"],
            ["platform_markets.tenant_id", "platform_markets.id"],
            ondelete="RESTRICT",
            name="fk_inventory_reservations_tenant_market",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_inventory_reservations_tenant_id"),
        CheckConstraint("quantity > 0", name="ck_inventory_reservation_quantity_positive"),
        CheckConstraint("status IN ('held','released','committed')", name="ck_inventory_reservation_status"),
        CheckConstraint(
            "scope_type IS NULL OR scope_type IN ('store','channel','market')",
            name="ck_inventory_reservation_scope_type",
        ),
        CheckConstraint("version > 0", name="ck_inventory_reservation_version"),
        Index("ix_inventory_reservations_tenant_variant_status", "tenant_id", "variant_id", "status"),
        Index("ix_inventory_reservations_tenant_reference", "tenant_id", "reference_type", "reference_id"),
        Index("ix_inventory_reservations_tenant_status_expiry", "tenant_id", "status", "expires_at"),
    )
    variant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    location_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    quantity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    scope_type: Mapped[str | None] = mapped_column(String(20))
    store_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    channel_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    market_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    reference_type: Mapped[str | None] = mapped_column(String(50))
    reference_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="held")


class FulfillmentScopeModel(InventoryResourceMixin, Base):
    """Declares that a Warehouse serves a selling scope (Store, Channel or
    Market) at a given priority. This is the integration seam with Platform:
    the allocation engine, given a demand for a scope, walks the warehouses
    mapped to it in priority order. Mutually-exclusive scope columns backed by
    composite FKs to the Kernel, same posture as pricing assignments."""

    __tablename__ = "inventory_fulfillment_scopes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["inventory_warehouses.tenant_id", "inventory_warehouses.id"],
            ondelete="RESTRICT",
            name="fk_inventory_fulfillment_scopes_tenant_warehouse",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "store_id"],
            ["platform_stores.tenant_id", "platform_stores.id"],
            ondelete="RESTRICT",
            name="fk_inventory_fulfillment_scopes_tenant_store",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "channel_id"],
            ["platform_channels.tenant_id", "platform_channels.id"],
            ondelete="RESTRICT",
            name="fk_inventory_fulfillment_scopes_tenant_channel",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "market_id"],
            ["platform_markets.tenant_id", "platform_markets.id"],
            ondelete="RESTRICT",
            name="fk_inventory_fulfillment_scopes_tenant_market",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_inventory_fulfillment_scopes_tenant_id"),
        CheckConstraint("scope_type IN ('store','channel','market')", name="ck_inventory_fulfillment_scope_type"),
        CheckConstraint(_SCOPE_COLUMNS_CHECK, name="ck_inventory_fulfillment_scope_columns"),
        CheckConstraint("status IN ('active','archived')", name="ck_inventory_fulfillment_scope_status"),
        CheckConstraint("version > 0", name="ck_inventory_fulfillment_scope_version"),
        Index("ix_inventory_fulfillment_scopes_store", "tenant_id", "store_id", "status", "priority"),
        Index("ix_inventory_fulfillment_scopes_channel", "tenant_id", "channel_id", "status", "priority"),
        Index("ix_inventory_fulfillment_scopes_market", "tenant_id", "market_id", "status", "priority"),
        Index("ix_inventory_fulfillment_scopes_warehouse", "tenant_id", "warehouse_id", "status"),
    )
    warehouse_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(20), nullable=False)
    store_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    channel_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    market_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")


__all__ = [
    "FulfillmentScopeModel",
    "InventoryResourceMixin",
    "LocationModel",
    "ReservationModel",
    "StockLedgerEntryModel",
    "StockLevelModel",
    "TransferModel",
    "WarehouseModel",
]

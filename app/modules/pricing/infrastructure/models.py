from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.models import Base


class PricingResourceMixin:
    """Same shape as catalog.infrastructure.models.CatalogResourceMixin -- tenant
    ownership, optimistic version, and audit timestamps are identical across
    every tenant-owned, versioned resource in Nexus regardless of module."""

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


class PriceListModel(PricingResourceMixin, Base):
    """A named, currency-scoped container of per-Variant prices. Multi-currency
    support is achieved by having one PriceList per currency (the same pattern
    Shopify/VTEX/BigCommerce use), never by mixing currencies inside one list --
    every amount in a PriceList is unambiguous without a per-row currency."""

    __tablename__ = "pricing_price_lists"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_pricing_price_lists_tenant_id"),
        UniqueConstraint("tenant_id", "code", name="uq_pricing_price_lists_tenant_code"),
        CheckConstraint("status IN ('draft','active','archived')", name="ck_pricing_price_list_status"),
        CheckConstraint("version > 0", name="ck_pricing_price_list_version"),
        Index("ix_pricing_price_lists_tenant_status", "tenant_id", "status", "id"),
        Index(
            "uq_pricing_price_list_default",
            "tenant_id",
            unique=True,
            postgresql_where=text("is_default AND status <> 'archived'"),
        ),
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(String(2000))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")


class PriceListEntryModel(PricingResourceMixin, Base):
    """The actual price row for one Variant inside one PriceList: base price,
    compare-at, MSRP, and cost. This is deliberately per-Variant, never
    per-Product -- Nexus's Catalog already requires every Product to have at
    least one Variant (see CatalogResourceMixin's ProductVariantModel), so
    pricing at the Variant level is the only granularity that is always
    unambiguous."""

    __tablename__ = "pricing_price_list_entries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "price_list_id"],
            ["pricing_price_lists.tenant_id", "pricing_price_lists.id"],
            ondelete="RESTRICT",
            name="fk_pricing_price_list_entries_tenant_price_list",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["catalog_product_variants.tenant_id", "catalog_product_variants.id"],
            ondelete="RESTRICT",
            name="fk_pricing_price_list_entries_tenant_variant",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_pricing_price_list_entries_tenant_id"),
        UniqueConstraint(
            "tenant_id", "price_list_id", "variant_id", name="uq_pricing_price_list_entry_variant"
        ),
        CheckConstraint("unit_amount >= 0", name="ck_pricing_price_list_entry_unit_amount"),
        CheckConstraint(
            "compare_at_amount IS NULL OR compare_at_amount >= 0",
            name="ck_pricing_price_list_entry_compare_at_amount",
        ),
        CheckConstraint(
            "msrp_amount IS NULL OR msrp_amount >= 0", name="ck_pricing_price_list_entry_msrp_amount"
        ),
        CheckConstraint(
            "cost_amount IS NULL OR cost_amount >= 0", name="ck_pricing_price_list_entry_cost_amount"
        ),
        CheckConstraint("status IN ('active','archived')", name="ck_pricing_price_list_entry_status"),
        CheckConstraint("version > 0", name="ck_pricing_price_list_entry_version"),
        Index("ix_pricing_price_list_entries_tenant_list_status", "tenant_id", "price_list_id", "status"),
        Index("ix_pricing_price_list_entries_tenant_variant_status", "tenant_id", "variant_id", "status"),
    )
    price_list_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    variant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    unit_amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    compare_at_amount: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    msrp_amount: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    cost_amount: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")


class PriceListAssignmentModel(PricingResourceMixin, Base):
    """Assigns a PriceList to a Store, Channel, or Market -- the effective-date
    window and priority double as both "reglas de vigencia" and "prioridad de
    reglas": the resolution engine (domain/values.py) picks the
    highest-priority assignment whose window covers the resolution instant.

    The three scope FKs are nullable and mutually exclusive (see
    _SCOPE_COLUMNS_CHECK) rather than one polymorphic column, so referential
    integrity to Platform Kernel's tables is enforced by Postgres itself, not
    by application code re-checking existence -- the same posture Catalog
    already takes with ProductStoreModel's FK to platform_stores."""

    __tablename__ = "pricing_price_list_assignments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "price_list_id"],
            ["pricing_price_lists.tenant_id", "pricing_price_lists.id"],
            ondelete="RESTRICT",
            name="fk_pricing_assignments_tenant_price_list",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "store_id"],
            ["platform_stores.tenant_id", "platform_stores.id"],
            ondelete="RESTRICT",
            name="fk_pricing_assignments_tenant_store",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "channel_id"],
            ["platform_channels.tenant_id", "platform_channels.id"],
            ondelete="RESTRICT",
            name="fk_pricing_assignments_tenant_channel",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "market_id"],
            ["platform_markets.tenant_id", "platform_markets.id"],
            ondelete="RESTRICT",
            name="fk_pricing_assignments_tenant_market",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_pricing_assignments_tenant_id"),
        CheckConstraint("scope_type IN ('store','channel','market')", name="ck_pricing_assignment_scope_type"),
        CheckConstraint(_SCOPE_COLUMNS_CHECK, name="ck_pricing_assignment_scope_columns"),
        CheckConstraint(
            "effective_until IS NULL OR effective_from IS NULL OR effective_until > effective_from",
            name="ck_pricing_assignment_window",
        ),
        CheckConstraint("status IN ('active','archived')", name="ck_pricing_assignment_status"),
        CheckConstraint("version > 0", name="ck_pricing_assignment_version"),
        Index("ix_pricing_assignments_tenant_store_status", "tenant_id", "store_id", "status", "priority"),
        Index("ix_pricing_assignments_tenant_channel_status", "tenant_id", "channel_id", "status", "priority"),
        Index("ix_pricing_assignments_tenant_market_status", "tenant_id", "market_id", "status", "priority"),
        Index("ix_pricing_assignments_tenant_list_status", "tenant_id", "price_list_id", "status"),
    )
    price_list_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(20), nullable=False)
    store_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    channel_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    market_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")


class VariantPriceOverrideModel(PricingResourceMixin, Base):
    """A targeted price exception for one Variant at one scope that bypasses
    PriceList resolution entirely -- the "Overrides" requirement, functionally
    equivalent to what PrestaShop calls a specific_price, redesigned in
    Nexus's own tenant/RLS/versioning shape rather than copied. Carries its
    own currency because it is not backed by any PriceList."""

    __tablename__ = "pricing_variant_price_overrides"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["catalog_product_variants.tenant_id", "catalog_product_variants.id"],
            ondelete="RESTRICT",
            name="fk_pricing_overrides_tenant_variant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "store_id"],
            ["platform_stores.tenant_id", "platform_stores.id"],
            ondelete="RESTRICT",
            name="fk_pricing_overrides_tenant_store",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "channel_id"],
            ["platform_channels.tenant_id", "platform_channels.id"],
            ondelete="RESTRICT",
            name="fk_pricing_overrides_tenant_channel",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "market_id"],
            ["platform_markets.tenant_id", "platform_markets.id"],
            ondelete="RESTRICT",
            name="fk_pricing_overrides_tenant_market",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_pricing_overrides_tenant_id"),
        CheckConstraint("scope_type IN ('store','channel','market')", name="ck_pricing_override_scope_type"),
        CheckConstraint(_SCOPE_COLUMNS_CHECK, name="ck_pricing_override_scope_columns"),
        CheckConstraint("unit_amount >= 0", name="ck_pricing_override_unit_amount"),
        CheckConstraint(
            "compare_at_amount IS NULL OR compare_at_amount >= 0", name="ck_pricing_override_compare_at_amount"
        ),
        CheckConstraint(
            "effective_until IS NULL OR effective_from IS NULL OR effective_until > effective_from",
            name="ck_pricing_override_window",
        ),
        CheckConstraint("status IN ('active','archived')", name="ck_pricing_override_status"),
        CheckConstraint("version > 0", name="ck_pricing_override_version"),
        Index(
            "ix_pricing_overrides_tenant_variant_scope_status",
            "tenant_id",
            "variant_id",
            "scope_type",
            "status",
            "priority",
        ),
    )
    variant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(20), nullable=False)
    store_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    channel_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    market_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    unit_amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    compare_at_amount: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")


class PriceHistoryModel(Base):
    """Append-only ledger of every amount change to a PriceListEntry or a
    VariantPriceOverride, one row per changed field. Deliberately separate
    from AuditLogModel (which is a security/access trail, not a queryable
    price timeline a merchandiser would want a table view of) and from the
    outbox (which is transient dispatcher state, not durable history)."""

    __tablename__ = "pricing_price_history"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('price_list_entry','variant_price_override')", name="ck_pricing_history_entity_type"
        ),
        Index("ix_pricing_history_tenant_variant_changed", "tenant_id", "variant_id", "changed_at"),
        Index("ix_pricing_history_tenant_entity", "tenant_id", "entity_type", "entity_id", "changed_at"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    variant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    field_name: Mapped[str] = mapped_column(String(30), nullable=False)
    previous_amount: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    new_amount: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    changed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500))


__all__ = [
    "PriceHistoryModel",
    "PriceListAssignmentModel",
    "PriceListEntryModel",
    "PriceListModel",
    "PricingResourceMixin",
    "VariantPriceOverrideModel",
]

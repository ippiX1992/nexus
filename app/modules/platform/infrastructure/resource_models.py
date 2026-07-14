from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    String,
    Table,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.models import Base


class StoreModel(Base):
    __tablename__ = "platform_stores"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_platform_stores_tenant_id"),
        UniqueConstraint("tenant_id", "code", name="uq_platform_stores_tenant_code"),
        UniqueConstraint("tenant_id", "slug", name="uq_platform_stores_tenant_slug"),
        CheckConstraint("status IN ('draft','active','suspended','archived')", name="ck_platform_store_status"),
        Index("ix_platform_stores_tenant_status", "tenant_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="draft")
    default_locale: Mapped[str] = mapped_column(String(35))
    default_currency: Mapped[str] = mapped_column(String(3))
    timezone: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class SiteModel(Base):
    __tablename__ = "platform_sites"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "store_id"], ["platform_stores.tenant_id", "platform_stores.id"], ondelete="CASCADE", name="fk_platform_sites_tenant_store"),
        UniqueConstraint("tenant_id", "id", name="uq_platform_sites_tenant_id"),
        UniqueConstraint("tenant_id", "store_id", "code", name="uq_platform_sites_store_code"),
        UniqueConstraint("tenant_id", "store_id", "slug", name="uq_platform_sites_store_slug"),
        CheckConstraint("site_type IN ('commerce','content','landing','portal')", name="ck_platform_site_type"),
        CheckConstraint("status IN ('draft','active','archived')", name="ck_platform_site_status"),
        Index("ix_platform_sites_tenant_store", "tenant_id", "store_id"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    store_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(100))
    site_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="draft")
    primary_domain_placeholder: Mapped[str | None] = mapped_column(String(253))
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class ChannelModel(Base):
    __tablename__ = "platform_channels"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "store_id"], ["platform_stores.tenant_id", "platform_stores.id"], ondelete="CASCADE", name="fk_platform_channels_tenant_store"),
        UniqueConstraint("tenant_id", "id", name="uq_platform_channels_tenant_id"),
        UniqueConstraint("tenant_id", "store_id", "code", name="uq_platform_channels_store_code"),
        CheckConstraint("channel_type IN ('web','mobile','marketplace','b2b','social','pos','api')", name="ck_platform_channel_type"),
        CheckConstraint("status IN ('draft','active','archived')", name="ck_platform_channel_status"),
        Index("ix_platform_channels_tenant_store", "tenant_id", "store_id"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    store_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(160))
    channel_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class EnvironmentModel(Base):
    __tablename__ = "platform_environments"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "store_id"], ["platform_stores.tenant_id", "platform_stores.id"], ondelete="CASCADE", name="fk_platform_environments_tenant_store"),
        UniqueConstraint("tenant_id", "id", name="uq_platform_environments_tenant_id"),
        UniqueConstraint("tenant_id", "store_id", "code", name="uq_platform_environments_store_code"),
        CheckConstraint("environment_type IN ('development','preview','staging','production')", name="ck_platform_environment_type"),
        CheckConstraint("status IN ('active','archived')", name="ck_platform_environment_status"),
        CheckConstraint("(environment_type = 'production') = is_production", name="ck_platform_environment_production_flag"),
        Index("ix_platform_environments_tenant_store", "tenant_id", "store_id"),
        Index("uq_platform_environment_primary_production", "tenant_id", "store_id", unique=True, postgresql_where=text("is_production AND status <> 'archived'")),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    store_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(160))
    environment_type: Mapped[str] = mapped_column(String(20))
    is_production: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class MarketModel(Base):
    __tablename__ = "platform_markets"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "store_id"], ["platform_stores.tenant_id", "platform_stores.id"], ondelete="CASCADE", name="fk_platform_markets_tenant_store"),
        UniqueConstraint("tenant_id", "id", name="uq_platform_markets_tenant_id"),
        UniqueConstraint("tenant_id", "store_id", "code", name="uq_platform_markets_store_code"),
        CheckConstraint("status IN ('draft','active','archived')", name="ck_platform_market_status"),
        Index("ix_platform_markets_tenant_store", "tenant_id", "store_id"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    store_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(160))
    country_code: Mapped[str] = mapped_column(String(2))
    currency_code: Mapped[str] = mapped_column(String(3))
    default_locale: Mapped[str] = mapped_column(String(35))
    timezone: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class StoreLocaleModel(Base):
    __tablename__ = "platform_store_locales"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "store_id"], ["platform_stores.tenant_id", "platform_stores.id"], ondelete="CASCADE"),
        Index("ix_platform_store_locales_tenant_store", "tenant_id", "store_id"),
        Index("uq_platform_store_default_locale", "tenant_id", "store_id", unique=True, postgresql_where=text("is_default")),
    )
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    store_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    locale_code: Mapped[str] = mapped_column(String(35), primary_key=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


class StoreCurrencyModel(Base):
    __tablename__ = "platform_store_currencies"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "store_id"], ["platform_stores.tenant_id", "platform_stores.id"], ondelete="CASCADE"),
        CheckConstraint("minor_unit BETWEEN 0 AND 4", name="ck_platform_store_currency_minor_unit"),
        Index("ix_platform_store_currencies_tenant_store", "tenant_id", "store_id"),
        Index("uq_platform_store_default_currency", "tenant_id", "store_id", unique=True, postgresql_where=text("is_default")),
    )
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    store_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    currency_code: Mapped[str] = mapped_column(String(3), primary_key=True)
    minor_unit: Mapped[int] = mapped_column(SmallInteger)
    rounding_mode: Mapped[str] = mapped_column(String(24), default="ROUND_HALF_EVEN")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


class MarketLocaleModel(Base):
    __tablename__ = "platform_market_locales"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "market_id"], ["platform_markets.tenant_id", "platform_markets.id"], ondelete="CASCADE"),
        Index("ix_platform_market_locales_tenant_market", "tenant_id", "market_id"),
    )
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    market_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    locale_code: Mapped[str] = mapped_column(String(35), primary_key=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


class MarketCurrencyModel(Base):
    __tablename__ = "platform_market_currencies"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "market_id"], ["platform_markets.tenant_id", "platform_markets.id"], ondelete="CASCADE"),
        CheckConstraint("minor_unit BETWEEN 0 AND 4", name="ck_platform_market_currency_minor_unit"),
        Index("ix_platform_market_currencies_tenant_market", "tenant_id", "market_id"),
    )
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    market_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    currency_code: Mapped[str] = mapped_column(String(3), primary_key=True)
    minor_unit: Mapped[int] = mapped_column(SmallInteger)
    rounding_mode: Mapped[str] = mapped_column(String(24), default="ROUND_HALF_EVEN")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


channel_sites = Table(
    "platform_channel_sites", Base.metadata,
    Column("tenant_id", PGUUID(as_uuid=True), primary_key=True),
    Column("channel_id", PGUUID(as_uuid=True), primary_key=True),
    Column("site_id", PGUUID(as_uuid=True), primary_key=True),
    ForeignKeyConstraint(["tenant_id", "channel_id"], ["platform_channels.tenant_id", "platform_channels.id"], ondelete="CASCADE"),
    ForeignKeyConstraint(["tenant_id", "site_id"], ["platform_sites.tenant_id", "platform_sites.id"], ondelete="CASCADE"),
    Index("ix_platform_channel_sites_tenant_channel", "tenant_id", "channel_id"),
)
channel_markets = Table(
    "platform_channel_markets", Base.metadata,
    Column("tenant_id", PGUUID(as_uuid=True), primary_key=True),
    Column("channel_id", PGUUID(as_uuid=True), primary_key=True),
    Column("market_id", PGUUID(as_uuid=True), primary_key=True),
    ForeignKeyConstraint(["tenant_id", "channel_id"], ["platform_channels.tenant_id", "platform_channels.id"], ondelete="CASCADE"),
    ForeignKeyConstraint(["tenant_id", "market_id"], ["platform_markets.tenant_id", "platform_markets.id"], ondelete="CASCADE"),
    Index("ix_platform_channel_markets_tenant_channel", "tenant_id", "channel_id"),
)
channel_environments = Table(
    "platform_channel_environments", Base.metadata,
    Column("tenant_id", PGUUID(as_uuid=True), primary_key=True),
    Column("channel_id", PGUUID(as_uuid=True), primary_key=True),
    Column("environment_id", PGUUID(as_uuid=True), primary_key=True),
    ForeignKeyConstraint(["tenant_id", "channel_id"], ["platform_channels.tenant_id", "platform_channels.id"], ondelete="CASCADE"),
    ForeignKeyConstraint(["tenant_id", "environment_id"], ["platform_environments.tenant_id", "platform_environments.id"], ondelete="CASCADE"),
    Index("ix_platform_channel_environments_tenant_channel", "tenant_id", "channel_id"),
)


class ResourceScopeModel(Base):
    __tablename__ = "platform_resource_scopes"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "parent_scope_id"], ["platform_resource_scopes.tenant_id", "platform_resource_scopes.id"], ondelete="CASCADE"),
        UniqueConstraint("tenant_id", "id", name="uq_platform_resource_scopes_tenant_id"),
        UniqueConstraint("tenant_id", "scope_type", "resource_id", name="uq_platform_resource_scope_resource"),
        CheckConstraint("scope_type IN ('tenant','store','site','channel','environment','market')", name="ck_platform_scope_type"),
        CheckConstraint("status IN ('active','archived')", name="ck_platform_scope_status"),
        Index("ix_platform_resource_scopes_tenant_parent", "tenant_id", "parent_scope_id"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    scope_type: Mapped[str] = mapped_column(String(20))
    resource_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    parent_scope_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(20), default="active")

"""Platform Kernel schema, explicit RBAC seeds and forced RLS.

Revision ID: 0002
Revises: 0001
"""

from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

PLATFORM_PERMISSIONS = (
    "store.read", "store.create", "store.update", "store.archive",
    "site.read", "site.create", "site.update", "site.archive",
    "channel.read", "channel.create", "channel.update", "channel.archive",
    "environment.read", "environment.create", "environment.update", "environment.archive",
    "market.read", "market.create", "market.update", "market.archive",
    "operation.read", "entitlement.read", "entitlement.manage",
)

TENANT_TABLES = (
    "platform_stores", "platform_sites", "platform_channels", "platform_environments",
    "platform_markets", "platform_store_locales", "platform_store_currencies",
    "platform_market_locales", "platform_market_currencies", "platform_channel_sites",
    "platform_channel_markets", "platform_channel_environments", "platform_resource_scopes",
    "platform_outbox_events", "platform_inbox_events", "platform_idempotency_records",
    "platform_operations", "platform_jobs", "platform_entitlement_overrides",
)


def _resource_columns(include_archive: bool = True) -> list[sa.Column]:
    columns = [
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]
    if include_archive:
        columns.append(sa.Column("archived_at", sa.DateTime(timezone=True)))
    return columns


def _create_rls(table: str) -> None:
    predicate = "tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid"
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY {table}_select ON {table} FOR SELECT USING ({predicate})")
    op.execute(f"CREATE POLICY {table}_insert ON {table} FOR INSERT WITH CHECK ({predicate})")
    op.execute(f"CREATE POLICY {table}_update ON {table} FOR UPDATE USING ({predicate}) WITH CHECK ({predicate})")
    op.execute(f"CREATE POLICY {table}_delete ON {table} FOR DELETE USING ({predicate})")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO nexus_app")


def upgrade() -> None:
    op.create_table(
        "platform_stores",
        *_resource_columns(),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("default_locale", sa.String(35), nullable=False),
        sa.Column("default_currency", sa.String(3), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_platform_stores_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_platform_stores_tenant_code"),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_platform_stores_tenant_slug"),
        sa.CheckConstraint("status IN ('draft','active','suspended','archived')", name="ck_platform_store_status"),
    )
    op.create_index("ix_platform_stores_tenant_status", "platform_stores", ["tenant_id", "status"])

    op.create_table(
        "platform_sites",
        *_resource_columns(),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("site_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("primary_domain_placeholder", sa.String(253)),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.ForeignKeyConstraint(["tenant_id", "store_id"], ["platform_stores.tenant_id", "platform_stores.id"], ondelete="CASCADE", name="fk_platform_sites_tenant_store"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_platform_sites_tenant_id"),
        sa.UniqueConstraint("tenant_id", "store_id", "code", name="uq_platform_sites_store_code"),
        sa.UniqueConstraint("tenant_id", "store_id", "slug", name="uq_platform_sites_store_slug"),
        sa.CheckConstraint("site_type IN ('commerce','content','landing','portal')", name="ck_platform_site_type"),
        sa.CheckConstraint("status IN ('draft','active','archived')", name="ck_platform_site_status"),
    )
    op.create_index("ix_platform_sites_tenant_store", "platform_sites", ["tenant_id", "store_id"])

    op.create_table(
        "platform_channels",
        *_resource_columns(),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("channel_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.ForeignKeyConstraint(["tenant_id", "store_id"], ["platform_stores.tenant_id", "platform_stores.id"], ondelete="CASCADE", name="fk_platform_channels_tenant_store"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_platform_channels_tenant_id"),
        sa.UniqueConstraint("tenant_id", "store_id", "code", name="uq_platform_channels_store_code"),
        sa.CheckConstraint("channel_type IN ('web','mobile','marketplace','b2b','social','pos','api')", name="ck_platform_channel_type"),
        sa.CheckConstraint("status IN ('draft','active','archived')", name="ck_platform_channel_status"),
    )
    op.create_index("ix_platform_channels_tenant_store", "platform_channels", ["tenant_id", "store_id"])

    op.create_table(
        "platform_environments",
        *_resource_columns(),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("environment_type", sa.String(20), nullable=False),
        sa.Column("is_production", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.ForeignKeyConstraint(["tenant_id", "store_id"], ["platform_stores.tenant_id", "platform_stores.id"], ondelete="CASCADE", name="fk_platform_environments_tenant_store"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_platform_environments_tenant_id"),
        sa.UniqueConstraint("tenant_id", "store_id", "code", name="uq_platform_environments_store_code"),
        sa.CheckConstraint("environment_type IN ('development','preview','staging','production')", name="ck_platform_environment_type"),
        sa.CheckConstraint("status IN ('active','archived')", name="ck_platform_environment_status"),
        sa.CheckConstraint("(environment_type = 'production') = is_production", name="ck_platform_environment_production_flag"),
    )
    op.create_index("ix_platform_environments_tenant_store", "platform_environments", ["tenant_id", "store_id"])
    op.create_index("uq_platform_environment_primary_production", "platform_environments", ["tenant_id", "store_id"], unique=True, postgresql_where=sa.text("is_production AND status <> 'archived'"))

    op.create_table(
        "platform_markets",
        *_resource_columns(),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("default_locale", sa.String(35), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.ForeignKeyConstraint(["tenant_id", "store_id"], ["platform_stores.tenant_id", "platform_stores.id"], ondelete="CASCADE", name="fk_platform_markets_tenant_store"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_platform_markets_tenant_id"),
        sa.UniqueConstraint("tenant_id", "store_id", "code", name="uq_platform_markets_store_code"),
        sa.CheckConstraint("status IN ('draft','active','archived')", name="ck_platform_market_status"),
    )
    op.create_index("ix_platform_markets_tenant_store", "platform_markets", ["tenant_id", "store_id"])

    op.create_table(
        "platform_store_locales",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("locale_code", sa.String(35), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["tenant_id", "store_id"], ["platform_stores.tenant_id", "platform_stores.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id", "store_id", "locale_code"),
    )
    op.create_index("ix_platform_store_locales_tenant_store", "platform_store_locales", ["tenant_id", "store_id"])
    op.create_index("uq_platform_store_default_locale", "platform_store_locales", ["tenant_id", "store_id"], unique=True, postgresql_where=sa.text("is_default"))

    op.create_table(
        "platform_store_currencies",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("minor_unit", sa.SmallInteger(), nullable=False),
        sa.Column("rounding_mode", sa.String(24), nullable=False, server_default="ROUND_HALF_EVEN"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["tenant_id", "store_id"], ["platform_stores.tenant_id", "platform_stores.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id", "store_id", "currency_code"),
        sa.CheckConstraint("minor_unit BETWEEN 0 AND 4", name="ck_platform_store_currency_minor_unit"),
    )
    op.create_index("ix_platform_store_currencies_tenant_store", "platform_store_currencies", ["tenant_id", "store_id"])
    op.create_index("uq_platform_store_default_currency", "platform_store_currencies", ["tenant_id", "store_id"], unique=True, postgresql_where=sa.text("is_default"))

    op.create_table(
        "platform_market_locales",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("market_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("locale_code", sa.String(35), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["tenant_id", "market_id"], ["platform_markets.tenant_id", "platform_markets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id", "market_id", "locale_code"),
    )
    op.create_index("ix_platform_market_locales_tenant_market", "platform_market_locales", ["tenant_id", "market_id"])

    op.create_table(
        "platform_market_currencies",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("market_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("minor_unit", sa.SmallInteger(), nullable=False),
        sa.Column("rounding_mode", sa.String(24), nullable=False, server_default="ROUND_HALF_EVEN"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["tenant_id", "market_id"], ["platform_markets.tenant_id", "platform_markets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id", "market_id", "currency_code"),
        sa.CheckConstraint("minor_unit BETWEEN 0 AND 4", name="ck_platform_market_currency_minor_unit"),
    )
    op.create_index("ix_platform_market_currencies_tenant_market", "platform_market_currencies", ["tenant_id", "market_id"])

    for name, left, right in (
        ("platform_channel_sites", "site", "platform_sites"),
        ("platform_channel_markets", "market", "platform_markets"),
        ("platform_channel_environments", "environment", "platform_environments"),
    ):
        right_id = f"{left}_id"
        op.create_table(
            name,
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("channel_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(right_id, postgresql.UUID(as_uuid=True), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id", "channel_id"], ["platform_channels.tenant_id", "platform_channels.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["tenant_id", right_id], [f"{right}.tenant_id", f"{right}.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("tenant_id", "channel_id", right_id),
        )
        op.create_index(f"ix_{name}_tenant_channel", name, ["tenant_id", "channel_id"])

    op.create_table(
        "platform_resource_scopes",
        *_resource_columns(include_archive=False),
        sa.Column("scope_type", sa.String(20), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_scope_id", postgresql.UUID(as_uuid=True)),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.ForeignKeyConstraint(["tenant_id", "parent_scope_id"], ["platform_resource_scopes.tenant_id", "platform_resource_scopes.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_platform_resource_scopes_tenant_id"),
        sa.UniqueConstraint("tenant_id", "scope_type", "resource_id", name="uq_platform_resource_scope_resource"),
        sa.CheckConstraint("scope_type IN ('tenant','store','site','channel','environment','market')", name="ck_platform_scope_type"),
        sa.CheckConstraint("status IN ('active','archived')", name="ck_platform_scope_status"),
    )
    op.create_index("ix_platform_resource_scopes_tenant_parent", "platform_resource_scopes", ["tenant_id", "parent_scope_id"])

    op.create_table(
        "platform_outbox_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("store_id", postgresql.UUID(as_uuid=True)),
        sa.Column("aggregate_type", sa.String(64), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(160), nullable=False),
        sa.Column("event_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("causation_id", postgresql.UUID(as_uuid=True)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(500)),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.ForeignKeyConstraint(["tenant_id", "store_id"], ["platform_stores.tenant_id", "platform_stores.id"], ondelete="CASCADE"),
        sa.CheckConstraint("status IN ('pending','processing','published','failed','dead_letter')", name="ck_platform_outbox_status"),
    )
    op.create_index("ix_platform_outbox_claim", "platform_outbox_events", ["tenant_id", "status", "available_at"])

    op.create_table(
        "platform_inbox_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("consumer_name", sa.String(120), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(160), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20), nullable=False, server_default="processing"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_error", sa.String(500)),
        sa.UniqueConstraint("consumer_name", "event_id", name="uq_platform_inbox_consumer_event"),
        sa.CheckConstraint("status IN ('processing','processed','failed')", name="ck_platform_inbox_status"),
    )
    op.create_index("ix_platform_inbox_tenant_status", "platform_inbox_events", ["tenant_id", "status"])

    op.create_table(
        "platform_idempotency_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(200), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("endpoint", sa.String(300), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="processing"),
        sa.Column("response_body", postgresql.JSONB()),
        sa.Column("response_code", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "actor_id", "method", "endpoint", "key", name="uq_platform_idempotency_operation"),
        sa.CheckConstraint("status IN ('processing','completed','failed')", name="ck_platform_idempotency_status"),
    )
    op.create_index("ix_platform_idempotency_tenant_expiry", "platform_idempotency_records", ["tenant_id", "expires_at"])

    op.create_table(
        "platform_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("operation_type", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message", sa.String(500)),
        sa.Column("result", postgresql.JSONB()),
        sa.Column("error", sa.String(500)),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "id", name="uq_platform_operations_tenant_id"),
        sa.CheckConstraint("status IN ('queued','running','succeeded','failed','cancelled')", name="ck_platform_operation_status"),
        sa.CheckConstraint("progress BETWEEN 0 AND 100", name="ck_platform_operation_progress"),
    )
    op.create_index("ix_platform_operations_tenant_created", "platform_operations", ["tenant_id", "created_at"])

    op.create_table(
        "platform_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("operation_id", postgresql.UUID(as_uuid=True)),
        sa.Column("job_type", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(500)),
        sa.Column("lock_owner", sa.String(120)),
        sa.Column("lock_expires_at", sa.DateTime(timezone=True)),
        sa.Column("idempotency_key", sa.String(200)),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id", "operation_id"], ["platform_operations.tenant_id", "platform_operations.id"], ondelete="SET NULL"),
        sa.CheckConstraint("status IN ('queued','running','succeeded','failed','cancelled','dead_letter')", name="ck_platform_job_status"),
        sa.CheckConstraint("max_attempts > 0 AND attempts >= 0", name="ck_platform_job_attempts"),
    )
    op.create_index("ix_platform_jobs_claim", "platform_jobs", ["tenant_id", "status", "scheduled_at", "lock_expires_at"])
    op.create_index("uq_platform_jobs_idempotency", "platform_jobs", ["tenant_id", "job_type", "idempotency_key"], unique=True, postgresql_where=sa.text("idempotency_key IS NOT NULL"))

    op.create_table(
        "platform_entitlement_definitions",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("default_value", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.CheckConstraint("default_value >= 0", name="ck_platform_entitlement_default"),
    )
    op.create_table(
        "platform_entitlement_overrides",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(100), sa.ForeignKey("platform_entitlement_definitions.key", ondelete="CASCADE"), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "key"),
        sa.CheckConstraint("value >= 0", name="ck_platform_entitlement_override"),
    )
    op.create_index("ix_platform_entitlement_overrides_tenant", "platform_entitlement_overrides", ["tenant_id", "key"])

    definitions = sa.table("platform_entitlement_definitions", sa.column("key", sa.String()), sa.column("default_value", sa.Integer()), sa.column("description", sa.String()))
    op.bulk_insert(definitions, [
        {"key": "stores.max", "default_value": 10, "description": "Maximum stores per tenant"},
        {"key": "sites.max_per_store", "default_value": 10, "description": "Maximum sites per store"},
        {"key": "channels.max_per_store", "default_value": 10, "description": "Maximum sales channels per store"},
        {"key": "markets.max_per_store", "default_value": 20, "description": "Maximum markets per store"},
        {"key": "environments.max_per_store", "default_value": 4, "description": "Maximum environments per store"},
        {"key": "users.max", "default_value": 100, "description": "Maximum active members per tenant"},
    ])

    permission_table = sa.table("permissions", sa.column("id", postgresql.UUID(as_uuid=True)), sa.column("code", sa.String()))
    op.bulk_insert(permission_table, [{"id": uuid4(), "code": code} for code in PLATFORM_PERMISSIONS])
    role_grants = {
        "owner": PLATFORM_PERMISSIONS,
        "admin": PLATFORM_PERMISSIONS,
        "manager": tuple(p for p in PLATFORM_PERMISSIONS if not p.endswith(".archive") and p != "entitlement.manage"),
        "editor": ("store.read", "site.read", "channel.read", "environment.read", "market.read", "operation.read", "entitlement.read"),
        "analyst": ("store.read", "site.read", "channel.read", "environment.read", "market.read", "operation.read", "entitlement.read"),
        "viewer": ("store.read", "site.read", "channel.read", "environment.read", "market.read", "operation.read", "entitlement.read"),
    }
    bind = op.get_bind()
    for role_name, codes in role_grants.items():
        bind.execute(sa.text("""
            INSERT INTO role_permissions(role_id, permission_id)
            SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
            WHERE r.is_system IS TRUE AND r.name = :role_name AND p.code = ANY(:codes)
            ON CONFLICT DO NOTHING
        """), {"role_name": role_name, "codes": list(codes)})

    op.execute("GRANT SELECT ON platform_entitlement_definitions TO nexus_app")
    for table in TENANT_TABLES:
        _create_rls(table)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code = ANY(:codes))"), {"codes": list(PLATFORM_PERMISSIONS)})
    bind.execute(sa.text("DELETE FROM permissions WHERE code = ANY(:codes)"), {"codes": list(PLATFORM_PERMISSIONS)})
    for table in (
        "platform_entitlement_overrides", "platform_entitlement_definitions", "platform_jobs",
        "platform_operations", "platform_idempotency_records", "platform_inbox_events",
        "platform_outbox_events", "platform_resource_scopes", "platform_channel_environments",
        "platform_channel_markets", "platform_channel_sites", "platform_market_currencies",
        "platform_market_locales", "platform_store_currencies", "platform_store_locales",
        "platform_markets", "platform_environments", "platform_channels", "platform_sites",
        "platform_stores",
    ):
        op.drop_table(table)

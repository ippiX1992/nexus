"""Pricing Engine (M4.0): Price Lists, Assignments, Variant Overrides, History, RBAC and forced RLS.

Revision ID: 0006
Revises: 0005
"""

from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

PRICING_PERMISSIONS = (
    "pricing.price_list.read",
    "pricing.price_list.create",
    "pricing.price_list.update",
    "pricing.price_list.archive",
    "pricing.price_list_entry.read",
    "pricing.price_list_entry.manage",
    "pricing.assignment.read",
    "pricing.assignment.manage",
    "pricing.variant_override.read",
    "pricing.variant_override.manage",
    "pricing.price.resolve",
)

PRICING_TABLES = (
    "pricing_price_lists",
    "pricing_price_list_entries",
    "pricing_price_list_assignments",
    "pricing_variant_price_overrides",
    "pricing_price_history",
)

_SCOPE_COLUMNS_CHECK = (
    "(scope_type = 'store' AND store_id IS NOT NULL AND channel_id IS NULL AND market_id IS NULL) OR "
    "(scope_type = 'channel' AND channel_id IS NOT NULL AND store_id IS NULL AND market_id IS NULL) OR "
    "(scope_type = 'market' AND market_id IS NOT NULL AND store_id IS NULL AND channel_id IS NULL)"
)


def _resource_columns() -> list[sa.Column]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
    ]


def _scope_columns() -> list[sa.Column]:
    return [
        sa.Column("scope_type", sa.String(20), nullable=False),
        sa.Column("store_id", postgresql.UUID(as_uuid=True)),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True)),
        sa.Column("market_id", postgresql.UUID(as_uuid=True)),
    ]


def _scope_fks(table: str) -> list[sa.ForeignKeyConstraint]:
    return [
        sa.ForeignKeyConstraint(
            ["tenant_id", "store_id"],
            ["platform_stores.tenant_id", "platform_stores.id"],
            ondelete="RESTRICT",
            name=f"fk_{table}_tenant_store",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "channel_id"],
            ["platform_channels.tenant_id", "platform_channels.id"],
            ondelete="RESTRICT",
            name=f"fk_{table}_tenant_channel",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "market_id"],
            ["platform_markets.tenant_id", "platform_markets.id"],
            ondelete="RESTRICT",
            name=f"fk_{table}_tenant_market",
        ),
    ]


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
        "pricing_price_lists",
        *_resource_columns(),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notes", sa.String(2000)),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_pricing_price_lists_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_pricing_price_lists_tenant_code"),
        sa.CheckConstraint("status IN ('draft','active','archived')", name="ck_pricing_price_list_status"),
        sa.CheckConstraint("version > 0", name="ck_pricing_price_list_version"),
    )
    op.create_index(
        "ix_pricing_price_lists_tenant_status", "pricing_price_lists", ["tenant_id", "status", "id"]
    )
    op.create_index(
        "uq_pricing_price_list_default",
        "pricing_price_lists",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("is_default AND status <> 'archived'"),
    )

    op.create_table(
        "pricing_price_list_entries",
        *_resource_columns(),
        sa.Column("price_list_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("unit_amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("compare_at_amount", sa.Numeric(19, 4)),
        sa.Column("msrp_amount", sa.Numeric(19, 4)),
        sa.Column("cost_amount", sa.Numeric(19, 4)),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "price_list_id"],
            ["pricing_price_lists.tenant_id", "pricing_price_lists.id"],
            ondelete="RESTRICT",
            name="fk_pricing_price_list_entries_tenant_price_list",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["catalog_product_variants.tenant_id", "catalog_product_variants.id"],
            ondelete="RESTRICT",
            name="fk_pricing_price_list_entries_tenant_variant",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_pricing_price_list_entries_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "price_list_id", "variant_id", name="uq_pricing_price_list_entry_variant"
        ),
        sa.CheckConstraint("unit_amount >= 0", name="ck_pricing_price_list_entry_unit_amount"),
        sa.CheckConstraint(
            "compare_at_amount IS NULL OR compare_at_amount >= 0",
            name="ck_pricing_price_list_entry_compare_at_amount",
        ),
        sa.CheckConstraint(
            "msrp_amount IS NULL OR msrp_amount >= 0", name="ck_pricing_price_list_entry_msrp_amount"
        ),
        sa.CheckConstraint(
            "cost_amount IS NULL OR cost_amount >= 0", name="ck_pricing_price_list_entry_cost_amount"
        ),
        sa.CheckConstraint("status IN ('active','archived')", name="ck_pricing_price_list_entry_status"),
        sa.CheckConstraint("version > 0", name="ck_pricing_price_list_entry_version"),
    )
    op.create_index(
        "ix_pricing_price_list_entries_tenant_list_status",
        "pricing_price_list_entries",
        ["tenant_id", "price_list_id", "status"],
    )
    op.create_index(
        "ix_pricing_price_list_entries_tenant_variant_status",
        "pricing_price_list_entries",
        ["tenant_id", "variant_id", "status"],
    )

    op.create_table(
        "pricing_price_list_assignments",
        *_resource_columns(),
        sa.Column("price_list_id", postgresql.UUID(as_uuid=True), nullable=False),
        *_scope_columns(),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("effective_from", sa.DateTime(timezone=True)),
        sa.Column("effective_until", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "price_list_id"],
            ["pricing_price_lists.tenant_id", "pricing_price_lists.id"],
            ondelete="RESTRICT",
            name="fk_pricing_assignments_tenant_price_list",
        ),
        *_scope_fks("pricing_assignments"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_pricing_assignments_tenant_id"),
        sa.CheckConstraint("scope_type IN ('store','channel','market')", name="ck_pricing_assignment_scope_type"),
        sa.CheckConstraint(_SCOPE_COLUMNS_CHECK, name="ck_pricing_assignment_scope_columns"),
        sa.CheckConstraint(
            "effective_until IS NULL OR effective_from IS NULL OR effective_until > effective_from",
            name="ck_pricing_assignment_window",
        ),
        sa.CheckConstraint("status IN ('active','archived')", name="ck_pricing_assignment_status"),
        sa.CheckConstraint("version > 0", name="ck_pricing_assignment_version"),
    )
    op.create_index(
        "ix_pricing_assignments_tenant_store_status",
        "pricing_price_list_assignments",
        ["tenant_id", "store_id", "status", "priority"],
    )
    op.create_index(
        "ix_pricing_assignments_tenant_channel_status",
        "pricing_price_list_assignments",
        ["tenant_id", "channel_id", "status", "priority"],
    )
    op.create_index(
        "ix_pricing_assignments_tenant_market_status",
        "pricing_price_list_assignments",
        ["tenant_id", "market_id", "status", "priority"],
    )
    op.create_index(
        "ix_pricing_assignments_tenant_list_status",
        "pricing_price_list_assignments",
        ["tenant_id", "price_list_id", "status"],
    )

    op.create_table(
        "pricing_variant_price_overrides",
        *_resource_columns(),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
        *_scope_columns(),
        sa.Column("unit_amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("compare_at_amount", sa.Numeric(19, 4)),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("effective_from", sa.DateTime(timezone=True)),
        sa.Column("effective_until", sa.DateTime(timezone=True)),
        sa.Column("reason", sa.String(500)),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["catalog_product_variants.tenant_id", "catalog_product_variants.id"],
            ondelete="RESTRICT",
            name="fk_pricing_overrides_tenant_variant",
        ),
        *_scope_fks("pricing_overrides"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_pricing_overrides_tenant_id"),
        sa.CheckConstraint("scope_type IN ('store','channel','market')", name="ck_pricing_override_scope_type"),
        sa.CheckConstraint(_SCOPE_COLUMNS_CHECK, name="ck_pricing_override_scope_columns"),
        sa.CheckConstraint("unit_amount >= 0", name="ck_pricing_override_unit_amount"),
        sa.CheckConstraint(
            "compare_at_amount IS NULL OR compare_at_amount >= 0", name="ck_pricing_override_compare_at_amount"
        ),
        sa.CheckConstraint(
            "effective_until IS NULL OR effective_from IS NULL OR effective_until > effective_from",
            name="ck_pricing_override_window",
        ),
        sa.CheckConstraint("status IN ('active','archived')", name="ck_pricing_override_status"),
        sa.CheckConstraint("version > 0", name="ck_pricing_override_version"),
    )
    op.create_index(
        "ix_pricing_overrides_tenant_variant_scope_status",
        "pricing_variant_price_overrides",
        ["tenant_id", "variant_id", "scope_type", "status", "priority"],
    )

    op.create_table(
        "pricing_price_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(30), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("field_name", sa.String(30), nullable=False),
        sa.Column("previous_amount", sa.Numeric(19, 4)),
        sa.Column("new_amount", sa.Numeric(19, 4)),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("changed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reason", sa.String(500)),
        sa.CheckConstraint(
            "entity_type IN ('price_list_entry','variant_price_override')", name="ck_pricing_history_entity_type"
        ),
    )
    op.create_index(
        "ix_pricing_history_tenant_variant_changed",
        "pricing_price_history",
        ["tenant_id", "variant_id", "changed_at"],
    )
    op.create_index(
        "ix_pricing_history_tenant_entity",
        "pricing_price_history",
        ["tenant_id", "entity_type", "entity_id", "changed_at"],
    )

    bind = op.get_bind()
    for code in PRICING_PERMISSIONS:
        bind.execute(
            sa.text("INSERT INTO permissions(id, code) VALUES (:id, :code) ON CONFLICT (code) DO NOTHING"),
            {"id": uuid4(), "code": code},
        )

    reads = tuple(permission for permission in PRICING_PERMISSIONS if permission.endswith(".read"))
    editor = (
        "pricing.price_list.read",
        "pricing.price_list.create",
        "pricing.price_list.update",
        "pricing.price_list_entry.read",
        "pricing.price_list_entry.manage",
        "pricing.assignment.read",
        "pricing.assignment.manage",
        "pricing.variant_override.read",
        "pricing.variant_override.manage",
        "pricing.price.resolve",
    )
    grants = {
        "owner": PRICING_PERMISSIONS,
        "admin": PRICING_PERMISSIONS,
        "manager": PRICING_PERMISSIONS,
        "editor": editor,
        "analyst": (*reads, "pricing.price.resolve"),
        "viewer": (*reads, "pricing.price.resolve"),
    }
    for role_name, codes in grants.items():
        bind.execute(
            sa.text(
                """
                INSERT INTO role_permissions(role_id, permission_id)
                SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
                WHERE r.is_system IS TRUE AND r.name = :role_name AND p.code = ANY(:codes)
                ON CONFLICT DO NOTHING
                """
            ),
            {"role_name": role_name, "codes": list(codes)},
        )

    for table in PRICING_TABLES:
        _create_rls(table)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN "
            "(SELECT id FROM permissions WHERE code = ANY(:codes))"
        ),
        {"codes": list(PRICING_PERMISSIONS)},
    )
    bind.execute(
        sa.text("DELETE FROM permissions WHERE code = ANY(:codes)"),
        {"codes": list(PRICING_PERMISSIONS)},
    )

    for table in (
        "pricing_price_history",
        "pricing_variant_price_overrides",
        "pricing_price_list_assignments",
        "pricing_price_list_entries",
        "pricing_price_lists",
    ):
        op.drop_table(table)

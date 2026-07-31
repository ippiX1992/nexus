"""Inventory Engine (M4.1): Warehouses, Locations, Stock, Ledger, Transfers, Reservations, RBAC and forced RLS.

Revision ID: 0007
Revises: 0006
"""

from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

INVENTORY_PERMISSIONS = (
    "inventory.warehouse.read",
    "inventory.warehouse.create",
    "inventory.warehouse.update",
    "inventory.warehouse.archive",
    "inventory.location.read",
    "inventory.location.create",
    "inventory.location.update",
    "inventory.location.archive",
    "inventory.stock.read",
    "inventory.stock.adjust",
    "inventory.stock.recount",
    "inventory.transfer.read",
    "inventory.transfer.manage",
    "inventory.reservation.read",
    "inventory.reservation.manage",
    "inventory.fulfillment_scope.read",
    "inventory.fulfillment_scope.manage",
    "inventory.allocation.read",
)

INVENTORY_TABLES = (
    "inventory_warehouses",
    "inventory_locations",
    "inventory_stock_levels",
    "inventory_ledger_entries",
    "inventory_transfers",
    "inventory_reservations",
    "inventory_fulfillment_scopes",
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
        "inventory_warehouses",
        *_resource_columns(),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("country_code", sa.String(2)),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_inventory_warehouses_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_inventory_warehouses_tenant_code"),
        sa.CheckConstraint("status IN ('active','archived')", name="ck_inventory_warehouse_status"),
        sa.CheckConstraint("version > 0", name="ck_inventory_warehouse_version"),
    )
    op.create_index("ix_inventory_warehouses_tenant_status", "inventory_warehouses", ["tenant_id", "status", "id"])

    op.create_table(
        "inventory_locations",
        *_resource_columns(),
        sa.Column("warehouse_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("location_type", sa.String(20), nullable=False, server_default="storage"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["inventory_warehouses.tenant_id", "inventory_warehouses.id"],
            ondelete="RESTRICT",
            name="fk_inventory_locations_tenant_warehouse",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_inventory_locations_tenant_id"),
        sa.UniqueConstraint("tenant_id", "warehouse_id", "code", name="uq_inventory_location_warehouse_code"),
        sa.CheckConstraint(
            "location_type IN ('storage','picking','staging','returns','quarantine')",
            name="ck_inventory_location_type",
        ),
        sa.CheckConstraint("status IN ('active','archived')", name="ck_inventory_location_status"),
        sa.CheckConstraint("version > 0", name="ck_inventory_location_version"),
    )
    op.create_index(
        "ix_inventory_locations_tenant_warehouse_status",
        "inventory_locations",
        ["tenant_id", "warehouse_id", "status", "id"],
    )

    op.create_table(
        "inventory_stock_levels",
        *_resource_columns(),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("on_hand", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("reserved", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("incoming", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("available", sa.BigInteger(), sa.Computed("on_hand - reserved", persisted=True)),
        sa.ForeignKeyConstraint(
            ["tenant_id", "location_id"],
            ["inventory_locations.tenant_id", "inventory_locations.id"],
            ondelete="RESTRICT",
            name="fk_inventory_stock_levels_tenant_location",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["catalog_product_variants.tenant_id", "catalog_product_variants.id"],
            ondelete="RESTRICT",
            name="fk_inventory_stock_levels_tenant_variant",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_inventory_stock_levels_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "location_id", "variant_id", name="uq_inventory_stock_level_location_variant"
        ),
        sa.CheckConstraint("on_hand >= 0", name="ck_inventory_stock_on_hand_nonneg"),
        sa.CheckConstraint("reserved >= 0", name="ck_inventory_stock_reserved_nonneg"),
        sa.CheckConstraint("incoming >= 0", name="ck_inventory_stock_incoming_nonneg"),
        sa.CheckConstraint("reserved <= on_hand", name="ck_inventory_stock_reserved_le_on_hand"),
        sa.CheckConstraint("version > 0", name="ck_inventory_stock_version"),
    )
    op.create_index(
        "ix_inventory_stock_levels_tenant_variant", "inventory_stock_levels", ["tenant_id", "variant_id", "location_id"]
    )

    op.create_table(
        "inventory_ledger_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entry_type", sa.String(30), nullable=False),
        sa.Column("quantity_delta", sa.BigInteger(), nullable=False),
        sa.Column("on_hand_after", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(500)),
        sa.Column("reference_type", sa.String(50)),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "location_id"],
            ["inventory_locations.tenant_id", "inventory_locations.id"],
            ondelete="RESTRICT",
            name="fk_inventory_ledger_tenant_location",
        ),
        sa.CheckConstraint(
            "entry_type IN ('receipt','adjustment','transfer_in','transfer_out',"
            "'reservation_hold','reservation_release','reservation_commit','recount')",
            name="ck_inventory_ledger_entry_type",
        ),
    )
    op.create_index(
        "ix_inventory_ledger_tenant_variant_created", "inventory_ledger_entries", ["tenant_id", "variant_id", "created_at"]
    )
    op.create_index(
        "ix_inventory_ledger_tenant_location_created",
        "inventory_ledger_entries",
        ["tenant_id", "location_id", "created_at"],
    )
    op.create_index(
        "ix_inventory_ledger_tenant_reference",
        "inventory_ledger_entries",
        ["tenant_id", "reference_type", "reference_id"],
    )

    op.create_table(
        "inventory_transfers",
        *_resource_columns(),
        sa.Column("from_location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("to_location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(500)),
        sa.Column("status", sa.String(20), nullable=False, server_default="in_transit"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "from_location_id"],
            ["inventory_locations.tenant_id", "inventory_locations.id"],
            ondelete="RESTRICT",
            name="fk_inventory_transfers_tenant_from_location",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "to_location_id"],
            ["inventory_locations.tenant_id", "inventory_locations.id"],
            ondelete="RESTRICT",
            name="fk_inventory_transfers_tenant_to_location",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["catalog_product_variants.tenant_id", "catalog_product_variants.id"],
            ondelete="RESTRICT",
            name="fk_inventory_transfers_tenant_variant",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_inventory_transfers_tenant_id"),
        sa.CheckConstraint("quantity > 0", name="ck_inventory_transfer_quantity_positive"),
        sa.CheckConstraint("from_location_id <> to_location_id", name="ck_inventory_transfer_distinct_locations"),
        sa.CheckConstraint("status IN ('in_transit','completed','cancelled')", name="ck_inventory_transfer_status"),
        sa.CheckConstraint("version > 0", name="ck_inventory_transfer_version"),
    )
    op.create_index("ix_inventory_transfers_tenant_status", "inventory_transfers", ["tenant_id", "status", "id"])

    op.create_table(
        "inventory_reservations",
        *_resource_columns(),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
        *_scope_columns_nullable(),
        sa.Column("reference_type", sa.String(50)),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20), nullable=False, server_default="held"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "location_id"],
            ["inventory_locations.tenant_id", "inventory_locations.id"],
            ondelete="RESTRICT",
            name="fk_inventory_reservations_tenant_location",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["catalog_product_variants.tenant_id", "catalog_product_variants.id"],
            ondelete="RESTRICT",
            name="fk_inventory_reservations_tenant_variant",
        ),
        *_scope_fks("inventory_reservations"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_inventory_reservations_tenant_id"),
        sa.CheckConstraint("quantity > 0", name="ck_inventory_reservation_quantity_positive"),
        sa.CheckConstraint("status IN ('held','released','committed')", name="ck_inventory_reservation_status"),
        sa.CheckConstraint(
            "scope_type IS NULL OR scope_type IN ('store','channel','market')",
            name="ck_inventory_reservation_scope_type",
        ),
        sa.CheckConstraint("version > 0", name="ck_inventory_reservation_version"),
    )
    op.create_index(
        "ix_inventory_reservations_tenant_variant_status",
        "inventory_reservations",
        ["tenant_id", "variant_id", "status"],
    )
    op.create_index(
        "ix_inventory_reservations_tenant_reference",
        "inventory_reservations",
        ["tenant_id", "reference_type", "reference_id"],
    )
    op.create_index(
        "ix_inventory_reservations_tenant_status_expiry",
        "inventory_reservations",
        ["tenant_id", "status", "expires_at"],
    )

    op.create_table(
        "inventory_fulfillment_scopes",
        *_resource_columns(),
        sa.Column("warehouse_id", postgresql.UUID(as_uuid=True), nullable=False),
        *_scope_columns(),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["inventory_warehouses.tenant_id", "inventory_warehouses.id"],
            ondelete="RESTRICT",
            name="fk_inventory_fulfillment_scopes_tenant_warehouse",
        ),
        *_scope_fks("inventory_fulfillment_scopes"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_inventory_fulfillment_scopes_tenant_id"),
        sa.CheckConstraint("scope_type IN ('store','channel','market')", name="ck_inventory_fulfillment_scope_type"),
        sa.CheckConstraint(_SCOPE_COLUMNS_CHECK, name="ck_inventory_fulfillment_scope_columns"),
        sa.CheckConstraint("status IN ('active','archived')", name="ck_inventory_fulfillment_scope_status"),
        sa.CheckConstraint("version > 0", name="ck_inventory_fulfillment_scope_version"),
    )
    op.create_index(
        "ix_inventory_fulfillment_scopes_store",
        "inventory_fulfillment_scopes",
        ["tenant_id", "store_id", "status", "priority"],
    )
    op.create_index(
        "ix_inventory_fulfillment_scopes_channel",
        "inventory_fulfillment_scopes",
        ["tenant_id", "channel_id", "status", "priority"],
    )
    op.create_index(
        "ix_inventory_fulfillment_scopes_market",
        "inventory_fulfillment_scopes",
        ["tenant_id", "market_id", "status", "priority"],
    )
    op.create_index(
        "ix_inventory_fulfillment_scopes_warehouse",
        "inventory_fulfillment_scopes",
        ["tenant_id", "warehouse_id", "status"],
    )

    bind = op.get_bind()
    for code in INVENTORY_PERMISSIONS:
        bind.execute(
            sa.text("INSERT INTO permissions(id, code) VALUES (:id, :code) ON CONFLICT (code) DO NOTHING"),
            {"id": uuid4(), "code": code},
        )

    reads = tuple(permission for permission in INVENTORY_PERMISSIONS if permission.endswith(".read"))
    editor = (
        "inventory.warehouse.read",
        "inventory.warehouse.create",
        "inventory.warehouse.update",
        "inventory.location.read",
        "inventory.location.create",
        "inventory.location.update",
        "inventory.stock.read",
        "inventory.stock.adjust",
        "inventory.stock.recount",
        "inventory.transfer.read",
        "inventory.transfer.manage",
        "inventory.reservation.read",
        "inventory.reservation.manage",
        "inventory.fulfillment_scope.read",
        "inventory.fulfillment_scope.manage",
        "inventory.allocation.read",
    )
    grants = {
        "owner": INVENTORY_PERMISSIONS,
        "admin": INVENTORY_PERMISSIONS,
        "manager": INVENTORY_PERMISSIONS,
        "editor": editor,
        "analyst": (*reads, "inventory.allocation.read"),
        "viewer": (*reads, "inventory.allocation.read"),
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

    for table in INVENTORY_TABLES:
        _create_rls(table)


def _scope_columns_nullable() -> list[sa.Column]:
    """Reservations may be unscoped (a plain hold not tied to a Store/Channel/
    Market), so scope_type is nullable here, unlike fulfillment scopes."""
    return [
        sa.Column("scope_type", sa.String(20)),
        sa.Column("store_id", postgresql.UUID(as_uuid=True)),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True)),
        sa.Column("market_id", postgresql.UUID(as_uuid=True)),
    ]


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN "
            "(SELECT id FROM permissions WHERE code = ANY(:codes))"
        ),
        {"codes": list(INVENTORY_PERMISSIONS)},
    )
    bind.execute(
        sa.text("DELETE FROM permissions WHERE code = ANY(:codes)"),
        {"codes": list(INVENTORY_PERMISSIONS)},
    )

    for table in (
        "inventory_fulfillment_scopes",
        "inventory_reservations",
        "inventory_transfers",
        "inventory_ledger_entries",
        "inventory_stock_levels",
        "inventory_locations",
        "inventory_warehouses",
    ):
        op.drop_table(table)

"""Storefront orders + tracking (0008): public checkout persistence.

Adds storefront_orders, storefront_order_items and storefront_order_events so
the public storefront can place orders (reserving stock) and expose order +
tracking status. Tenant-scoped with forced RLS, mirroring the other modules.

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

_TABLES = ("storefront_orders", "storefront_order_items", "storefront_order_events")


def _secure(table: str) -> None:
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
        "storefront_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("order_number", sa.String(40), nullable=False),
        sa.Column("tracking_number", sa.String(40), nullable=False),
        sa.Column("store_key", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="placed"),
        sa.Column("customer_name", sa.String(160), nullable=False),
        sa.Column("customer_email", sa.String(255)),
        sa.Column("customer_phone", sa.String(40)),
        sa.Column("shipping_address", sa.String(500)),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("subtotal", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "order_number", name="uq_storefront_order_number"),
    )
    op.create_index("ix_storefront_orders_tracking", "storefront_orders", ["tenant_id", "tracking_number"])

    op.create_table(
        "storefront_order_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True)),
        sa.Column("sku", sa.String(120)),
        sa.Column("name", sa.String(255)),
        sa.Column("unit_amount", sa.Numeric(14, 4)),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("line_total", sa.Numeric(14, 4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["order_id"], ["storefront_orders.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_storefront_order_items_order", "storefront_order_items", ["order_id"])

    op.create_table(
        "storefront_order_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("note", sa.String(255)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["order_id"], ["storefront_orders.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_storefront_order_events_order", "storefront_order_events", ["order_id"])

    for table in _TABLES:
        _secure(table)


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")

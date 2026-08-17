"""Storefront shipping method + amount on orders (0009).

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("storefront_orders", sa.Column("shipping_method", sa.String(24), nullable=False, server_default="standard"))
    op.add_column("storefront_orders", sa.Column("shipping_amount", sa.Numeric(14, 4), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("storefront_orders", "shipping_amount")
    op.drop_column("storefront_orders", "shipping_method")

"""Storefront shipping location (province/city) on orders (0011).

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("storefront_orders", sa.Column("shipping_province", sa.String(80), nullable=True))
    op.add_column("storefront_orders", sa.Column("shipping_city", sa.String(80), nullable=True))


def downgrade() -> None:
    op.drop_column("storefront_orders", "shipping_city")
    op.drop_column("storefront_orders", "shipping_province")

"""Storefront coupons on orders + product reviews (0010).

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


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
    op.add_column("storefront_orders", sa.Column("coupon_code", sa.String(40), nullable=True))
    op.add_column("storefront_orders", sa.Column("discount_amount", sa.Numeric(14, 4), nullable=False, server_default="0"))

    op.create_table(
        "storefront_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("product_slug", sa.String(200), nullable=False),
        sa.Column("author", sa.String(120), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.String(1000)),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_storefront_review_rating"),
    )
    op.create_index("ix_storefront_reviews_slug", "storefront_reviews", ["tenant_id", "product_slug"])
    _secure("storefront_reviews")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS storefront_reviews CASCADE")
    op.drop_column("storefront_orders", "discount_amount")
    op.drop_column("storefront_orders", "coupon_code")

"""Product media (images + video) with forced RLS.

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

TABLE = "catalog_product_media"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("catalog_products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("media_type", sa.String(10), nullable=False, server_default="image"),
        # storage_key = path under media_root for uploaded files; external_url for embeds (e.g. YouTube).
        sa.Column("storage_key", sa.Text()),
        sa.Column("external_url", sa.String(1000)),
        sa.Column("original_name", sa.String(255)),
        sa.Column("content_type", sa.String(120)),
        sa.Column("byte_size", sa.BigInteger()),
        sa.Column("alt_text", sa.String(255)),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("tenant_id", "id", name="uq_catalog_product_media_tenant_id"),
        sa.CheckConstraint("media_type IN ('image','video')", name="ck_catalog_product_media_type"),
        sa.CheckConstraint("storage_key IS NOT NULL OR external_url IS NOT NULL", name="ck_catalog_product_media_source"),
    )
    op.create_index(
        "ix_catalog_product_media_tenant_product_position",
        TABLE,
        ["tenant_id", "product_id", "position", "id"],
    )

    predicate = "tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid"
    op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY {TABLE}_select ON {TABLE} FOR SELECT USING ({predicate})")
    op.execute(f"CREATE POLICY {TABLE}_insert ON {TABLE} FOR INSERT WITH CHECK ({predicate})")
    op.execute(f"CREATE POLICY {TABLE}_update ON {TABLE} FOR UPDATE USING ({predicate}) WITH CHECK ({predicate})")
    op.execute(f"CREATE POLICY {TABLE}_delete ON {TABLE} FOR DELETE USING ({predicate})")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {TABLE} TO nexus_app")


def downgrade() -> None:
    op.drop_index("ix_catalog_product_media_tenant_product_position", table_name=TABLE)
    op.drop_table(TABLE)

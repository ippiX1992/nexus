"""Catalog Foundation schema, RBAC, entitlements and forced RLS.

Revision ID: 0003
Revises: 0002
"""

from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

CATALOG_PERMISSIONS = (
    "catalog.product.read",
    "catalog.product.create",
    "catalog.product.update",
    "catalog.product.archive",
    "catalog.variant.read",
    "catalog.variant.create",
    "catalog.variant.update",
    "catalog.variant.archive",
    "catalog.product_type.read",
    "catalog.product_type.manage",
    "catalog.brand.read",
    "catalog.brand.manage",
    "catalog.taxonomy.read",
    "catalog.taxonomy.manage",
    "catalog.category.read",
    "catalog.category.manage",
    "catalog.assignment.read",
    "catalog.assignment.manage",
)

CATALOG_TABLES = (
    "catalog_product_types",
    "catalog_brands",
    "catalog_products",
    "catalog_product_variants",
    "catalog_product_identifiers",
    "catalog_product_translations",
    "catalog_product_seo",
    "catalog_taxonomies",
    "catalog_categories",
    "catalog_category_closure",
    "catalog_product_categories",
    "catalog_product_stores",
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
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
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
        "catalog_product_types",
        *_resource_columns(),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_catalog_product_types_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_catalog_product_types_tenant_code"),
        sa.CheckConstraint("status IN ('active','archived')", name="ck_catalog_product_type_status"),
        sa.CheckConstraint("version > 0", name="ck_catalog_product_type_version"),
    )
    op.create_index(
        "ix_catalog_product_types_tenant_status_created",
        "catalog_product_types",
        ["tenant_id", "status", "created_at", "id"],
    )

    op.create_table(
        "catalog_brands",
        *_resource_columns(),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(160), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_catalog_brands_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_catalog_brands_tenant_code"),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_catalog_brands_tenant_slug"),
        sa.CheckConstraint("status IN ('active','archived')", name="ck_catalog_brand_status"),
        sa.CheckConstraint("version > 0", name="ck_catalog_brand_version"),
    )
    op.create_index(
        "ix_catalog_brands_tenant_status_created",
        "catalog_brands",
        ["tenant_id", "status", "created_at", "id"],
    )

    op.create_table(
        "catalog_products",
        *_resource_columns(),
        sa.Column("product_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True)),
        sa.Column("code", sa.String(160)),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_type_id"],
            ["catalog_product_types.tenant_id", "catalog_product_types.id"],
            ondelete="RESTRICT",
            name="fk_catalog_products_tenant_product_type",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "brand_id"],
            ["catalog_brands.tenant_id", "catalog_brands.id"],
            ondelete="RESTRICT",
            name="fk_catalog_products_tenant_brand",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_catalog_products_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_catalog_products_tenant_code"),
        sa.CheckConstraint("status IN ('draft','active','archived')", name="ck_catalog_product_status"),
        sa.CheckConstraint("version > 0", name="ck_catalog_product_version"),
    )
    op.create_index(
        "ix_catalog_products_tenant_status_created",
        "catalog_products",
        ["tenant_id", "status", "created_at", "id"],
    )
    op.create_index(
        "ix_catalog_products_tenant_type_status",
        "catalog_products",
        ["tenant_id", "product_type_id", "status", "id"],
    )
    op.create_index(
        "ix_catalog_products_tenant_brand_status",
        "catalog_products",
        ["tenant_id", "brand_id", "status", "id"],
    )

    op.create_table(
        "catalog_product_variants",
        *_resource_columns(),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku", sa.String(160), nullable=False),
        sa.Column("sku_normalized", sa.String(160), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["catalog_products.tenant_id", "catalog_products.id"],
            ondelete="RESTRICT",
            name="fk_catalog_variants_tenant_product",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_catalog_variants_tenant_id"),
        sa.UniqueConstraint("tenant_id", "product_id", "id", name="uq_catalog_variants_tenant_product_id"),
        sa.UniqueConstraint("tenant_id", "sku_normalized", name="uq_catalog_variants_tenant_sku"),
        sa.CheckConstraint(
            "status IN ('draft','active','archived')",
            name="ck_catalog_variant_status",
        ),
        sa.CheckConstraint("length(sku_normalized) > 0", name="ck_catalog_variant_sku_nonempty"),
        sa.CheckConstraint("version > 0", name="ck_catalog_variant_version"),
    )
    op.create_index(
        "uq_catalog_variant_default",
        "catalog_product_variants",
        ["tenant_id", "product_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )
    op.create_index(
        "ix_catalog_variants_tenant_product_status",
        "catalog_product_variants",
        ["tenant_id", "product_id", "status", "created_at", "id"],
    )

    op.create_table(
        "catalog_product_identifiers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("identifier_type", sa.String(20), nullable=False),
        sa.Column("value", sa.String(255), nullable=False),
        sa.Column("normalized_value", sa.String(255), nullable=False),
        sa.Column("source_system", sa.String(100)),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["catalog_product_variants.tenant_id", "catalog_product_variants.id"],
            ondelete="RESTRICT",
            name="fk_catalog_identifiers_tenant_variant",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_catalog_identifiers_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "identifier_type",
            "normalized_value",
            name="uq_catalog_identifier_tenant_type_value",
        ),
        sa.CheckConstraint(
            "identifier_type IN ('ean','upc','isbn','mpn','external')",
            name="ck_catalog_identifier_type",
        ),
        sa.CheckConstraint("length(normalized_value) > 0", name="ck_catalog_identifier_nonempty"),
        sa.CheckConstraint(
            "identifier_type <> 'external' OR source_system IS NOT NULL",
            name="ck_catalog_external_identifier_source",
        ),
    )
    op.create_index(
        "uq_catalog_identifier_primary",
        "catalog_product_identifiers",
        ["tenant_id", "variant_id", "identifier_type"],
        unique=True,
        postgresql_where=sa.text("is_primary AND archived_at IS NULL"),
    )
    op.create_index(
        "ix_catalog_identifiers_tenant_variant",
        "catalog_product_identifiers",
        ["tenant_id", "variant_id", "archived_at", "id"],
    )

    op.create_table(
        "catalog_product_translations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("locale", sa.String(35), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("short_description", sa.String(1000)),
        sa.Column("long_description", sa.Text()),
        sa.Column("slug", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["catalog_products.tenant_id", "catalog_products.id"],
            ondelete="RESTRICT",
            name="fk_catalog_translations_tenant_product",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_catalog_translations_tenant_id"),
        sa.UniqueConstraint("tenant_id", "product_id", "locale", name="uq_catalog_translation_product_locale"),
        sa.UniqueConstraint("tenant_id", "locale", "slug", name="uq_catalog_translation_tenant_locale_slug"),
    )
    op.create_index(
        "ix_catalog_translations_tenant_name",
        "catalog_product_translations",
        ["tenant_id", "locale", "name", "product_id"],
    )

    op.create_table(
        "catalog_product_seo",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("locale", sa.String(35), nullable=False),
        sa.Column("title", sa.String(300)),
        sa.Column("description", sa.String(500)),
        sa.Column("canonical_path", sa.String(500)),
        sa.Column("robots_index", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("robots_follow", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["catalog_products.tenant_id", "catalog_products.id"],
            ondelete="RESTRICT",
            name="fk_catalog_seo_tenant_product",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_catalog_seo_tenant_id"),
        sa.UniqueConstraint("tenant_id", "product_id", "locale", name="uq_catalog_seo_product_locale"),
    )
    op.create_index(
        "ix_catalog_seo_tenant_product",
        "catalog_product_seo",
        ["tenant_id", "product_id", "locale"],
    )

    op.create_table(
        "catalog_taxonomies",
        *_resource_columns(),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_catalog_taxonomies_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_catalog_taxonomies_tenant_code"),
        sa.CheckConstraint("status IN ('active','archived')", name="ck_catalog_taxonomy_status"),
        sa.CheckConstraint("version > 0", name="ck_catalog_taxonomy_version"),
    )
    op.create_index(
        "ix_catalog_taxonomies_tenant_status_created",
        "catalog_taxonomies",
        ["tenant_id", "status", "created_at", "id"],
    )

    op.create_table(
        "catalog_categories",
        *_resource_columns(),
        sa.Column("taxonomy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True)),
        sa.Column("code", sa.String(120), nullable=False),
        sa.Column("name", sa.String(250), nullable=False),
        sa.Column("slug", sa.String(200), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "taxonomy_id"],
            ["catalog_taxonomies.tenant_id", "catalog_taxonomies.id"],
            ondelete="RESTRICT",
            name="fk_catalog_categories_tenant_taxonomy",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "taxonomy_id", "parent_id"],
            ["catalog_categories.tenant_id", "catalog_categories.taxonomy_id", "catalog_categories.id"],
            ondelete="RESTRICT",
            name="fk_catalog_categories_tenant_parent",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_catalog_categories_tenant_id"),
        sa.UniqueConstraint("tenant_id", "taxonomy_id", "id", name="uq_catalog_categories_tenant_taxonomy_id"),
        sa.UniqueConstraint("tenant_id", "taxonomy_id", "code", name="uq_catalog_categories_taxonomy_code"),
        sa.UniqueConstraint("tenant_id", "taxonomy_id", "slug", name="uq_catalog_categories_taxonomy_slug"),
        sa.CheckConstraint("status IN ('active','archived')", name="ck_catalog_category_status"),
        sa.CheckConstraint("parent_id IS NULL OR parent_id <> id", name="ck_catalog_category_not_own_parent"),
        sa.CheckConstraint("position >= 0", name="ck_catalog_category_position"),
        sa.CheckConstraint("version > 0", name="ck_catalog_category_version"),
    )
    op.create_index(
        "ix_catalog_categories_tenant_parent",
        "catalog_categories",
        ["tenant_id", "taxonomy_id", "parent_id", "position", "id"],
    )

    op.create_table(
        "catalog_category_closure",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("taxonomy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ancestor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("descendant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "taxonomy_id", "ancestor_id"],
            ["catalog_categories.tenant_id", "catalog_categories.taxonomy_id", "catalog_categories.id"],
            ondelete="RESTRICT",
            name="fk_catalog_closure_tenant_ancestor",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "taxonomy_id", "descendant_id"],
            ["catalog_categories.tenant_id", "catalog_categories.taxonomy_id", "catalog_categories.id"],
            ondelete="RESTRICT",
            name="fk_catalog_closure_tenant_descendant",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "taxonomy_id", "ancestor_id", "descendant_id"),
        sa.CheckConstraint("depth >= 0", name="ck_catalog_category_closure_depth"),
    )
    op.create_index(
        "ix_catalog_closure_descendant",
        "catalog_category_closure",
        ["tenant_id", "taxonomy_id", "descendant_id", "depth", "ancestor_id"],
    )

    op.create_table(
        "catalog_product_categories",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("taxonomy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["catalog_products.tenant_id", "catalog_products.id"],
            ondelete="RESTRICT",
            name="fk_catalog_product_categories_tenant_product",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "taxonomy_id", "category_id"],
            ["catalog_categories.tenant_id", "catalog_categories.taxonomy_id", "catalog_categories.id"],
            ondelete="RESTRICT",
            name="fk_catalog_product_categories_tenant_category",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "product_id", "category_id"),
        sa.CheckConstraint("position >= 0", name="ck_catalog_product_category_position"),
    )
    op.create_index(
        "uq_catalog_product_primary_category",
        "catalog_product_categories",
        ["tenant_id", "product_id", "taxonomy_id"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
    )
    op.create_index(
        "ix_catalog_product_categories_category",
        "catalog_product_categories",
        ["tenant_id", "category_id", "product_id"],
    )

    op.create_table(
        "catalog_product_stores",
        *_resource_columns(),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("eligible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["catalog_products.tenant_id", "catalog_products.id"],
            ondelete="RESTRICT",
            name="fk_catalog_product_stores_tenant_product",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "store_id"],
            ["platform_stores.tenant_id", "platform_stores.id"],
            ondelete="RESTRICT",
            name="fk_catalog_product_stores_tenant_store",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_catalog_product_stores_tenant_id"),
        sa.UniqueConstraint("tenant_id", "product_id", "store_id", name="uq_catalog_product_store_assignment"),
        sa.CheckConstraint("status IN ('draft','active','suspended','archived')", name="ck_catalog_product_store_status"),
        sa.CheckConstraint("version > 0", name="ck_catalog_product_store_version"),
    )
    op.create_index(
        "ix_catalog_product_stores_store_status",
        "catalog_product_stores",
        ["tenant_id", "store_id", "status", "product_id"],
    )
    op.create_index(
        "ix_catalog_product_stores_product",
        "catalog_product_stores",
        ["tenant_id", "product_id", "status", "store_id"],
    )

    bind = op.get_bind()
    for key, default_value, description in (
        ("catalog.products.max", 50_000, "Maximum non-archived products per tenant"),
        ("catalog.variants.max_per_product", 100, "Maximum non-archived variants per product"),
    ):
        bind.execute(
            sa.text(
                """
                INSERT INTO platform_entitlement_definitions(key, default_value, description)
                VALUES (:key, :default_value, :description)
                ON CONFLICT (key) DO NOTHING
                """
            ),
            {"key": key, "default_value": default_value, "description": description},
        )

    for code in CATALOG_PERMISSIONS:
        bind.execute(
            sa.text("INSERT INTO permissions(id, code) VALUES (:id, :code) ON CONFLICT (code) DO NOTHING"),
            {"id": uuid4(), "code": code},
        )

    reads = tuple(permission for permission in CATALOG_PERMISSIONS if permission.endswith(".read"))
    editor = (
        "catalog.product.read",
        "catalog.product.create",
        "catalog.product.update",
        "catalog.variant.read",
        "catalog.variant.create",
        "catalog.variant.update",
        "catalog.product_type.read",
        "catalog.brand.read",
        "catalog.brand.manage",
        "catalog.taxonomy.read",
        "catalog.category.read",
        "catalog.category.manage",
        "catalog.assignment.read",
    )
    grants = {
        "owner": CATALOG_PERMISSIONS,
        "admin": CATALOG_PERMISSIONS,
        "manager": tuple(p for p in CATALOG_PERMISSIONS if p != "catalog.product_type.manage"),
        "editor": editor,
        "analyst": reads,
        "viewer": reads,
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

    for table in CATALOG_TABLES:
        _create_rls(table)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN "
            "(SELECT id FROM permissions WHERE code = ANY(:codes))"
        ),
        {"codes": list(CATALOG_PERMISSIONS)},
    )
    bind.execute(
        sa.text("DELETE FROM permissions WHERE code = ANY(:codes)"),
        {"codes": list(CATALOG_PERMISSIONS)},
    )
    bind.execute(
        sa.text(
            "DELETE FROM platform_entitlement_definitions "
            "WHERE key IN ('catalog.products.max','catalog.variants.max_per_product')"
        )
    )
    for table in (
        "catalog_product_stores",
        "catalog_product_categories",
        "catalog_category_closure",
        "catalog_categories",
        "catalog_taxonomies",
        "catalog_product_seo",
        "catalog_product_translations",
        "catalog_product_identifiers",
        "catalog_product_variants",
        "catalog_products",
        "catalog_brands",
        "catalog_product_types",
    ):
        op.drop_table(table)

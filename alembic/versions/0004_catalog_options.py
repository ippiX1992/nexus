"""Catalog Options and Variant Combinations (M3.1), RBAC, entitlements and forced RLS.

Revision ID: 0004
Revises: 0003
"""

from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

CATALOG_OPTIONS_PERMISSIONS = (
    "catalog.option.read",
    "catalog.option.create",
    "catalog.option.update",
    "catalog.option.archive",
    "catalog.option_value.read",
    "catalog.option_value.create",
    "catalog.option_value.update",
    "catalog.option_value.archive",
    "catalog.product_option.read",
    "catalog.product_option.manage",
    "catalog.variant_combination.read",
    "catalog.variant_combination.create",
    "catalog.variant_combination.generate",
    "catalog.variant_combination.archive",
)

CATALOG_OPTIONS_TABLES = (
    "catalog_options",
    "catalog_option_translations",
    "catalog_option_values",
    "catalog_option_value_translations",
    "catalog_product_options",
    "catalog_variant_option_values",
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
        "catalog_options",
        *_resource_columns(),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("input_type", sa.String(20), nullable=False, server_default="select"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_catalog_options_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_catalog_options_tenant_code"),
        sa.CheckConstraint("status IN ('active','archived')", name="ck_catalog_option_status"),
        sa.CheckConstraint("input_type IN ('select','swatch')", name="ck_catalog_option_input_type"),
        sa.CheckConstraint("version > 0", name="ck_catalog_option_version"),
    )
    op.create_index(
        "ix_catalog_options_tenant_status_position",
        "catalog_options",
        ["tenant_id", "status", "position", "id"],
    )

    op.create_table(
        "catalog_option_translations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("option_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("locale", sa.String(35), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "option_id"],
            ["catalog_options.tenant_id", "catalog_options.id"],
            ondelete="RESTRICT",
            name="fk_catalog_option_translations_tenant_option",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_catalog_option_translations_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "option_id", "locale", name="uq_catalog_option_translation_option_locale"
        ),
    )

    op.create_table(
        "catalog_option_values",
        *_resource_columns(),
        sa.Column("option_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("value", sa.String(200), nullable=False),
        sa.Column("swatch_hex", sa.String(7)),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "option_id"],
            ["catalog_options.tenant_id", "catalog_options.id"],
            ondelete="RESTRICT",
            name="fk_catalog_option_values_tenant_option",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_catalog_option_values_tenant_id"),
        sa.UniqueConstraint("tenant_id", "option_id", "id", name="uq_catalog_option_values_tenant_option_id"),
        sa.UniqueConstraint(
            "tenant_id", "option_id", "code", name="uq_catalog_option_value_tenant_option_code"
        ),
        sa.CheckConstraint("status IN ('active','archived')", name="ck_catalog_option_value_status"),
        sa.CheckConstraint(
            "swatch_hex IS NULL OR swatch_hex ~ '^#[0-9a-fA-F]{6}$'",
            name="ck_catalog_option_value_swatch_hex",
        ),
        sa.CheckConstraint("version > 0", name="ck_catalog_option_value_version"),
    )
    op.create_index(
        "ix_catalog_option_values_tenant_option_status",
        "catalog_option_values",
        ["tenant_id", "option_id", "status", "position", "id"],
    )

    op.create_table(
        "catalog_option_value_translations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("option_value_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("locale", sa.String(35), nullable=False),
        sa.Column("value", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "option_value_id"],
            ["catalog_option_values.tenant_id", "catalog_option_values.id"],
            ondelete="RESTRICT",
            name="fk_catalog_option_value_translations_tenant_value",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_catalog_option_value_translations_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "option_value_id", "locale", name="uq_catalog_option_value_translation_value_locale"
        ),
    )

    op.create_table(
        "catalog_product_options",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("option_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["catalog_products.tenant_id", "catalog_products.id"],
            ondelete="RESTRICT",
            name="fk_catalog_product_options_tenant_product",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "option_id"],
            ["catalog_options.tenant_id", "catalog_options.id"],
            ondelete="RESTRICT",
            name="fk_catalog_product_options_tenant_option",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "product_id", "option_id"),
        sa.CheckConstraint("position >= 0", name="ck_catalog_product_option_position"),
    )
    op.create_index(
        "ix_catalog_product_options_product",
        "catalog_product_options",
        ["tenant_id", "product_id", "position", "option_id"],
    )

    op.create_table(
        "catalog_variant_option_values",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("option_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("option_value_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["catalog_product_variants.tenant_id", "catalog_product_variants.id"],
            ondelete="RESTRICT",
            name="fk_catalog_variant_option_values_tenant_variant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["catalog_products.tenant_id", "catalog_products.id"],
            ondelete="RESTRICT",
            name="fk_catalog_variant_option_values_tenant_product",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id", "option_id"],
            [
                "catalog_product_options.tenant_id",
                "catalog_product_options.product_id",
                "catalog_product_options.option_id",
            ],
            ondelete="RESTRICT",
            name="fk_catalog_variant_option_values_tenant_product_option",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "option_id", "option_value_id"],
            ["catalog_option_values.tenant_id", "catalog_option_values.option_id", "catalog_option_values.id"],
            ondelete="RESTRICT",
            name="fk_catalog_variant_option_values_tenant_value",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "variant_id", "option_id", "option_value_id"),
        sa.UniqueConstraint(
            "tenant_id", "variant_id", "option_id", name="uq_catalog_variant_option_one_value_per_option"
        ),
    )
    op.create_index(
        "ix_catalog_variant_option_values_value",
        "catalog_variant_option_values",
        ["tenant_id", "option_value_id", "variant_id"],
    )

    op.add_column("catalog_product_variants", sa.Column("combination_fingerprint", sa.String(64)))
    op.create_check_constraint(
        "ck_catalog_variant_fingerprint_format",
        "catalog_product_variants",
        "combination_fingerprint IS NULL OR combination_fingerprint ~ '^[0-9a-f]{64}$'",
    )
    op.create_index(
        "uq_catalog_variant_combination_fingerprint",
        "catalog_product_variants",
        ["tenant_id", "product_id", "combination_fingerprint"],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL AND combination_fingerprint IS NOT NULL"),
    )

    bind = op.get_bind()
    for key, default_value, description in (
        ("catalog.product_options.max_per_product", 6, "Maximum Options a Product may declare"),
        ("catalog.option_values.max_per_option", 200, "Maximum Option Values per Option"),
        ("catalog.variant_combinations.max_per_product", 100, "Maximum non-archived Variant combinations per product"),
        ("catalog.combination_generation.max_per_operation", 50, "Maximum combinations a single generation Operation may create"),
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

    for code in CATALOG_OPTIONS_PERMISSIONS:
        bind.execute(
            sa.text("INSERT INTO permissions(id, code) VALUES (:id, :code) ON CONFLICT (code) DO NOTHING"),
            {"id": uuid4(), "code": code},
        )

    reads = tuple(permission for permission in CATALOG_OPTIONS_PERMISSIONS if permission.endswith(".read"))
    editor = (
        "catalog.option.read",
        "catalog.option.create",
        "catalog.option.update",
        "catalog.option_value.read",
        "catalog.option_value.create",
        "catalog.option_value.update",
        "catalog.product_option.read",
        "catalog.product_option.manage",
        "catalog.variant_combination.read",
        "catalog.variant_combination.create",
        "catalog.variant_combination.generate",
    )
    grants = {
        "owner": CATALOG_OPTIONS_PERMISSIONS,
        "admin": CATALOG_OPTIONS_PERMISSIONS,
        "manager": CATALOG_OPTIONS_PERMISSIONS,
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

    for table in CATALOG_OPTIONS_TABLES:
        _create_rls(table)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN "
            "(SELECT id FROM permissions WHERE code = ANY(:codes))"
        ),
        {"codes": list(CATALOG_OPTIONS_PERMISSIONS)},
    )
    bind.execute(
        sa.text("DELETE FROM permissions WHERE code = ANY(:codes)"),
        {"codes": list(CATALOG_OPTIONS_PERMISSIONS)},
    )
    bind.execute(
        sa.text(
            "DELETE FROM platform_entitlement_definitions WHERE key IN ("
            "'catalog.product_options.max_per_product',"
            "'catalog.option_values.max_per_option',"
            "'catalog.variant_combinations.max_per_product',"
            "'catalog.combination_generation.max_per_operation')"
        )
    )

    op.drop_index("uq_catalog_variant_combination_fingerprint", table_name="catalog_product_variants")
    op.drop_constraint("ck_catalog_variant_fingerprint_format", "catalog_product_variants", type_="check")
    op.drop_column("catalog_product_variants", "combination_fingerprint")

    for table in (
        "catalog_variant_option_values",
        "catalog_product_options",
        "catalog_option_value_translations",
        "catalog_option_values",
        "catalog_option_translations",
        "catalog_options",
    ):
        op.drop_table(table)

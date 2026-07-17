"""Catalog Attributes and Product Specifications (M3.2), RBAC, entitlements and forced RLS.

Revision ID: 0005
Revises: 0004
"""

from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

CATALOG_ATTRIBUTES_PERMISSIONS = (
    "catalog.attribute.read",
    "catalog.attribute.create",
    "catalog.attribute.update",
    "catalog.attribute.archive",
    "catalog.attribute_option.read",
    "catalog.attribute_option.create",
    "catalog.attribute_option.update",
    "catalog.attribute_option.archive",
    "catalog.attribute_group.read",
    "catalog.attribute_group.create",
    "catalog.attribute_group.update",
    "catalog.attribute_group.archive",
    "catalog.product_type_attribute.read",
    "catalog.product_type_attribute.manage",
    "catalog.product_attribute_value.read",
    "catalog.product_attribute_value.manage",
)

CATALOG_ATTRIBUTES_TABLES = (
    "catalog_attributes",
    "catalog_attribute_translations",
    "catalog_attribute_options",
    "catalog_attribute_option_translations",
    "catalog_attribute_groups",
    "catalog_attribute_group_translations",
    "catalog_product_type_attributes",
    "catalog_product_attribute_values",
    "catalog_product_attribute_value_options",
)

DATA_TYPES = ("TEXT", "LONG_TEXT", "INTEGER", "DECIMAL", "BOOLEAN", "DATE", "DATETIME", "SELECT", "MULTI_SELECT")


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
    data_type_list = "'" + "','".join(DATA_TYPES) + "'"

    op.create_table(
        "catalog_attributes",
        *_resource_columns(),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.String(2000)),
        sa.Column("data_type", sa.String(20), nullable=False),
        sa.Column("unit", sa.String(50)),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_filterable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_searchable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_comparable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_visible_storefront", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_catalog_attributes_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_catalog_attributes_tenant_code"),
        sa.CheckConstraint("status IN ('active','archived')", name="ck_catalog_attribute_status"),
        sa.CheckConstraint(f"data_type IN ({data_type_list})", name="ck_catalog_attribute_data_type"),
        sa.CheckConstraint("version > 0", name="ck_catalog_attribute_version"),
    )
    op.create_index(
        "ix_catalog_attributes_tenant_status_position",
        "catalog_attributes",
        ["tenant_id", "status", "position", "id"],
    )

    op.create_table(
        "catalog_attribute_translations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("attribute_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("locale", sa.String(35), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.String(2000)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "attribute_id"],
            ["catalog_attributes.tenant_id", "catalog_attributes.id"],
            ondelete="RESTRICT",
            name="fk_catalog_attribute_translations_tenant_attribute",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_catalog_attribute_translations_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "attribute_id", "locale", name="uq_catalog_attribute_translation_attribute_locale"
        ),
    )

    op.create_table(
        "catalog_attribute_options",
        *_resource_columns(),
        sa.Column("attribute_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "attribute_id"],
            ["catalog_attributes.tenant_id", "catalog_attributes.id"],
            ondelete="RESTRICT",
            name="fk_catalog_attribute_options_tenant_attribute",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_catalog_attribute_options_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "attribute_id", "id", name="uq_catalog_attribute_options_tenant_attribute_id"
        ),
        sa.UniqueConstraint(
            "tenant_id", "attribute_id", "code", name="uq_catalog_attribute_option_tenant_attribute_code"
        ),
        sa.CheckConstraint("status IN ('active','archived')", name="ck_catalog_attribute_option_status"),
        sa.CheckConstraint("version > 0", name="ck_catalog_attribute_option_version"),
    )
    op.create_index(
        "ix_catalog_attribute_options_tenant_attribute_status",
        "catalog_attribute_options",
        ["tenant_id", "attribute_id", "status", "position", "id"],
    )

    op.create_table(
        "catalog_attribute_option_translations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("attribute_option_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("locale", sa.String(35), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "attribute_option_id"],
            ["catalog_attribute_options.tenant_id", "catalog_attribute_options.id"],
            ondelete="RESTRICT",
            name="fk_catalog_attribute_option_translations_tenant_option",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_catalog_attribute_option_translations_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "attribute_option_id",
            "locale",
            name="uq_catalog_attribute_option_translation_option_locale",
        ),
    )

    op.create_table(
        "catalog_attribute_groups",
        *_resource_columns(),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.String(2000)),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_catalog_attribute_groups_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_catalog_attribute_groups_tenant_code"),
        sa.CheckConstraint("status IN ('active','archived')", name="ck_catalog_attribute_group_status"),
        sa.CheckConstraint("version > 0", name="ck_catalog_attribute_group_version"),
    )
    op.create_index(
        "ix_catalog_attribute_groups_tenant_status_position",
        "catalog_attribute_groups",
        ["tenant_id", "status", "position", "id"],
    )

    op.create_table(
        "catalog_attribute_group_translations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("locale", sa.String(35), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.String(2000)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "group_id"],
            ["catalog_attribute_groups.tenant_id", "catalog_attribute_groups.id"],
            ondelete="RESTRICT",
            name="fk_catalog_attribute_group_translations_tenant_group",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_catalog_attribute_group_translations_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "group_id", "locale", name="uq_catalog_attribute_group_translation_group_locale"
        ),
    )

    op.create_table(
        "catalog_product_type_attributes",
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("product_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attribute_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("group_id", postgresql.UUID(as_uuid=True)),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("visible_override", sa.Boolean()),
        sa.Column("filterable_override", sa.Boolean()),
        sa.Column("comparable_override", sa.Boolean()),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_type_id"],
            ["catalog_product_types.tenant_id", "catalog_product_types.id"],
            ondelete="RESTRICT",
            name="fk_catalog_product_type_attributes_tenant_product_type",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "attribute_id"],
            ["catalog_attributes.tenant_id", "catalog_attributes.id"],
            ondelete="RESTRICT",
            name="fk_catalog_product_type_attributes_tenant_attribute",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "group_id"],
            ["catalog_attribute_groups.tenant_id", "catalog_attribute_groups.id"],
            ondelete="RESTRICT",
            name="fk_catalog_product_type_attributes_tenant_group",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "product_type_id", "attribute_id"),
        sa.CheckConstraint("position >= 0", name="ck_catalog_product_type_attribute_position"),
    )
    op.create_index(
        "ix_catalog_product_type_attributes_type",
        "catalog_product_type_attributes",
        ["tenant_id", "product_type_id", "position", "attribute_id"],
    )

    op.create_table(
        "catalog_product_attribute_values",
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attribute_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("value_text", sa.String(500)),
        sa.Column("value_long_text", sa.Text()),
        sa.Column("value_integer", sa.BigInteger()),
        sa.Column("value_decimal", sa.Numeric(20, 6)),
        sa.Column("value_boolean", sa.Boolean()),
        sa.Column("value_date", sa.Date()),
        sa.Column("value_datetime", sa.DateTime(timezone=True)),
        sa.Column("value_option_id", postgresql.UUID(as_uuid=True)),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["catalog_products.tenant_id", "catalog_products.id"],
            ondelete="RESTRICT",
            name="fk_catalog_product_attribute_values_tenant_product",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "attribute_id"],
            ["catalog_attributes.tenant_id", "catalog_attributes.id"],
            ondelete="RESTRICT",
            name="fk_catalog_product_attribute_values_tenant_attribute",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "attribute_id", "value_option_id"],
            ["catalog_attribute_options.tenant_id", "catalog_attribute_options.attribute_id", "catalog_attribute_options.id"],
            ondelete="RESTRICT",
            name="fk_catalog_product_attribute_values_tenant_option",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "product_id", "attribute_id"),
        sa.CheckConstraint(
            "(CASE WHEN value_text IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN value_long_text IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN value_integer IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN value_decimal IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN value_boolean IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN value_date IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN value_datetime IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN value_option_id IS NOT NULL THEN 1 ELSE 0 END) <= 1",
            name="ck_catalog_product_attribute_value_single_column",
        ),
    )
    op.create_index(
        "ix_catalog_product_attribute_values_attribute",
        "catalog_product_attribute_values",
        ["tenant_id", "attribute_id", "product_id"],
    )

    op.create_table(
        "catalog_product_attribute_value_options",
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attribute_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attribute_option_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id", "attribute_id"],
            [
                "catalog_product_attribute_values.tenant_id",
                "catalog_product_attribute_values.product_id",
                "catalog_product_attribute_values.attribute_id",
            ],
            ondelete="CASCADE",
            name="fk_catalog_product_attribute_value_options_tenant_value",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "attribute_id", "attribute_option_id"],
            [
                "catalog_attribute_options.tenant_id",
                "catalog_attribute_options.attribute_id",
                "catalog_attribute_options.id",
            ],
            ondelete="RESTRICT",
            name="fk_catalog_product_attribute_value_options_tenant_option",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "product_id", "attribute_id", "attribute_option_id"),
    )
    op.create_index(
        "ix_catalog_product_attribute_value_options_option",
        "catalog_product_attribute_value_options",
        ["tenant_id", "attribute_option_id", "product_id"],
    )

    bind = op.get_bind()
    for key, default_value, description in (
        ("catalog.product_type_attributes.max_per_product_type", 60, "Maximum Attributes a Product Type may declare"),
        ("catalog.attribute_options.max_per_attribute", 200, "Maximum Attribute Options per Attribute"),
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

    for code in CATALOG_ATTRIBUTES_PERMISSIONS:
        bind.execute(
            sa.text("INSERT INTO permissions(id, code) VALUES (:id, :code) ON CONFLICT (code) DO NOTHING"),
            {"id": uuid4(), "code": code},
        )

    reads = tuple(permission for permission in CATALOG_ATTRIBUTES_PERMISSIONS if permission.endswith(".read"))
    editor = (
        "catalog.attribute.read",
        "catalog.attribute.create",
        "catalog.attribute.update",
        "catalog.attribute_option.read",
        "catalog.attribute_option.create",
        "catalog.attribute_option.update",
        "catalog.attribute_group.read",
        "catalog.attribute_group.create",
        "catalog.attribute_group.update",
        "catalog.product_type_attribute.read",
        "catalog.product_type_attribute.manage",
        "catalog.product_attribute_value.read",
        "catalog.product_attribute_value.manage",
    )
    grants = {
        "owner": CATALOG_ATTRIBUTES_PERMISSIONS,
        "admin": CATALOG_ATTRIBUTES_PERMISSIONS,
        "manager": CATALOG_ATTRIBUTES_PERMISSIONS,
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

    for table in CATALOG_ATTRIBUTES_TABLES:
        _create_rls(table)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN "
            "(SELECT id FROM permissions WHERE code = ANY(:codes))"
        ),
        {"codes": list(CATALOG_ATTRIBUTES_PERMISSIONS)},
    )
    bind.execute(
        sa.text("DELETE FROM permissions WHERE code = ANY(:codes)"),
        {"codes": list(CATALOG_ATTRIBUTES_PERMISSIONS)},
    )
    bind.execute(
        sa.text(
            "DELETE FROM platform_entitlement_definitions WHERE key IN ("
            "'catalog.product_type_attributes.max_per_product_type',"
            "'catalog.attribute_options.max_per_attribute')"
        )
    )

    for table in (
        "catalog_product_attribute_value_options",
        "catalog_product_attribute_values",
        "catalog_product_type_attributes",
        "catalog_attribute_group_translations",
        "catalog_attribute_groups",
        "catalog_attribute_option_translations",
        "catalog_attribute_options",
        "catalog_attribute_translations",
        "catalog_attributes",
    ):
        op.drop_table(table)

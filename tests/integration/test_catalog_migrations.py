import os
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
URL = os.environ["DATABASE_MIGRATION_URL"]
CATALOG_TABLES = {
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
}
CATALOG_PERMISSIONS = {
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
}


def alembic(*args: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=ROOT,
        check=True,
        env=os.environ,
    )


def test_catalog_migration_round_trip_and_security_contract() -> None:
    alembic("downgrade", "0002")
    alembic("upgrade", "0003")
    alembic("downgrade", "0002")
    alembic("upgrade", "0003")

    dsn = URL.replace("postgresql+psycopg://", "postgresql://")
    try:
        _assert_m30_security_contract(dsn)
    finally:
        # This test intentionally stops at 0003 to check the M3.0 contract in
        # isolation from 0004 -- but the shared test DB must not be left below
        # head for the tests that run after this one (M3.1's own tables and
        # the combination_fingerprint column would otherwise be missing).
        alembic("upgrade", "head")


def _assert_m30_security_contract(dsn: str) -> None:
    with psycopg.connect(dsn) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public'"
            )
        }
        assert CATALOG_TABLES <= tables

        for table in CATALOG_TABLES:
            policy_count = connection.execute(
                "SELECT count(*) FROM pg_policy WHERE polrelid=%s::regclass",
                (table,),
            ).fetchone()
            assert policy_count is not None
            assert policy_count[0] == 4
            rls = connection.execute(
                """
                SELECT relrowsecurity, relforcerowsecurity
                FROM pg_class
                WHERE oid=%s::regclass
                """,
                (table,),
            ).fetchone()
            assert rls == (True, True)
            privileges = connection.execute(
                """
                SELECT
                    has_table_privilege('nexus_app', %s, 'SELECT'),
                    has_table_privilege('nexus_app', %s, 'INSERT'),
                    has_table_privilege('nexus_app', %s, 'UPDATE'),
                    has_table_privilege('nexus_app', %s, 'DELETE')
                """,
                (table, table, table, table),
            ).fetchone()
            assert privileges == (True, True, True, True)

        permissions = {
            row[0]
            for row in connection.execute(
                "SELECT code FROM permissions WHERE code LIKE 'catalog.%'"
            )
        }
        assert permissions == CATALOG_PERMISSIONS

        entitlements = dict(
            connection.execute(
                """
                SELECT key, default_value
                FROM platform_entitlement_definitions
                WHERE key LIKE 'catalog.%'
                """
            ).fetchall()
        )
        assert entitlements == {
            "catalog.products.max": 50_000,
            "catalog.variants.max_per_product": 100,
        }

        indexes = {
            row[0]
            for row in connection.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE tablename IN (
                    'catalog_product_variants',
                    'catalog_product_identifiers',
                    'catalog_product_translations',
                    'catalog_categories',
                    'catalog_product_categories'
                )
                """
            )
        }
        assert {
            "uq_catalog_variants_tenant_sku",
            "uq_catalog_identifier_tenant_type_value",
            "uq_catalog_translation_tenant_locale_slug",
            "uq_catalog_categories_taxonomy_slug",
            "uq_catalog_product_primary_category",
        } <= indexes

        product_fks = {
            row[0]
            for row in connection.execute(
                """
                SELECT conname
                FROM pg_constraint
                WHERE conrelid='catalog_products'::regclass
                  AND contype='f'
                """
            )
        }
        assert {
            "fk_catalog_products_tenant_product_type",
            "fk_catalog_products_tenant_brand",
        } <= product_fks

        store_policy = connection.execute(
            """
            SELECT pg_get_expr(polqual, polrelid)
            FROM pg_policy
            WHERE polrelid='catalog_product_stores'::regclass
              AND polcmd='r'
            """
        ).fetchone()
        assert store_policy is not None
        assert "app.current_store_id" in store_policy[0]


CATALOG_OPTIONS_TABLES = {
    "catalog_options",
    "catalog_option_translations",
    "catalog_option_values",
    "catalog_option_value_translations",
    "catalog_product_options",
    "catalog_variant_option_values",
}
CATALOG_OPTIONS_PERMISSIONS = {
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
}


def test_catalog_options_migration_round_trip_and_security_contract() -> None:
    alembic("downgrade", "0003")
    alembic("upgrade", "0004")
    alembic("downgrade", "0003")
    alembic("upgrade", "0004")

    dsn = URL.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(dsn) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")
        }
        assert CATALOG_OPTIONS_TABLES <= tables

        for table in CATALOG_OPTIONS_TABLES:
            policy_count = connection.execute(
                "SELECT count(*) FROM pg_policy WHERE polrelid=%s::regclass", (table,)
            ).fetchone()
            assert policy_count is not None and policy_count[0] == 4
            rls = connection.execute(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE oid=%s::regclass", (table,)
            ).fetchone()
            assert rls == (True, True)
            privileges = connection.execute(
                """
                SELECT
                    has_table_privilege('nexus_app', %s, 'SELECT'),
                    has_table_privilege('nexus_app', %s, 'INSERT'),
                    has_table_privilege('nexus_app', %s, 'UPDATE'),
                    has_table_privilege('nexus_app', %s, 'DELETE')
                """,
                (table, table, table, table),
            ).fetchone()
            assert privileges == (True, True, True, True)

        permissions = {
            row[0]
            for row in connection.execute(
                "SELECT code FROM permissions WHERE code LIKE 'catalog.option%' OR code LIKE 'catalog.product_option%' OR code LIKE 'catalog.variant_combination%'"
            )
        }
        assert permissions == CATALOG_OPTIONS_PERMISSIONS

        entitlements = dict(
            connection.execute(
                """
                SELECT key, default_value FROM platform_entitlement_definitions
                WHERE key IN (
                    'catalog.product_options.max_per_product',
                    'catalog.option_values.max_per_option',
                    'catalog.variant_combinations.max_per_product',
                    'catalog.combination_generation.max_per_operation'
                )
                """
            ).fetchall()
        )
        assert entitlements == {
            "catalog.product_options.max_per_product": 6,
            "catalog.option_values.max_per_option": 200,
            "catalog.variant_combinations.max_per_product": 100,
            "catalog.combination_generation.max_per_operation": 50,
        }

        fingerprint_column = connection.execute(
            """
            SELECT data_type FROM information_schema.columns
            WHERE table_name='catalog_product_variants' AND column_name='combination_fingerprint'
            """
        ).fetchone()
        assert fingerprint_column is not None

        fingerprint_index = connection.execute(
            "SELECT indexname FROM pg_indexes WHERE tablename='catalog_product_variants' AND indexname=%s",
            ("uq_catalog_variant_combination_fingerprint",),
        ).fetchone()
        assert fingerprint_index is not None

        one_value_per_option = connection.execute(
            "SELECT conname FROM pg_constraint WHERE conrelid='catalog_variant_option_values'::regclass AND contype='u'"
        ).fetchall()
        assert ("uq_catalog_variant_option_one_value_per_option",) in one_value_per_option


CATALOG_ATTRIBUTES_TABLES = {
    "catalog_attributes",
    "catalog_attribute_translations",
    "catalog_attribute_options",
    "catalog_attribute_option_translations",
    "catalog_attribute_groups",
    "catalog_attribute_group_translations",
    "catalog_product_type_attributes",
    "catalog_product_attribute_values",
    "catalog_product_attribute_value_options",
}
CATALOG_ATTRIBUTES_PERMISSIONS = {
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
}


def test_catalog_attributes_migration_round_trip_and_security_contract() -> None:
    alembic("downgrade", "0004")
    alembic("upgrade", "0005")
    alembic("downgrade", "0004")
    try:
        alembic("upgrade", "0005")

        dsn = URL.replace("postgresql+psycopg://", "postgresql://")
        with psycopg.connect(dsn) as connection:
            tables = {
                row[0]
                for row in connection.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            }
            assert CATALOG_ATTRIBUTES_TABLES <= tables

            for table in CATALOG_ATTRIBUTES_TABLES:
                policy_count = connection.execute(
                    "SELECT count(*) FROM pg_policy WHERE polrelid=%s::regclass", (table,)
                ).fetchone()
                assert policy_count is not None and policy_count[0] == 4
                rls = connection.execute(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE oid=%s::regclass", (table,)
                ).fetchone()
                assert rls == (True, True)
                privileges = connection.execute(
                    """
                    SELECT
                        has_table_privilege('nexus_app', %s, 'SELECT'),
                        has_table_privilege('nexus_app', %s, 'INSERT'),
                        has_table_privilege('nexus_app', %s, 'UPDATE'),
                        has_table_privilege('nexus_app', %s, 'DELETE')
                    """,
                    (table, table, table, table),
                ).fetchone()
                assert privileges == (True, True, True, True)

            permissions = {
                row[0]
                for row in connection.execute(
                    "SELECT code FROM permissions WHERE code LIKE 'catalog.attribute%' OR code LIKE 'catalog.product_type_attribute%' OR code LIKE 'catalog.product_attribute_value%'"
                )
            }
            assert permissions == CATALOG_ATTRIBUTES_PERMISSIONS

            entitlements = dict(
                connection.execute(
                    """
                    SELECT key, default_value FROM platform_entitlement_definitions
                    WHERE key IN (
                        'catalog.product_type_attributes.max_per_product_type',
                        'catalog.attribute_options.max_per_attribute'
                    )
                    """
                ).fetchall()
            )
            assert entitlements == {
                "catalog.product_type_attributes.max_per_product_type": 60,
                "catalog.attribute_options.max_per_attribute": 200,
            }

            single_column_check = connection.execute(
                "SELECT conname FROM pg_constraint WHERE conrelid='catalog_product_attribute_values'::regclass AND contype='c'"
            ).fetchall()
            assert ("ck_catalog_product_attribute_value_single_column",) in single_column_check
    finally:
        # Leave the shared test DB at head so every test file that runs after
        # this one (alphabetically or otherwise) still sees the full schema.
        alembic("upgrade", "head")

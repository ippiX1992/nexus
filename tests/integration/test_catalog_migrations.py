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

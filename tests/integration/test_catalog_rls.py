import os
from uuid import UUID, uuid4

import asyncpg
import pytest

from tests.integration.test_catalog_api import (
    catalog_context,
    create_brand,
    create_product,
    create_store,
    create_type,
)

pytestmark = pytest.mark.integration


def asyncpg_dsn(value: str) -> str:
    return value.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgresql+psycopg://", "postgresql://"
    )


APP_DSN = asyncpg_dsn(os.environ["DATABASE_URL"])


async def seed_tenant_catalog(client, registration, suffix):
    headers, tenant = await catalog_context(client, registration)
    store = await create_store(client, headers, code=f"store-{suffix}")
    product_type = await create_type(client, headers, code=f"type-{suffix}")
    brand = await create_brand(client, headers, code=f"brand-{suffix}")
    product_response, _ = await create_product(
        client,
        headers,
        product_type["id"],
        sku=f"RLS-{suffix}",
        brand_id=brand["id"],
        code=f"product-{suffix}",
    )
    detail = product_response.json()
    taxonomy_response = await client.post(
        "/api/v1/catalog/taxonomies",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"code": f"taxonomy-{suffix}", "name": f"Taxonomy {suffix}"},
    )
    taxonomy = taxonomy_response.json()
    category_response = await client.post(
        f"/api/v1/catalog/taxonomies/{taxonomy['id']}/categories",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "code": f"category-{suffix}",
            "name": f"Category {suffix}",
            "slug": f"category-{suffix}",
            "position": 0,
        },
    )
    assignment_response = await client.put(
        f"/api/v1/catalog/products/{detail['product']['id']}/stores/{store['id']}",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"status": "draft"},
    )
    assert assignment_response.status_code == 200
    return {
        "tenant": UUID(tenant["id"]),
        "store": UUID(store["id"]),
        "product_type": UUID(product_type["id"]),
        "brand": UUID(brand["id"]),
        "product": UUID(detail["product"]["id"]),
        "variant": UUID(detail["variants"][0]["id"]),
        "taxonomy": UUID(taxonomy["id"]),
        "category": UUID(category_response.json()["id"]),
        "assignment": UUID(assignment_response.json()["id"]),
    }


async def test_catalog_rls_blocks_cross_tenant_crud_store_scope_and_pool_leaks(
    client, registration
):
    tenant_a = await seed_tenant_catalog(client, registration, "a")
    tenant_b = await seed_tenant_catalog(
        client,
        {
            **registration,
            "email": "catalog-rls-b@example.com",
            "company": "Catalog RLS B",
        },
        "b",
    )

    pool = await asyncpg.create_pool(APP_DSN, min_size=1, max_size=1)
    async with pool.acquire() as connection:
        for table in (
            "catalog_product_types",
            "catalog_brands",
            "catalog_products",
            "catalog_product_variants",
            "catalog_categories",
            "catalog_product_stores",
        ):
            assert await connection.fetchval(f"SELECT count(*) FROM {table}") == 0

        async with connection.transaction():
            await connection.execute(
                "SELECT set_config('app.current_tenant_id',$1,true)",
                str(tenant_a["tenant"]),
            )
            assert (
                await connection.fetchval("SELECT count(*) FROM catalog_products")
                == 1
            )
            assert (
                await connection.fetchrow(
                    "SELECT id FROM catalog_products WHERE id=$1",
                    tenant_b["product"],
                )
                is None
            )
            assert (
                await connection.fetchrow(
                    "SELECT id FROM catalog_product_variants WHERE id=$1",
                    tenant_b["variant"],
                )
                is None
            )
            assert (
                await connection.fetchrow(
                    "SELECT id FROM catalog_brands WHERE id=$1",
                    tenant_b["brand"],
                )
                is None
            )
            assert (
                await connection.fetchrow(
                    "SELECT id FROM catalog_categories WHERE id=$1",
                    tenant_b["category"],
                )
                is None
            )

            assert (
                await connection.fetchval(
                    "SELECT count(*) FROM catalog_product_stores"
                )
                == 1
            )
            await connection.execute(
                "SELECT set_config('app.current_store_id',$1,true)",
                str(tenant_a["store"]),
            )
            assert (
                await connection.fetchval(
                    "SELECT count(*) FROM catalog_product_stores"
                )
                == 1
            )
            await connection.execute(
                "SELECT set_config('app.current_store_id',$1,true)",
                str(tenant_b["store"]),
            )
            assert (
                await connection.fetchval(
                    "SELECT count(*) FROM catalog_product_stores"
                )
                == 0
            )

            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                async with connection.transaction():
                    await connection.execute(
                        """
                        INSERT INTO catalog_products
                            (id,tenant_id,product_type_id,status,version)
                        VALUES($1,$2,$3,'draft',1)
                        """,
                        uuid4(),
                        tenant_b["tenant"],
                        tenant_b["product_type"],
                    )
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                async with connection.transaction():
                    await connection.execute(
                        """
                        INSERT INTO catalog_product_variants
                            (id,tenant_id,product_id,sku,sku_normalized,is_default,status,version)
                        VALUES($1,$2,$3,'BAD','bad',false,'active',1)
                        """,
                        uuid4(),
                        tenant_b["tenant"],
                        tenant_b["product"],
                    )
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                async with connection.transaction():
                    await connection.execute(
                        """
                        INSERT INTO catalog_brands
                            (id,tenant_id,code,name,slug,status,version)
                        VALUES($1,$2,'bad','Bad','bad','active',1)
                        """,
                        uuid4(),
                        tenant_b["tenant"],
                    )
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                async with connection.transaction():
                    await connection.execute(
                        """
                        INSERT INTO catalog_categories
                            (id,tenant_id,taxonomy_id,code,name,slug,position,status,version)
                        VALUES($1,$2,$3,'bad','Bad','bad',0,'active',1)
                        """,
                        uuid4(),
                        tenant_b["tenant"],
                        tenant_b["taxonomy"],
                    )
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                async with connection.transaction():
                    await connection.execute(
                        """
                        INSERT INTO catalog_product_stores
                            (id,tenant_id,product_id,store_id,status,eligible,version)
                        VALUES($1,$2,$3,$4,'draft',false,1)
                        """,
                        uuid4(),
                        tenant_b["tenant"],
                        tenant_b["product"],
                        tenant_b["store"],
                    )

            assert (
                await connection.execute(
                    "UPDATE catalog_products SET code='bad' WHERE id=$1",
                    tenant_b["product"],
                )
                == "UPDATE 0"
            )
            assert (
                await connection.execute(
                    "DELETE FROM catalog_products WHERE id=$1",
                    tenant_b["product"],
                )
                == "DELETE 0"
            )

        assert await connection.fetch("SELECT * FROM catalog_products") == []
        assert await connection.fetch("SELECT * FROM catalog_product_stores") == []

    async with pool.acquire() as reused:
        assert await reused.fetch("SELECT * FROM catalog_products") == []
        assert await reused.fetch("SELECT * FROM catalog_brands") == []

    await pool.close()

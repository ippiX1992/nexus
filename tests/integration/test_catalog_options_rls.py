import os
from uuid import UUID, uuid4

import asyncpg
import pytest

from tests.integration.test_catalog_api import catalog_context, create_brand, create_store, create_type
from tests.integration.test_catalog_options_api import create_option, create_option_value

pytestmark = pytest.mark.integration


def asyncpg_dsn(value: str) -> str:
    return value.replace("postgresql+asyncpg://", "postgresql://").replace("postgresql+psycopg://", "postgresql://")


APP_DSN = asyncpg_dsn(os.environ["DATABASE_URL"])


async def seed_options_tenant(client, registration, suffix):
    headers, tenant = await catalog_context(client, registration)
    await create_store(client, headers, code=f"store-{suffix}")
    product_type = await create_type(client, headers, code=f"type-{suffix}")
    brand = await create_brand(client, headers, code=f"brand-{suffix}")
    product_response = await client.post(
        "/api/v1/catalog/products",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "product_type_id": product_type["id"],
            "brand_id": brand["id"],
            "code": f"product-{suffix}",
            "sku": f"SKU-{suffix}",
            "translation": {"locale": "es-EC", "name": f"Product {suffix}", "slug": f"product-{suffix}"},
        },
    )
    assert product_response.status_code == 201, product_response.text
    detail = product_response.json()
    option = await create_option(client, headers, code=f"color-{suffix}")
    value = await create_option_value(client, headers, option["id"], code=f"red-{suffix}")
    assign = await client.put(
        f"/api/v1/catalog/products/{detail['product']['id']}/options",
        headers={**headers, "If-Match": str(detail["product"]["version"])},
        json={"options": [{"option_id": option["id"], "position": 0}]},
    )
    assert assign.status_code == 200, assign.text
    variant = await client.post(
        f"/api/v1/catalog/products/{detail['product']['id']}/variants",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"sku": f"SKU-{suffix}-RED", "option_value_ids": [value["id"]]},
    )
    assert variant.status_code == 201, variant.text
    return {
        "headers": headers,
        "tenant_id": tenant["id"],
        "product_id": detail["product"]["id"],
        "option_id": option["id"],
        "value_id": value["id"],
        "variant_id": variant.json()["id"],
    }


async def test_options_rls_blocks_cross_tenant_reads_and_direct_sql(client, registration):
    tenant_a = await seed_options_tenant(client, registration, "a")
    tenant_b = await seed_options_tenant(
        client, {**registration, "email": "catalog-options-rls-b@example.com", "company": "Options RLS B"}, "b"
    )

    # Cross-tenant via the API: tenant B's token cannot see tenant A's Option.
    cross = await client.get(f"/api/v1/catalog/options/{tenant_a['option_id']}", headers=tenant_b["headers"])
    assert cross.status_code == 404

    cross_value = await client.get(
        f"/api/v1/catalog/options/{tenant_a['option_id']}/values", headers=tenant_b["headers"]
    )
    assert cross_value.status_code == 404

    cross_product_options = await client.get(
        f"/api/v1/catalog/products/{tenant_a['product_id']}/options", headers=tenant_b["headers"]
    )
    assert cross_product_options.status_code == 404

    # Direct SQL as the application role (RLS-bound), no tenant context set --
    # must see nothing across all six new tables, not just Options.
    connection = await asyncpg.connect(APP_DSN)
    try:
        for table in (
            "catalog_options", "catalog_option_translations", "catalog_option_values",
            "catalog_option_value_translations", "catalog_product_options", "catalog_variant_option_values",
        ):
            rows = await connection.fetch(f"SELECT 1 FROM {table} LIMIT 1")
            assert rows == [], f"{table} leaked rows without app.current_tenant_id set"

        # With tenant A's context set, tenant B's rows must not be visible either.
        await connection.execute("SELECT set_config('app.current_tenant_id', $1, false)", tenant_a["tenant_id"])
        option_ids = {row["id"] for row in await connection.fetch("SELECT id FROM catalog_options")}
        assert option_ids == {UUID(tenant_a["option_id"])}
    finally:
        await connection.close()


async def test_option_value_belonging_to_unrelated_option_is_rejected(client, registration):
    headers, _ = await catalog_context(client, registration)
    await create_store(client, headers)
    product_type = await create_type(client, headers)
    product_response = await client.post(
        "/api/v1/catalog/products",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "product_type_id": product_type["id"],
            "code": "product-x",
            "sku": "SKU-X",
            "translation": {"locale": "es-EC", "name": "Product X", "slug": "product-x"},
        },
    )
    detail = product_response.json()
    color = await create_option(client, headers, code="color")
    red = await create_option_value(client, headers, color["id"], code="red")
    size = await create_option(client, headers, code="size")  # NOT assigned to the product
    small = await create_option_value(client, headers, size["id"], code="s", value="S")

    assign = await client.put(
        f"/api/v1/catalog/products/{detail['product']['id']}/options",
        headers={**headers, "If-Match": str(detail["product"]["version"])},
        json={"options": [{"option_id": color["id"], "position": 0}]},
    )
    assert assign.status_code == 200, assign.text

    # "size"/"small" is a real Option Value, just not one assigned to this
    # Product -- must be rejected, not silently accepted.
    rejected = await client.post(
        f"/api/v1/catalog/products/{detail['product']['id']}/variants",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"sku": "PRODUCT-X-WRONG", "option_value_ids": [red["id"], small["id"]]},
    )
    assert rejected.status_code == 422, rejected.text


async def test_archived_option_value_rejected_on_new_assignment_but_kept_on_existing_variant(client, registration):
    seed = await seed_options_tenant(client, registration, "archive")
    archive = await client.post(
        f"/api/v1/catalog/option-values/{seed['value_id']}/archive",
        headers={**seed["headers"], "If-Match": "1"},
    )
    assert archive.status_code == 200, archive.text

    existing_variant = await client.get(
        f"/api/v1/catalog/products/{seed['product_id']}/variants?limit=10", headers=seed["headers"]
    )
    assert any(item["id"] == seed["variant_id"] for item in existing_variant.json()["items"])

    new_attempt = await client.post(
        f"/api/v1/catalog/products/{seed['product_id']}/variants",
        headers={**seed["headers"], "Idempotency-Key": str(uuid4())},
        json={"sku": "NEW-WITH-ARCHIVED-VALUE", "option_value_ids": [seed["value_id"]]},
    )
    assert new_attempt.status_code == 422, new_attempt.text

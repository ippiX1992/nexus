import os
from uuid import UUID, uuid4

import asyncpg
import pytest

from tests.integration.test_catalog_api import catalog_context, create_brand, create_store, create_type
from tests.integration.test_catalog_attributes_api import create_attribute, create_attribute_option

pytestmark = pytest.mark.integration


def asyncpg_dsn(value: str) -> str:
    return value.replace("postgresql+asyncpg://", "postgresql://").replace("postgresql+psycopg://", "postgresql://")


APP_DSN = asyncpg_dsn(os.environ["DATABASE_URL"])


async def seed_attributes_tenant(client, registration, suffix):
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
    attribute = await create_attribute(client, headers, code=f"power-{suffix}", data_type="DECIMAL")
    material = await create_attribute(client, headers, code=f"material-{suffix}", data_type="SELECT")
    option = await create_attribute_option(client, headers, material["id"], code=f"steel-{suffix}")
    assign = await client.put(
        f"/api/v1/catalog/product-types/{product_type['id']}/attributes",
        headers={**headers, "If-Match": str(product_type["version"])},
        json={
            "attributes": [
                {"attribute_id": attribute["id"], "position": 0, "required": True},
                {"attribute_id": material["id"], "position": 1, "required": False},
            ]
        },
    )
    assert assign.status_code == 200, assign.text
    value = await client.put(
        f"/api/v1/catalog/products/{detail['product']['id']}/attributes",
        headers={**headers, "If-Match": str(detail["product"]["version"])},
        json={"values": [{"attribute_id": attribute["id"], "value": "100"}]},
    )
    assert value.status_code == 200, value.text
    return {
        "headers": headers,
        "tenant_id": tenant["id"],
        "product_id": detail["product"]["id"],
        "product_type_id": product_type["id"],
        "attribute_id": attribute["id"],
        "material_id": material["id"],
        "option_id": option["id"],
    }


async def test_attributes_rls_blocks_cross_tenant_reads_and_direct_sql(client, registration):
    tenant_a = await seed_attributes_tenant(client, registration, "a")
    tenant_b = await seed_attributes_tenant(
        client, {**registration, "email": "catalog-attributes-rls-b@example.com", "company": "Attributes RLS B"}, "b"
    )

    cross = await client.get(f"/api/v1/catalog/attributes/{tenant_a['attribute_id']}", headers=tenant_b["headers"])
    assert cross.status_code == 404

    cross_options = await client.get(
        f"/api/v1/catalog/attributes/{tenant_a['material_id']}/options", headers=tenant_b["headers"]
    )
    assert cross_options.status_code == 404

    cross_product_type_attributes = await client.get(
        f"/api/v1/catalog/product-types/{tenant_a['product_type_id']}/attributes", headers=tenant_b["headers"]
    )
    assert cross_product_type_attributes.status_code == 404

    cross_product_values = await client.get(
        f"/api/v1/catalog/products/{tenant_a['product_id']}/attributes", headers=tenant_b["headers"]
    )
    assert cross_product_values.status_code == 404

    connection = await asyncpg.connect(APP_DSN)
    try:
        for table in (
            "catalog_attributes",
            "catalog_attribute_translations",
            "catalog_attribute_options",
            "catalog_attribute_option_translations",
            "catalog_attribute_groups",
            "catalog_attribute_group_translations",
            "catalog_product_type_attributes",
            "catalog_product_attribute_values",
            "catalog_product_attribute_value_options",
        ):
            rows = await connection.fetch(f"SELECT 1 FROM {table} LIMIT 1")
            assert rows == [], f"{table} leaked rows without app.current_tenant_id set"

        await connection.execute("SELECT set_config('app.current_tenant_id', $1, false)", tenant_a["tenant_id"])
        attribute_ids = {row["id"] for row in await connection.fetch("SELECT id FROM catalog_attributes")}
        assert attribute_ids == {UUID(tenant_a["attribute_id"]), UUID(tenant_a["material_id"])}
    finally:
        await connection.close()


async def test_attribute_option_belonging_to_unrelated_attribute_is_rejected(client, registration):
    headers, _ = await catalog_context(client, registration)
    material = await create_attribute(client, headers, code="material", data_type="SELECT")
    color = await create_attribute(client, headers, code="color", data_type="SELECT")
    material_option = await create_attribute_option(client, headers, material["id"], code="steel")

    await create_store(client, headers)
    product_type = await create_type(client, headers)
    product_response = await client.post(
        "/api/v1/catalog/products",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "product_type_id": product_type["id"],
            "code": "product-cross-attribute",
            "sku": "SKU-CROSS-ATTR",
            "translation": {"locale": "es-EC", "name": "Product Cross", "slug": "product-cross-attribute"},
        },
    )
    assert product_response.status_code == 201, product_response.text
    detail = product_response.json()

    assign = await client.put(
        f"/api/v1/catalog/product-types/{product_type['id']}/attributes",
        headers={**headers, "If-Match": str(product_type["version"])},
        json={"attributes": [{"attribute_id": color["id"], "position": 0}]},
    )
    assert assign.status_code == 200, assign.text

    rejected = await client.put(
        f"/api/v1/catalog/products/{detail['product']['id']}/attributes",
        headers={**headers, "If-Match": str(detail["product"]["version"])},
        json={"values": [{"attribute_id": color["id"], "value": material_option["id"]}]},
    )
    assert rejected.status_code == 422, rejected.text

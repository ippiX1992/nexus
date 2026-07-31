import os
from uuid import UUID, uuid4

import asyncpg
import pytest

from tests.integration.test_catalog_api import catalog_context, create_product, create_store, create_type
from tests.integration.test_inventory_api import create_location, create_warehouse, receive

pytestmark = pytest.mark.integration


def asyncpg_dsn(value: str) -> str:
    return value.replace("postgresql+asyncpg://", "postgresql://").replace("postgresql+psycopg://", "postgresql://")


APP_DSN = asyncpg_dsn(os.environ["DATABASE_URL"])


async def seed_inventory_tenant(client, registration, suffix):
    headers, tenant = await catalog_context(
        client, {**registration, "email": f"inventory-rls-{suffix}@example.com", "company": f"Inventory RLS {suffix}"}
    )
    await create_store(client, headers, code=f"store-{suffix}")
    product_type = await create_type(client, headers, code=f"type-{suffix}")
    product_response, _ = await create_product(
        client, headers, product_type["id"], sku=f"RLS-{suffix.upper()}", code=f"product-{suffix}"
    )
    assert product_response.status_code == 201, product_response.text
    variant_id = product_response.json()["variants"][0]["id"]
    warehouse = await create_warehouse(client, headers, code=f"wh-{suffix}")
    location = await create_location(client, headers, warehouse["id"], code=f"loc-{suffix}")
    await receive(client, headers, location["id"], variant_id, 5)
    return {
        "headers": headers,
        "tenant_id": tenant["id"],
        "warehouse_id": warehouse["id"],
        "location_id": location["id"],
        "variant_id": variant_id,
    }


async def test_inventory_rls_blocks_cross_tenant_reads_and_direct_sql(client, registration):
    tenant_a = await seed_inventory_tenant(client, registration, "a")
    tenant_b = await seed_inventory_tenant(client, registration, "b")

    cross_warehouse = await client.get(
        f"/api/v1/inventory/warehouses/{tenant_a['warehouse_id']}", headers=tenant_b["headers"]
    )
    assert cross_warehouse.status_code == 404
    cross_stock = await client.get(
        f"/api/v1/inventory/stock?variant_id={tenant_a['variant_id']}", headers=tenant_b["headers"]
    )
    assert cross_stock.status_code == 200
    assert cross_stock.json()["items"] == []  # tenant B sees none of tenant A's stock

    connection = await asyncpg.connect(APP_DSN)
    try:
        for table in (
            "inventory_warehouses",
            "inventory_locations",
            "inventory_stock_levels",
            "inventory_ledger_entries",
            "inventory_transfers",
            "inventory_reservations",
            "inventory_fulfillment_scopes",
        ):
            rows = await connection.fetch(f"SELECT 1 FROM {table} LIMIT 1")
            assert rows == [], f"{table} leaked rows without app.current_tenant_id set"

        await connection.execute("SELECT set_config('app.current_tenant_id', $1, false)", tenant_a["tenant_id"])
        warehouse_ids = {row["id"] for row in await connection.fetch("SELECT id FROM inventory_warehouses")}
        assert warehouse_ids == {UUID(tenant_a["warehouse_id"])}
    finally:
        await connection.close()


async def test_cross_tenant_transfer_is_rejected(client, registration):
    tenant_a = await seed_inventory_tenant(client, registration, "x")
    tenant_b = await seed_inventory_tenant(client, registration, "y")
    # Tenant B cannot transfer using tenant A's locations/variant (they are invisible -> 404).
    response = await client.post(
        "/api/v1/inventory/transfers",
        headers={**tenant_b["headers"], "Idempotency-Key": str(uuid4())},
        json={
            "from_location_id": tenant_a["location_id"],
            "to_location_id": tenant_b["location_id"],
            "variant_id": tenant_a["variant_id"],
            "quantity": 1,
        },
    )
    assert response.status_code == 404, response.text

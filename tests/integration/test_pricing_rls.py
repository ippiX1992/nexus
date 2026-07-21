import os
from uuid import UUID, uuid4

import asyncpg
import pytest

from tests.integration.test_catalog_api import catalog_context, create_product, create_store, create_type
from tests.integration.test_pricing_api import create_channel, create_price_list

pytestmark = pytest.mark.integration


def asyncpg_dsn(value: str) -> str:
    return value.replace("postgresql+asyncpg://", "postgresql://").replace("postgresql+psycopg://", "postgresql://")


APP_DSN = asyncpg_dsn(os.environ["DATABASE_URL"])


async def seed_pricing_tenant(client, registration, suffix):
    headers, tenant = await catalog_context(
        client, {**registration, "email": f"pricing-rls-{suffix}@example.com", "company": f"Pricing RLS {suffix}"}
    )
    store = await create_store(client, headers, code=f"store-{suffix}")
    channel = await create_channel(client, headers, store["id"], code=f"web-{suffix}")
    product_type = await create_type(client, headers, code=f"type-{suffix}")
    product_response, _ = await create_product(
        client, headers, product_type["id"], sku=f"RLS-{suffix.upper()}", code=f"product-{suffix}"
    )
    assert product_response.status_code == 201, product_response.text
    variant_id = product_response.json()["variants"][0]["id"]
    price_list = await create_price_list(client, headers, code=f"list-{suffix}")
    entry = await client.put(
        f"/api/v1/pricing/price-lists/{price_list['id']}/entries/{variant_id}",
        headers=headers,
        json={"unit_amount": "42.00"},
    )
    assert entry.status_code == 200, entry.text
    assignment = await client.post(
        "/api/v1/pricing/assignments",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"price_list_id": price_list["id"], "scope_type": "channel", "channel_id": channel["id"], "priority": 0},
    )
    assert assignment.status_code == 201, assignment.text
    override = await client.post(
        "/api/v1/pricing/variant-overrides",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "variant_id": variant_id, "scope_type": "channel", "channel_id": channel["id"],
            "unit_amount": "1.00", "currency_code": "USD",
        },
    )
    assert override.status_code == 201, override.text
    return {
        "headers": headers,
        "tenant_id": tenant["id"],
        "price_list_id": price_list["id"],
        "assignment_id": assignment.json()["id"],
        "override_id": override.json()["id"],
        "variant_id": variant_id,
    }


async def test_pricing_rls_blocks_cross_tenant_reads_and_direct_sql(client, registration):
    tenant_a = await seed_pricing_tenant(client, registration, "a")
    tenant_b = await seed_pricing_tenant(client, registration, "b")

    cross_list = await client.get(f"/api/v1/pricing/price-lists/{tenant_a['price_list_id']}", headers=tenant_b["headers"])
    assert cross_list.status_code == 404
    cross_assignment = await client.get(f"/api/v1/pricing/assignments/{tenant_a['assignment_id']}", headers=tenant_b["headers"])
    assert cross_assignment.status_code == 404
    cross_override = await client.get(f"/api/v1/pricing/variant-overrides/{tenant_a['override_id']}", headers=tenant_b["headers"])
    assert cross_override.status_code == 404
    cross_resolve = await client.get(
        f"/api/v1/pricing/resolve?variant_id={tenant_a['variant_id']}", headers=tenant_b["headers"]
    )
    assert cross_resolve.status_code in (404, 422)  # variant itself is invisible cross-tenant

    connection = await asyncpg.connect(APP_DSN)
    try:
        for table in (
            "pricing_price_lists",
            "pricing_price_list_entries",
            "pricing_price_list_assignments",
            "pricing_variant_price_overrides",
            "pricing_price_history",
        ):
            rows = await connection.fetch(f"SELECT 1 FROM {table} LIMIT 1")
            assert rows == [], f"{table} leaked rows without app.current_tenant_id set"

        await connection.execute("SELECT set_config('app.current_tenant_id', $1, false)", tenant_a["tenant_id"])
        price_list_ids = {row["id"] for row in await connection.fetch("SELECT id FROM pricing_price_lists")}
        assert price_list_ids == {UUID(tenant_a["price_list_id"])}
    finally:
        await connection.close()

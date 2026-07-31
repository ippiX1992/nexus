import asyncio
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.integration.test_catalog_api import catalog_context
from tests.integration.test_inventory_api import create_location, create_warehouse, receive, seed_variant
from tests.integration.test_pricing_api import create_channel


async def isolated_client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


pytestmark = pytest.mark.integration


async def test_concurrent_reservations_cannot_oversell(client, registration):
    """The single physical unit of protection is the row-level SELECT ... FOR
    UPDATE on the stock level inside the reservation engine. With exactly 3
    units in stock and two concurrent 3-unit reservation attempts, the row
    lock must serialize them so exactly one wins (201) and the other is told
    there is not enough stock (409) -- never both succeeding into a negative
    available."""
    headers, _ = await catalog_context(client, registration)
    variant = await seed_variant(client, headers)
    store = (await client.get("/api/v1/stores", headers=headers)).json()[0]
    channel = await create_channel(client, headers, store["id"])
    warehouse = await create_warehouse(client, headers)
    location = await create_location(client, headers, warehouse["id"])
    await receive(client, headers, location["id"], variant["id"], 3)
    await client.post(
        "/api/v1/inventory/fulfillment-scopes",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"warehouse_id": warehouse["id"], "scope_type": "channel", "channel_id": channel["id"], "priority": 1},
    )

    async def attempt():
        async with await isolated_client() as caller:
            return await caller.post(
                "/api/v1/inventory/reservations",
                headers={**headers, "Idempotency-Key": str(uuid4())},
                json={"variant_id": variant["id"], "quantity": 3, "scope_type": "channel", "scope_id": channel["id"]},
            )

    first, second = await asyncio.gather(attempt(), attempt())
    codes = sorted([first.status_code, second.status_code])
    assert codes == [201, 409], f"expected exactly one winner, got {codes}"

    stock = await client.get(
        f"/api/v1/inventory/stock?variant_id={variant['id']}&location_id={location['id']}", headers=headers
    )
    level = stock.json()["items"][0]
    assert level["reserved"] == 3
    assert level["available"] == 0
    assert level["on_hand"] == 3


async def test_concurrent_warehouse_archive_has_exactly_one_winner(client, registration):
    headers, _ = await catalog_context(client, registration)
    warehouse = await create_warehouse(client, headers)

    async def attempt():
        async with await isolated_client() as caller:
            return await caller.post(
                f"/api/v1/inventory/warehouses/{warehouse['id']}/archive",
                headers={**headers, "If-Match": str(warehouse["version"])},
            )

    first, second = await asyncio.gather(attempt(), attempt())
    codes = sorted([first.status_code, second.status_code])
    assert codes == [200, 409]

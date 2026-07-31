"""M4.1 Inventory Engine: warehouses/locations, stock receive/adjust/recount,
the append-only ledger, transfers, the allocation + reservation engines
(hold/release/commit), fulfillment-scope-driven allocation, idempotency and
outbox evidence -- all against a real PostgreSQL, no mocks."""

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.infrastructure.database import SessionFactory
from app.infrastructure.tenant_context import set_tenant_context
from app.modules.platform.infrastructure.models import OutboxEventModel
from tests.integration.test_catalog_api import catalog_context, create_product, create_store, create_type
from tests.integration.test_pricing_api import create_channel

pytestmark = pytest.mark.integration


async def create_warehouse(client, headers, *, code="wh-main", name="Main Warehouse"):
    response = await client.post(
        "/api/v1/inventory/warehouses",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"code": code, "name": name, "country_code": "EC"},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_location(client, headers, warehouse_id, *, code="a1", name="Aisle 1"):
    response = await client.post(
        f"/api/v1/inventory/warehouses/{warehouse_id}/locations",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"code": code, "name": name, "location_type": "storage"},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def seed_variant(client, headers, *, sku="INV-001", code="inventory-product"):
    await create_store(client, headers)
    product_type = await create_type(client, headers)
    response, _ = await create_product(client, headers, product_type["id"], sku=sku, code=code)
    assert response.status_code == 201, response.text
    return response.json()["variants"][0]


async def receive(client, headers, location_id, variant_id, quantity):
    response = await client.post(
        f"/api/v1/inventory/locations/{location_id}/variants/{variant_id}/receive",
        headers=headers,
        json={"quantity": quantity},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_warehouse_creation_is_idempotent_and_emits_outbox_event(client, registration):
    headers, tenant = await catalog_context(client, registration)
    key = str(uuid4())
    payload = {"code": "wh-1", "name": "Warehouse One", "country_code": "EC"}
    first = await client.post("/api/v1/inventory/warehouses", headers={**headers, "Idempotency-Key": key}, json=payload)
    assert first.status_code == 201, first.text
    second = await client.post("/api/v1/inventory/warehouses", headers={**headers, "Idempotency-Key": key}, json=payload)
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]

    async with SessionFactory() as db:
        await set_tenant_context(db, tenant["id"])
        events = (
            await db.execute(
                select(OutboxEventModel).where(
                    OutboxEventModel.tenant_id == tenant["id"],
                    OutboxEventModel.event_type == "inventory.warehouse.created.v1",
                )
            )
        ).scalars().all()
        assert len(events) == 1


async def test_receive_adjust_recount_lifecycle_and_ledger(client, registration):
    headers, _ = await catalog_context(client, registration)
    variant = await seed_variant(client, headers)
    warehouse = await create_warehouse(client, headers)
    location = await create_location(client, headers, warehouse["id"])

    received = await receive(client, headers, location["id"], variant["id"], 10)
    assert received["on_hand"] == 10
    assert received["available"] == 10
    assert received["reserved"] == 0

    adjusted = await client.post(
        f"/api/v1/inventory/locations/{location['id']}/variants/{variant['id']}/adjust",
        headers=headers,
        json={"delta": -3, "reason": "damaged"},
    )
    assert adjusted.status_code == 200, adjusted.text
    assert adjusted.json()["on_hand"] == 7

    recounted = await client.post(
        f"/api/v1/inventory/locations/{location['id']}/variants/{variant['id']}/recount",
        headers=headers,
        json={"counted": 5, "reason": "cycle count"},
    )
    assert recounted.status_code == 200, recounted.text
    assert recounted.json()["on_hand"] == 5

    ledger = await client.get(f"/api/v1/inventory/ledger?variant_id={variant['id']}", headers=headers)
    assert ledger.status_code == 200, ledger.text
    entry_types = [row["entry_type"] for row in ledger.json()["items"]]
    assert "receipt" in entry_types
    assert "adjustment" in entry_types
    assert "recount" in entry_types


async def test_adjustment_cannot_drive_stock_negative(client, registration):
    headers, _ = await catalog_context(client, registration)
    variant = await seed_variant(client, headers)
    warehouse = await create_warehouse(client, headers)
    location = await create_location(client, headers, warehouse["id"])
    await receive(client, headers, location["id"], variant["id"], 2)
    response = await client.post(
        f"/api/v1/inventory/locations/{location['id']}/variants/{variant['id']}/adjust",
        headers=headers,
        json={"delta": -5},
    )
    assert response.status_code == 409, response.text


async def test_transfer_moves_stock_and_tracks_incoming(client, registration):
    headers, _ = await catalog_context(client, registration)
    variant = await seed_variant(client, headers)
    warehouse = await create_warehouse(client, headers)
    source = await create_location(client, headers, warehouse["id"], code="src", name="Source")
    destination = await create_location(client, headers, warehouse["id"], code="dst", name="Dest")
    await receive(client, headers, source["id"], variant["id"], 10)

    transfer = await client.post(
        "/api/v1/inventory/transfers",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "from_location_id": source["id"], "to_location_id": destination["id"],
            "variant_id": variant["id"], "quantity": 4,
        },
    )
    assert transfer.status_code == 201, transfer.text
    transfer_body = transfer.json()

    # Source dropped by 4; destination shows 4 incoming, 0 on_hand until completion.
    src_stock = await client.get(
        f"/api/v1/inventory/stock?variant_id={variant['id']}&location_id={source['id']}", headers=headers
    )
    assert src_stock.json()["items"][0]["on_hand"] == 6
    dst_stock = await client.get(
        f"/api/v1/inventory/stock?variant_id={variant['id']}&location_id={destination['id']}", headers=headers
    )
    assert dst_stock.json()["items"][0]["incoming"] == 4
    assert dst_stock.json()["items"][0]["on_hand"] == 0

    completed = await client.post(
        f"/api/v1/inventory/transfers/{transfer_body['id']}/complete",
        headers={**headers, "If-Match": str(transfer_body["version"])},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed"
    dst_stock = await client.get(
        f"/api/v1/inventory/stock?variant_id={variant['id']}&location_id={destination['id']}", headers=headers
    )
    assert dst_stock.json()["items"][0]["on_hand"] == 4
    assert dst_stock.json()["items"][0]["incoming"] == 0


async def test_cancel_transfer_returns_stock_to_source(client, registration):
    headers, _ = await catalog_context(client, registration)
    variant = await seed_variant(client, headers)
    warehouse = await create_warehouse(client, headers)
    source = await create_location(client, headers, warehouse["id"], code="src", name="Source")
    destination = await create_location(client, headers, warehouse["id"], code="dst", name="Dest")
    await receive(client, headers, source["id"], variant["id"], 10)
    transfer = await client.post(
        "/api/v1/inventory/transfers",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "from_location_id": source["id"], "to_location_id": destination["id"],
            "variant_id": variant["id"], "quantity": 4,
        },
    )
    body = transfer.json()
    cancelled = await client.post(
        f"/api/v1/inventory/transfers/{body['id']}/cancel", headers={**headers, "If-Match": str(body["version"])}
    )
    assert cancelled.status_code == 200, cancelled.text
    src_stock = await client.get(
        f"/api/v1/inventory/stock?variant_id={variant['id']}&location_id={source['id']}", headers=headers
    )
    assert src_stock.json()["items"][0]["on_hand"] == 10


async def test_allocation_and_reservation_across_prioritized_warehouses(client, registration):
    headers, _ = await catalog_context(client, registration)
    variant = await seed_variant(client, headers)
    store = (await client.get("/api/v1/stores", headers=headers)).json()[0]
    channel = await create_channel(client, headers, store["id"])

    # Two warehouses serving the same channel at different priorities.
    high_wh = await create_warehouse(client, headers, code="wh-high", name="High Priority")
    low_wh = await create_warehouse(client, headers, code="wh-low", name="Low Priority")
    high_loc = await create_location(client, headers, high_wh["id"], code="h1")
    low_loc = await create_location(client, headers, low_wh["id"], code="l1")
    await receive(client, headers, high_loc["id"], variant["id"], 3)
    await receive(client, headers, low_loc["id"], variant["id"], 10)

    for warehouse_id, priority in ((high_wh["id"], 10), (low_wh["id"], 1)):
        scope = await client.post(
            "/api/v1/inventory/fulfillment-scopes",
            headers={**headers, "Idempotency-Key": str(uuid4())},
            json={"warehouse_id": warehouse_id, "scope_type": "channel", "channel_id": channel["id"], "priority": priority},
        )
        assert scope.status_code == 201, scope.text

    # Allocation preview: 5 units -> 3 from high priority, 2 from low.
    plan = await client.get(
        f"/api/v1/inventory/allocate?variant_id={variant['id']}&quantity=5&scope_type=channel&scope_id={channel['id']}",
        headers=headers,
    )
    assert plan.status_code == 200, plan.text
    assert plan.json()["fully_allocated"] is True
    assert plan.json()["allocated"] == 5
    quantities = sorted(line["quantity"] for line in plan.json()["allocations"])
    assert quantities == [2, 3]

    # Reservation actually holds the stock and drops available.
    reservation = await client.post(
        "/api/v1/inventory/reservations",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"variant_id": variant["id"], "quantity": 5, "scope_type": "channel", "scope_id": channel["id"]},
    )
    assert reservation.status_code == 201, reservation.text
    held = reservation.json()["items"]
    assert sum(item["quantity"] for item in held) == 5

    high_stock = await client.get(
        f"/api/v1/inventory/stock?variant_id={variant['id']}&location_id={high_loc['id']}", headers=headers
    )
    assert high_stock.json()["items"][0]["reserved"] == 3
    assert high_stock.json()["items"][0]["available"] == 0


async def test_reservation_commit_consumes_on_hand(client, registration):
    headers, _ = await catalog_context(client, registration)
    variant = await seed_variant(client, headers)
    store = (await client.get("/api/v1/stores", headers=headers)).json()[0]
    warehouse = await create_warehouse(client, headers)
    location = await create_location(client, headers, warehouse["id"])
    await receive(client, headers, location["id"], variant["id"], 10)
    await client.post(
        "/api/v1/inventory/fulfillment-scopes",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"warehouse_id": warehouse["id"], "scope_type": "store", "store_id": store["id"], "priority": 1},
    )
    reservation = await client.post(
        "/api/v1/inventory/reservations",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"variant_id": variant["id"], "quantity": 4, "scope_type": "store", "scope_id": store["id"]},
    )
    assert reservation.status_code == 201, reservation.text
    held = reservation.json()["items"][0]

    committed = await client.post(
        f"/api/v1/inventory/reservations/{held['id']}/commit", headers={**headers, "If-Match": str(held["version"])}
    )
    assert committed.status_code == 200, committed.text
    assert committed.json()["status"] == "committed"
    stock = await client.get(
        f"/api/v1/inventory/stock?variant_id={variant['id']}&location_id={location['id']}", headers=headers
    )
    assert stock.json()["items"][0]["on_hand"] == 6
    assert stock.json()["items"][0]["reserved"] == 0


async def test_reservation_release_returns_available(client, registration):
    headers, _ = await catalog_context(client, registration)
    variant = await seed_variant(client, headers)
    store = (await client.get("/api/v1/stores", headers=headers)).json()[0]
    warehouse = await create_warehouse(client, headers)
    location = await create_location(client, headers, warehouse["id"])
    await receive(client, headers, location["id"], variant["id"], 10)
    await client.post(
        "/api/v1/inventory/fulfillment-scopes",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"warehouse_id": warehouse["id"], "scope_type": "store", "store_id": store["id"], "priority": 1},
    )
    reservation = await client.post(
        "/api/v1/inventory/reservations",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"variant_id": variant["id"], "quantity": 4, "scope_type": "store", "scope_id": store["id"]},
    )
    held = reservation.json()["items"][0]
    released = await client.post(
        f"/api/v1/inventory/reservations/{held['id']}/release", headers={**headers, "If-Match": str(held["version"])}
    )
    assert released.status_code == 200, released.text
    stock = await client.get(
        f"/api/v1/inventory/stock?variant_id={variant['id']}&location_id={location['id']}", headers=headers
    )
    assert stock.json()["items"][0]["reserved"] == 0
    assert stock.json()["items"][0]["available"] == 10


async def test_reservation_rejected_when_scope_has_insufficient_stock(client, registration):
    headers, _ = await catalog_context(client, registration)
    variant = await seed_variant(client, headers)
    store = (await client.get("/api/v1/stores", headers=headers)).json()[0]
    warehouse = await create_warehouse(client, headers)
    location = await create_location(client, headers, warehouse["id"])
    await receive(client, headers, location["id"], variant["id"], 2)
    await client.post(
        "/api/v1/inventory/fulfillment-scopes",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"warehouse_id": warehouse["id"], "scope_type": "store", "store_id": store["id"], "priority": 1},
    )
    response = await client.post(
        "/api/v1/inventory/reservations",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"variant_id": variant["id"], "quantity": 5, "scope_type": "store", "scope_id": store["id"]},
    )
    assert response.status_code == 409, response.text


async def test_archive_warehouse_requires_correct_if_match(client, registration):
    headers, _ = await catalog_context(client, registration)
    warehouse = await create_warehouse(client, headers)
    stale = await client.post(
        f"/api/v1/inventory/warehouses/{warehouse['id']}/archive", headers={**headers, "If-Match": "99"}
    )
    assert stale.status_code == 409, stale.text
    fresh = await client.post(
        f"/api/v1/inventory/warehouses/{warehouse['id']}/archive",
        headers={**headers, "If-Match": str(warehouse["version"])},
    )
    assert fresh.status_code == 200, fresh.text
    assert fresh.json()["status"] == "archived"

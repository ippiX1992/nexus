"""M4.0 Pricing Engine: happy-path CRUD for Price Lists, entries, Assignments,
Variant Price Overrides, resolution priority, history, idempotency and
outbox evidence -- all against a real PostgreSQL, no mocks."""

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.infrastructure.database import SessionFactory
from app.infrastructure.tenant_context import set_tenant_context
from app.modules.platform.infrastructure.models import OutboxEventModel
from tests.integration.test_catalog_api import catalog_context, create_product, create_store, create_type

pytestmark = pytest.mark.integration


async def create_channel(client, headers, store_id, *, code="web", channel_type="web"):
    response = await client.post(
        f"/api/v1/stores/{store_id}/channels",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"code": code, "name": code.title(), "channel_type": channel_type},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_market(client, headers, store_id, *, code="ec"):
    response = await client.post(
        f"/api/v1/stores/{store_id}/markets",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "code": code,
            "name": code.upper(),
            "country_code": "EC",
            "currency_code": "USD",
            "default_locale": "es-EC",
            "timezone": "America/Guayaquil",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_price_list(client, headers, *, code="default", currency_code="USD", is_default=False):
    response = await client.post(
        "/api/v1/pricing/price-lists",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"code": code, "name": code.title(), "currency_code": currency_code, "is_default": is_default},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def seed_variant(client, headers):
    store = await create_store(client, headers)
    product_type = await create_type(client, headers)
    response, _ = await create_product(client, headers, product_type["id"], sku="PRC-001", code="pricing-product")
    assert response.status_code == 201, response.text
    detail = response.json()
    return store, detail["variants"][0]


async def test_price_list_creation_is_idempotent_and_emits_outbox_event(client, registration):
    headers, tenant = await catalog_context(client, registration)
    key = str(uuid4())
    payload = {"code": "wholesale", "name": "Wholesale", "currency_code": "usd", "is_default": False}
    first = await client.post("/api/v1/pricing/price-lists", headers={**headers, "Idempotency-Key": key}, json=payload)
    assert first.status_code == 201, first.text
    assert first.json()["currency_code"] == "USD"  # normalized to uppercase
    second = await client.post("/api/v1/pricing/price-lists", headers={**headers, "Idempotency-Key": key}, json=payload)
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]

    async with SessionFactory() as db:
        await set_tenant_context(db, tenant["id"])
        events = (
            await db.execute(
                select(OutboxEventModel).where(
                    OutboxEventModel.tenant_id == tenant["id"],
                    OutboxEventModel.event_type == "pricing.price_list.created.v1",
                )
            )
        ).scalars().all()
        assert len(events) == 1


async def test_only_one_default_price_list_per_tenant(client, registration):
    headers, _ = await catalog_context(client, registration)
    await create_price_list(client, headers, code="default-a", is_default=True)
    second = await client.post(
        "/api/v1/pricing/price-lists",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"code": "default-b", "name": "Default B", "currency_code": "USD", "is_default": True},
    )
    assert second.status_code == 409, second.text


async def test_price_list_entry_set_records_history_and_updates_on_second_call(client, registration):
    headers, tenant = await catalog_context(client, registration)
    _, variant = await seed_variant(client, headers)
    price_list = await create_price_list(client, headers, code="retail")

    first = await client.put(
        f"/api/v1/pricing/price-lists/{price_list['id']}/entries/{variant['id']}",
        headers=headers,
        json={"unit_amount": "10.00", "compare_at_amount": "15.00", "msrp_amount": "20.00", "cost_amount": "4.00"},
    )
    assert first.status_code == 200, first.text
    entry = first.json()
    assert entry["unit_amount"] == "10.0000"  # Numeric(19,4) always serializes at full scale
    assert entry["version"] == 1

    second = await client.put(
        f"/api/v1/pricing/price-lists/{price_list['id']}/entries/{variant['id']}",
        headers=headers,
        json={"unit_amount": "12.50", "compare_at_amount": "15.00", "msrp_amount": "20.00", "cost_amount": "4.00"},
    )
    assert second.status_code == 200, second.text
    assert second.json()["id"] == entry["id"]
    assert second.json()["unit_amount"] == "12.5000"
    assert second.json()["version"] == 2

    history = await client.get(f"/api/v1/pricing/price-history?variant_id={variant['id']}", headers=headers)
    assert history.status_code == 200, history.text
    fields_changed = {row["field_name"] for row in history.json()["items"]}
    assert "unit_amount" in fields_changed
    unit_amount_entries = [row for row in history.json()["items"] if row["field_name"] == "unit_amount"]
    assert any(row["previous_amount"] == "10.0000" and row["new_amount"] == "12.5000" for row in unit_amount_entries)


async def test_resolution_priority_override_beats_assignment_beats_default(client, registration):
    headers, _ = await catalog_context(client, registration)
    store, variant = await seed_variant(client, headers)
    channel = await create_channel(client, headers, store["id"])

    default_list = await create_price_list(client, headers, code="tenant-default", is_default=True)
    await client.put(
        f"/api/v1/pricing/price-lists/{default_list['id']}/entries/{variant['id']}",
        headers=headers,
        json={"unit_amount": "100.00"},
    )

    resolved_default = await client.get(
        f"/api/v1/pricing/resolve?variant_id={variant['id']}&channel_id={channel['id']}", headers=headers
    )
    assert resolved_default.status_code == 200, resolved_default.text
    assert resolved_default.json()["source"] == "default"
    assert resolved_default.json()["unit_amount"] == "100.0000"

    channel_list = await create_price_list(client, headers, code="channel-web")
    await client.put(
        f"/api/v1/pricing/price-lists/{channel_list['id']}/entries/{variant['id']}",
        headers=headers,
        json={"unit_amount": "80.00"},
    )
    assignment = await client.post(
        "/api/v1/pricing/assignments",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"price_list_id": channel_list["id"], "scope_type": "channel", "channel_id": channel["id"], "priority": 5},
    )
    assert assignment.status_code == 201, assignment.text

    resolved_assignment = await client.get(
        f"/api/v1/pricing/resolve?variant_id={variant['id']}&channel_id={channel['id']}", headers=headers
    )
    assert resolved_assignment.status_code == 200, resolved_assignment.text
    assert resolved_assignment.json()["source"] == "assignment"
    assert resolved_assignment.json()["unit_amount"] == "80.0000"

    override = await client.post(
        "/api/v1/pricing/variant-overrides",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "variant_id": variant["id"], "scope_type": "channel", "channel_id": channel["id"],
            "unit_amount": "49.99", "currency_code": "USD", "priority": 0,
        },
    )
    assert override.status_code == 201, override.text

    resolved_override = await client.get(
        f"/api/v1/pricing/resolve?variant_id={variant['id']}&channel_id={channel['id']}", headers=headers
    )
    assert resolved_override.status_code == 200, resolved_override.text
    assert resolved_override.json()["source"] == "override"
    assert resolved_override.json()["unit_amount"] == "49.9900"


async def test_resolve_returns_404_when_nothing_configured(client, registration):
    headers, _ = await catalog_context(client, registration)
    _, variant = await seed_variant(client, headers)
    response = await client.get(f"/api/v1/pricing/resolve?variant_id={variant['id']}", headers=headers)
    assert response.status_code == 404


async def test_assignment_requires_matching_scope_id(client, registration):
    headers, _ = await catalog_context(client, registration)
    price_list = await create_price_list(client, headers)
    response = await client.post(
        "/api/v1/pricing/assignments",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"price_list_id": price_list["id"], "scope_type": "store"},  # missing store_id
    )
    assert response.status_code == 422, response.text


async def test_archive_price_list_requires_correct_if_match(client, registration):
    headers, _ = await catalog_context(client, registration)
    price_list = await create_price_list(client, headers)
    stale = await client.post(
        f"/api/v1/pricing/price-lists/{price_list['id']}/archive", headers={**headers, "If-Match": "99"}
    )
    assert stale.status_code == 409, stale.text
    fresh = await client.post(
        f"/api/v1/pricing/price-lists/{price_list['id']}/archive",
        headers={**headers, "If-Match": str(price_list["version"])},
    )
    assert fresh.status_code == 200, fresh.text
    assert fresh.json()["status"] == "archived"


async def test_market_scoped_assignment_and_currency_flow(client, registration):
    headers, _ = await catalog_context(client, registration)
    store, variant = await seed_variant(client, headers)
    market = await create_market(client, headers, store["id"])
    price_list = await create_price_list(client, headers, code="ec-market")
    await client.put(
        f"/api/v1/pricing/price-lists/{price_list['id']}/entries/{variant['id']}",
        headers=headers,
        json={"unit_amount": "33.00"},
    )
    assignment = await client.post(
        "/api/v1/pricing/assignments",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"price_list_id": price_list["id"], "scope_type": "market", "market_id": market["id"], "priority": 1},
    )
    assert assignment.status_code == 201, assignment.text

    resolved = await client.get(f"/api/v1/pricing/resolve?variant_id={variant['id']}&market_id={market['id']}", headers=headers)
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["unit_amount"] == "33.0000"


async def test_list_price_lists_and_pagination_shape(client, registration):
    headers, _ = await catalog_context(client, registration)
    for index in range(3):
        await create_price_list(client, headers, code=f"list-{index}")
    listed = await client.get("/api/v1/pricing/price-lists?limit=2", headers=headers)
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert len(body["items"]) == 2
    assert body["has_more"] is True
    assert body["next_cursor"] is not None


async def test_update_price_list_name_and_reject_edits_once_archived(client, registration):
    headers, _ = await catalog_context(client, registration)
    price_list = await create_price_list(client, headers, code="editable")

    updated = await client.patch(
        f"/api/v1/pricing/price-lists/{price_list['id']}",
        headers={**headers, "If-Match": str(price_list["version"])},
        json={"name": "Renamed", "notes": "Updated via test"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Renamed"
    assert updated.json()["version"] == 2

    archived = await client.post(
        f"/api/v1/pricing/price-lists/{price_list['id']}/archive",
        headers={**headers, "If-Match": "2"},
    )
    assert archived.status_code == 200, archived.text

    rejected = await client.put(
        f"/api/v1/pricing/price-lists/{price_list['id']}/entries/{uuid4()}",
        headers=headers,
        json={"unit_amount": "5.00"},
    )
    assert rejected.status_code == 422, rejected.text  # ensure_reference_active: archived Price List


async def test_archive_assignment_and_override_lifecycle(client, registration):
    headers, _ = await catalog_context(client, registration)
    store, variant = await seed_variant(client, headers)
    channel = await create_channel(client, headers, store["id"])
    price_list = await create_price_list(client, headers, code="lifecycle")
    await client.put(
        f"/api/v1/pricing/price-lists/{price_list['id']}/entries/{variant['id']}",
        headers=headers,
        json={"unit_amount": "10.00"},
    )
    assignment = await client.post(
        "/api/v1/pricing/assignments",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"price_list_id": price_list["id"], "scope_type": "channel", "channel_id": channel["id"]},
    )
    assert assignment.status_code == 201, assignment.text

    stale_archive = await client.post(
        f"/api/v1/pricing/assignments/{assignment.json()['id']}/archive", headers={**headers, "If-Match": "99"}
    )
    assert stale_archive.status_code == 409, stale_archive.text
    archived_assignment = await client.post(
        f"/api/v1/pricing/assignments/{assignment.json()['id']}/archive",
        headers={**headers, "If-Match": str(assignment.json()["version"])},
    )
    assert archived_assignment.status_code == 200, archived_assignment.text
    assert archived_assignment.json()["status"] == "archived"

    override = await client.post(
        "/api/v1/pricing/variant-overrides",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "variant_id": variant["id"], "scope_type": "channel", "channel_id": channel["id"],
            "unit_amount": "1.00", "currency_code": "USD",
        },
    )
    assert override.status_code == 201, override.text
    archived_override = await client.post(
        f"/api/v1/pricing/variant-overrides/{override.json()['id']}/archive",
        headers={**headers, "If-Match": str(override.json()["version"])},
    )
    assert archived_override.status_code == 200, archived_override.text
    assert archived_override.json()["status"] == "archived"

    # With both the assignment and the override archived and no default Price
    # List, resolution has nothing left to fall back on.
    resolved = await client.get(
        f"/api/v1/pricing/resolve?variant_id={variant['id']}&channel_id={channel['id']}", headers=headers
    )
    assert resolved.status_code == 404


async def test_override_rejects_scope_id_that_does_not_match_scope_type(client, registration):
    headers, _ = await catalog_context(client, registration)
    _, variant = await seed_variant(client, headers)
    response = await client.post(
        "/api/v1/pricing/variant-overrides",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "variant_id": variant["id"], "scope_type": "store", "channel_id": str(uuid4()),  # channel_id set, but scope_type is store
            "unit_amount": "1.00", "currency_code": "USD",
        },
    )
    assert response.status_code == 422, response.text


async def test_assignment_rejects_inverted_effective_window(client, registration):
    headers, _ = await catalog_context(client, registration)
    store, _ = await seed_variant(client, headers)
    channel = await create_channel(client, headers, store["id"])
    price_list = await create_price_list(client, headers, code="window")
    response = await client.post(
        "/api/v1/pricing/assignments",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "price_list_id": price_list["id"], "scope_type": "channel", "channel_id": channel["id"],
            "effective_from": "2026-06-01T00:00:00Z", "effective_until": "2026-05-01T00:00:00Z",
        },
    )
    assert response.status_code == 422, response.text

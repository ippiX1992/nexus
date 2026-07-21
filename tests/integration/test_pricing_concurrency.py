import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.integration.test_catalog_api import catalog_context, create_product, create_store, create_type
from tests.integration.test_pricing_api import create_price_list

pytestmark = pytest.mark.integration


async def isolated_client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def test_concurrent_price_list_archives_have_exactly_one_winner(client, registration):
    headers, _ = await catalog_context(client, registration)
    price_list = await create_price_list(client, headers)

    async def attempt():
        async with await isolated_client() as caller:
            return await caller.post(
                f"/api/v1/pricing/price-lists/{price_list['id']}/archive",
                headers={**headers, "If-Match": str(price_list["version"])},
            )

    first, second = await asyncio.gather(attempt(), attempt())
    codes = sorted([first.status_code, second.status_code])
    assert codes == [200, 409]


async def test_concurrent_price_list_entry_updates_serialize_to_one_final_value(client, registration):
    """PUT entry/{variant_id} upserts under a row-level SELECT ... FOR UPDATE
    (see SqlAlchemyPricingRepository.upsert_price_list_entry), not an
    If-Match gate: once the entry already exists, two concurrent writers both
    succeed (200), but Postgres serializes them via the row lock, so the
    final row reflects exactly one of the two submitted values and exactly
    three versions (initial create + two serialized updates), never a torn
    write and never two entries for the same (price_list, variant)."""
    headers, _tenant = await catalog_context(client, registration)
    await create_store(client, headers)
    product_type = await create_type(client, headers)
    product_response, _ = await create_product(client, headers, product_type["id"], sku="CONC-001", code="conc-product")
    variant_id = product_response.json()["variants"][0]["id"]
    price_list = await create_price_list(client, headers)

    seeded = await client.put(
        f"/api/v1/pricing/price-lists/{price_list['id']}/entries/{variant_id}",
        headers=headers,
        json={"unit_amount": "1.00"},
    )
    assert seeded.status_code == 200, seeded.text
    assert seeded.json()["version"] == 1

    async def attempt(amount: str):
        async with await isolated_client() as caller:
            return await caller.put(
                f"/api/v1/pricing/price-lists/{price_list['id']}/entries/{variant_id}",
                headers=headers,
                json={"unit_amount": amount},
            )

    first, second = await asyncio.gather(attempt("11.00"), attempt("22.00"))
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text

    final = await client.get(f"/api/v1/pricing/price-lists/{price_list['id']}/entries", headers=headers)
    assert final.status_code == 200, final.text
    entries = final.json()["items"]
    assert len(entries) == 1
    assert entries[0]["unit_amount"] in ("11.0000", "22.0000")  # Numeric(19,4) always serializes at full scale
    assert entries[0]["version"] == 3  # seed (v1) + two row-lock-serialized updates (v2, v3)

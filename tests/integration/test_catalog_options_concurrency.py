import asyncio
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.integration.test_catalog_api import catalog_context, create_store, create_type
from tests.integration.test_catalog_options_api import create_option, create_option_value

pytestmark = pytest.mark.integration


async def isolated_client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def test_two_options_with_the_same_code_have_exactly_one_winner(client, registration):
    headers, _ = await catalog_context(client, registration)

    async def attempt():
        async with await isolated_client() as caller:
            return await caller.post(
                "/api/v1/catalog/options",
                headers={**headers, "Idempotency-Key": str(uuid4())},
                json={"code": "color", "name": "Color"},
            )

    first, second = await asyncio.gather(attempt(), attempt())
    codes = sorted([first.status_code, second.status_code])
    assert codes == [201, 409]


async def test_concurrent_identical_combinations_have_exactly_one_winner(client, registration):
    headers, _ = await catalog_context(client, registration)
    await create_store(client, headers)
    product_type = await create_type(client, headers)
    product_response = await client.post(
        "/api/v1/catalog/products",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "product_type_id": product_type["id"],
            "code": "product-race",
            "sku": "SKU-RACE",
            "translation": {"locale": "es-EC", "name": "Product Race", "slug": "product-race"},
        },
    )
    assert product_response.status_code == 201, product_response.text
    detail = product_response.json()
    option = await create_option(client, headers, code="color")
    value = await create_option_value(client, headers, option["id"], code="red")
    assign = await client.put(
        f"/api/v1/catalog/products/{detail['product']['id']}/options",
        headers={**headers, "If-Match": str(detail["product"]["version"])},
        json={"options": [{"option_id": option["id"], "position": 0}]},
    )
    assert assign.status_code == 200, assign.text

    async def attempt(sku):
        async with await isolated_client() as caller:
            return await caller.post(
                f"/api/v1/catalog/products/{detail['product']['id']}/variants",
                headers={**headers, "Idempotency-Key": str(uuid4())},
                json={"sku": sku, "option_value_ids": [value["id"]]},
            )

    first, second = await asyncio.gather(attempt("RACE-1"), attempt("RACE-2"))
    codes = sorted([first.status_code, second.status_code])
    # The database's partial unique index on (tenant_id, product_id,
    # combination_fingerprint), not application-level locking, is what
    # guarantees exactly one winner here -- see
    # docs/architecture/catalog-option-combinations.md section 5.
    assert codes == [201, 409]

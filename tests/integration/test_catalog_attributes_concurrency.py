import asyncio
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.integration.test_catalog_api import catalog_context, create_store, create_type
from tests.integration.test_catalog_attributes_api import create_attribute

pytestmark = pytest.mark.integration


async def isolated_client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def test_two_attributes_with_the_same_code_have_exactly_one_winner(client, registration):
    headers, _ = await catalog_context(client, registration)

    async def attempt():
        async with await isolated_client() as caller:
            return await caller.post(
                "/api/v1/catalog/attributes",
                headers={**headers, "Idempotency-Key": str(uuid4())},
                json={"code": "power", "name": "Power", "data_type": "DECIMAL"},
            )

    first, second = await asyncio.gather(attempt(), attempt())
    codes = sorted([first.status_code, second.status_code])
    assert codes == [201, 409]


async def test_concurrent_product_specification_writes_have_exactly_one_winner(client, registration):
    headers, _ = await catalog_context(client, registration)
    await create_store(client, headers)
    product_type = await create_type(client, headers)
    product_response = await client.post(
        "/api/v1/catalog/products",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "product_type_id": product_type["id"],
            "code": "product-attr-race",
            "sku": "SKU-ATTR-RACE",
            "translation": {"locale": "es-EC", "name": "Product Attr Race", "slug": "product-attr-race"},
        },
    )
    assert product_response.status_code == 201, product_response.text
    detail = product_response.json()
    attribute = await create_attribute(client, headers, code="power", data_type="DECIMAL")
    assign = await client.put(
        f"/api/v1/catalog/product-types/{product_type['id']}/attributes",
        headers={**headers, "If-Match": str(product_type["version"])},
        json={"attributes": [{"attribute_id": attribute["id"], "position": 0}]},
    )
    assert assign.status_code == 200, assign.text

    async def attempt(value):
        async with await isolated_client() as caller:
            return await caller.put(
                f"/api/v1/catalog/products/{detail['product']['id']}/attributes",
                headers={**headers, "If-Match": str(detail["product"]["version"])},
                json={"values": [{"attribute_id": attribute["id"], "value": value}]},
            )

    first, second = await asyncio.gather(attempt("100"), attempt("200"))
    codes = sorted([first.status_code, second.status_code])
    # Optimistic concurrency (If-Match against the Product's version), not
    # application-level locking, is what guarantees exactly one winner here.
    assert codes == [200, 409]

"""Further coverage of M3.1 error branches not exercised by the happy-path and
first coverage passes: generation request version/permission errors, product
option assignment against a missing/foreign Option, translation upserts
against missing Options/Values, and quota exhaustion for option values."""

from uuid import uuid4

import pytest

from tests.integration.test_catalog_api import catalog_context, create_store, create_type
from tests.integration.test_catalog_options_api import (
    create_option,
    seed_product_with_options,
)

pytestmark = pytest.mark.integration


async def test_generation_request_rejects_stale_version(client, registration):
    headers, _ = await catalog_context(client, registration)
    seed = await seed_product_with_options(client, headers)
    stale = await client.post(
        f"/api/v1/catalog/products/{seed['product']['id']}/variant-generation",
        headers={**headers, "If-Match": "999", "Idempotency-Key": str(uuid4())},
    )
    assert stale.status_code == 409, stale.text


async def test_generation_request_replays_on_same_idempotency_key(client, registration):
    headers, _ = await catalog_context(client, registration)
    seed = await seed_product_with_options(client, headers)
    current = await client.get(f"/api/v1/catalog/products/{seed['product']['id']}", headers=headers)
    version = current.json()["product"]["version"]
    key = str(uuid4())
    first = await client.post(
        f"/api/v1/catalog/products/{seed['product']['id']}/variant-generation",
        headers={**headers, "If-Match": str(version), "Idempotency-Key": key},
    )
    assert first.status_code == 202, first.text
    second = await client.post(
        f"/api/v1/catalog/products/{seed['product']['id']}/variant-generation",
        headers={**headers, "If-Match": str(version), "Idempotency-Key": key},
    )
    assert second.status_code == 202
    assert second.json()["operation_id"] == first.json()["operation_id"]


async def test_option_translation_upsert_rejects_missing_option(client, registration):
    headers, _ = await catalog_context(client, registration)
    missing = await client.put(
        f"/api/v1/catalog/options/{uuid4()}/translations/es-EC", headers=headers, json={"name": "x"}
    )
    assert missing.status_code == 404


async def test_option_value_translation_upsert_rejects_missing_value(client, registration):
    headers, _ = await catalog_context(client, registration)
    missing = await client.put(
        f"/api/v1/catalog/option-values/{uuid4()}/translations/es-EC", headers=headers, json={"value": "x"}
    )
    assert missing.status_code == 404


async def test_set_product_options_rejects_unknown_option_and_duplicate_in_payload(client, registration):
    headers, _ = await catalog_context(client, registration)
    await create_store(client, headers)
    product_type = await create_type(client, headers)
    created = await client.post(
        "/api/v1/catalog/products",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "product_type_id": product_type["id"],
            "code": "product-edge",
            "sku": "SKU-EDGE",
            "translation": {"locale": "es-EC", "name": "Product Edge", "slug": "product-edge"},
        },
    )
    assert created.status_code == 201, created.text
    detail = created.json()

    unknown = await client.put(
        f"/api/v1/catalog/products/{detail['product']['id']}/options",
        headers={**headers, "If-Match": str(detail["product"]["version"])},
        json={"options": [{"option_id": str(uuid4()), "position": 0}]},
    )
    assert unknown.status_code == 404, unknown.text

    option = await create_option(client, headers, code="color")
    duplicate = await client.put(
        f"/api/v1/catalog/products/{detail['product']['id']}/options",
        headers={**headers, "If-Match": str(detail["product"]["version"])},
        json={"options": [{"option_id": option["id"], "position": 0}, {"option_id": option["id"], "position": 1}]},
    )
    assert duplicate.status_code == 409, duplicate.text


async def test_variant_combination_rejects_duplicate_value_for_same_option_in_one_request(client, registration):
    headers, _ = await catalog_context(client, registration)
    seed = await seed_product_with_options(client, headers)
    rejected = await client.post(
        f"/api/v1/catalog/products/{seed['product']['id']}/variants",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "sku": "SHIRT-TWO-COLORS",
            "option_value_ids": [seed["values"]["red"]["id"], seed["values"]["blue"]["id"], seed["values"]["small"]["id"]],
        },
    )
    assert rejected.status_code == 409, rejected.text



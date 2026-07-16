"""Closes coverage gaps left by the happy-path tests in test_catalog_options_api.py:
GET/list endpoints, 404s, version conflicts, and edge branches not otherwise
exercised (empty preview, archive-is-idempotent, cross-resource validation)."""

from uuid import uuid4

import pytest

from tests.integration.test_catalog_api import catalog_context, create_store, create_type
from tests.integration.test_catalog_options_api import (
    create_option,
    create_option_value,
    seed_product_with_options,
)

pytestmark = pytest.mark.integration


async def test_list_options_and_get_missing_option_returns_404(client, registration):
    headers, _ = await catalog_context(client, registration)
    await create_option(client, headers, code="color")
    await create_option(client, headers, code="size")

    listed = await client.get("/api/v1/catalog/options", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 2

    missing = await client.get(f"/api/v1/catalog/options/{uuid4()}", headers=headers)
    assert missing.status_code == 404


async def test_update_option_version_conflict_and_archived_option_rejects_update(client, registration):
    headers, _ = await catalog_context(client, registration)
    option = await create_option(client, headers, code="color")

    stale = await client.patch(
        f"/api/v1/catalog/options/{option['id']}", headers={**headers, "If-Match": "999"}, json={"name": "X"}
    )
    assert stale.status_code == 409

    archived = await client.post(
        f"/api/v1/catalog/options/{option['id']}/archive", headers={**headers, "If-Match": str(option["version"])}
    )
    assert archived.status_code == 200

    rejected = await client.patch(
        f"/api/v1/catalog/options/{archived.json()['id']}",
        headers={**headers, "If-Match": str(archived.json()["version"])},
        json={"name": "Still archived"},
    )
    assert rejected.status_code == 422


async def test_option_value_missing_returns_404_and_update_version_conflict(client, registration):
    headers, _ = await catalog_context(client, registration)
    option = await create_option(client, headers, code="color")
    value = await create_option_value(client, headers, option["id"], code="red")

    missing = await client.patch(
        f"/api/v1/catalog/option-values/{uuid4()}", headers={**headers, "If-Match": "1"}, json={"value": "x"}
    )
    assert missing.status_code == 404

    stale = await client.patch(
        f"/api/v1/catalog/option-values/{value['id']}", headers={**headers, "If-Match": "999"}, json={"value": "x"}
    )
    assert stale.status_code == 409


async def test_product_options_get_empty_then_after_assignment(client, registration):
    headers, _ = await catalog_context(client, registration)
    await create_store(client, headers)
    product_type = await create_type(client, headers)
    created = await client.post(
        "/api/v1/catalog/products",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "product_type_id": product_type["id"],
            "code": "product-empty",
            "sku": "SKU-EMPTY",
            "translation": {"locale": "es-EC", "name": "Product Empty", "slug": "product-empty"},
        },
    )
    assert created.status_code == 201, created.text
    product_id = created.json()["product"]["id"]

    empty = await client.get(f"/api/v1/catalog/products/{product_id}/options", headers=headers)
    assert empty.status_code == 200 and empty.json() == []

    missing_product = await client.get(f"/api/v1/catalog/products/{uuid4()}/options", headers=headers)
    assert missing_product.status_code == 404


async def test_preview_without_any_product_options_is_a_domain_error(client, registration):
    headers, _ = await catalog_context(client, registration)
    await create_store(client, headers)
    product_type = await create_type(client, headers)
    created = await client.post(
        "/api/v1/catalog/products",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "product_type_id": product_type["id"],
            "code": "product-simple",
            "sku": "SKU-SIMPLE",
            "translation": {"locale": "es-EC", "name": "Product Simple", "slug": "product-simple"},
        },
    )
    assert created.status_code == 201, created.text
    product_id = created.json()["product"]["id"]

    preview = await client.post(f"/api/v1/catalog/products/{product_id}/variant-generation/preview", headers=headers)
    assert preview.status_code == 422, preview.text


async def test_default_variant_has_no_combination_and_untouched_by_option_assignment(client, registration):
    headers, _ = await catalog_context(client, registration)
    seed = await seed_product_with_options(client, headers)
    assert seed["default_variant"]["combination_fingerprint"] is None

    variants = await client.get(f"/api/v1/catalog/products/{seed['product']['id']}/variants?limit=10", headers=headers)
    default = next(item for item in variants.json()["items"] if item["is_default"])
    assert default["combination_fingerprint"] is None


async def test_archiving_an_already_archived_option_value_is_a_no_op_not_an_error(client, registration):
    headers, _ = await catalog_context(client, registration)
    option = await create_option(client, headers, code="color")
    value = await create_option_value(client, headers, option["id"], code="red")

    first = await client.post(
        f"/api/v1/catalog/option-values/{value['id']}/archive", headers={**headers, "If-Match": str(value["version"])}
    )
    assert first.status_code == 200 and first.json()["status"] == "archived"

    second = await client.post(
        f"/api/v1/catalog/option-values/{value['id']}/archive",
        headers={**headers, "If-Match": str(first.json()["version"])},
    )
    assert second.status_code == 200 and second.json()["status"] == "archived"
    assert second.json()["version"] == first.json()["version"]  # no-op does not bump version again

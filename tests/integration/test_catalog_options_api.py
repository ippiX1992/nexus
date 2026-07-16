from uuid import UUID, uuid4

import pytest

from app.infrastructure.database import SessionFactory
from app.infrastructure.tenant_context import set_tenant_context
from app.modules.catalog.application.generation import run_variant_generation_job
from app.modules.platform.application.jobs import claim_jobs
from app.modules.platform.infrastructure.runtime_models import JobModel
from tests.integration.test_catalog_api import (
    catalog_context,
    create_brand,
    create_product,
    create_store,
    create_type,
)

pytestmark = pytest.mark.integration


async def create_option(client, headers, *, code="color", input_type="select"):
    response = await client.post(
        "/api/v1/catalog/options",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"code": code, "name": code.title(), "input_type": input_type},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_option_value(client, headers, option_id, *, code="red", value=None):
    response = await client.post(
        f"/api/v1/catalog/options/{option_id}/values",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"code": code, "value": value or code.title()},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def seed_product_with_options(client, headers):
    await create_store(client, headers)
    product_type = await create_type(client, headers, code="apparel")
    brand = await create_brand(client, headers, code="nexus")
    product_response, _ = await create_product(
        client, headers, product_type["id"], sku="SHIRT-BASE", brand_id=brand["id"], code="shirt"
    )
    assert product_response.status_code == 201, product_response.text
    detail = product_response.json()
    color = await create_option(client, headers, code="color")
    red = await create_option_value(client, headers, color["id"], code="red")
    blue = await create_option_value(client, headers, color["id"], code="blue")
    size = await create_option(client, headers, code="size")
    small = await create_option_value(client, headers, size["id"], code="s", value="S")
    large = await create_option_value(client, headers, size["id"], code="l", value="L")
    assign = await client.put(
        f"/api/v1/catalog/products/{detail['product']['id']}/options",
        headers={**headers, "If-Match": str(detail["product"]["version"])},
        json={"options": [{"option_id": color["id"], "position": 0}, {"option_id": size["id"], "position": 1}]},
    )
    assert assign.status_code == 200, assign.text
    return {
        "product": detail["product"],
        "default_variant": detail["variants"][0],
        "color": color,
        "size": size,
        "values": {"red": red, "blue": blue, "small": small, "large": large},
    }


async def test_option_and_value_crud_translation_and_archive(client, registration):
    headers, _ = await catalog_context(client, registration)
    option = await create_option(client, headers, code="color")
    assert option["status"] == "active" and option["input_type"] == "select"

    updated = await client.patch(
        f"/api/v1/catalog/options/{option['id']}",
        headers={**headers, "If-Match": str(option["version"])},
        json={"name": "Colour"},
    )
    assert updated.status_code == 200 and updated.json()["name"] == "Colour"

    translated = await client.put(
        f"/api/v1/catalog/options/{option['id']}/translations/es-EC",
        headers=headers,
        json={"name": "Color"},
    )
    assert translated.status_code == 200 and translated.json()["locale"] == "es-EC"

    value = await create_option_value(client, headers, option["id"], code="red")
    assert value["status"] == "active"

    value_updated = await client.patch(
        f"/api/v1/catalog/option-values/{value['id']}",
        headers={**headers, "If-Match": str(value["version"])},
        json={"swatch_hex": "#ff0000"},
    )
    assert value_updated.status_code == 200 and value_updated.json()["swatch_hex"] == "#FF0000"

    archived_value = await client.post(
        f"/api/v1/catalog/option-values/{value['id']}/archive",
        headers={**headers, "If-Match": str(value_updated.json()["version"])},
    )
    assert archived_value.status_code == 200 and archived_value.json()["status"] == "archived"

    # The translation upsert above also bumped the Option's version (it changes
    # aggregate content) -- fetch the current one instead of reusing a stale value.
    current_option = await client.get(f"/api/v1/catalog/options/{option['id']}", headers=headers)
    archived_option = await client.post(
        f"/api/v1/catalog/options/{option['id']}/archive",
        headers={**headers, "If-Match": str(current_option.json()["version"])},
    )
    assert archived_option.status_code == 200 and archived_option.json()["status"] == "archived"


async def test_option_code_unique_per_tenant_and_value_code_unique_per_option(client, registration):
    headers, _ = await catalog_context(client, registration)
    await create_option(client, headers, code="color")
    duplicate = await client.post(
        "/api/v1/catalog/options", headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"code": "color", "name": "Color again"},
    )
    assert duplicate.status_code == 409

    option = await create_option(client, headers, code="size")
    await create_option_value(client, headers, option["id"], code="s")
    duplicate_value = await client.post(
        f"/api/v1/catalog/options/{option['id']}/values", headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"code": "s", "value": "Small again"},
    )
    assert duplicate_value.status_code == 409


async def test_product_options_max_per_product_quota_is_409(client, registration):
    headers, _ = await catalog_context(client, registration)
    await create_store(client, headers)
    product_type = await create_type(client, headers, code="gadget")
    product_response, _ = await create_product(client, headers, product_type["id"], sku="GADGET-1", code="gadget-1")
    assert product_response.status_code == 201, product_response.text
    detail = product_response.json()
    options = [await create_option(client, headers, code=f"opt-{i}") for i in range(7)]
    payload = {"options": [{"option_id": o["id"], "position": i} for i, o in enumerate(options)]}
    response = await client.put(
        f"/api/v1/catalog/products/{detail['product']['id']}/options",
        headers={**headers, "If-Match": str(detail["product"]["version"])},
        json=payload,
    )
    assert response.status_code == 409, response.text


async def test_manual_combination_creation_sets_fingerprint_and_rejects_incomplete_or_duplicate(client, registration):
    headers, _ = await catalog_context(client, registration)
    seed = await seed_product_with_options(client, headers)
    product_id = seed["product"]["id"]

    incomplete = await client.post(
        f"/api/v1/catalog/products/{product_id}/variants",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"sku": "SHIRT-RED", "option_value_ids": [seed["values"]["red"]["id"]]},
    )
    assert incomplete.status_code == 422, incomplete.text

    complete = await client.post(
        f"/api/v1/catalog/products/{product_id}/variants",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"sku": "SHIRT-RED-S", "option_value_ids": [seed["values"]["red"]["id"], seed["values"]["small"]["id"]]},
    )
    assert complete.status_code == 201, complete.text
    variant = complete.json()
    assert variant["combination_fingerprint"] is not None

    duplicate = await client.post(
        f"/api/v1/catalog/products/{product_id}/variants",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"sku": "SHIRT-RED-S-2", "option_value_ids": [seed["values"]["red"]["id"], seed["values"]["small"]["id"]]},
    )
    assert duplicate.status_code == 409, duplicate.text


async def test_retiring_a_product_option_in_use_is_blocked(client, registration):
    headers, _ = await catalog_context(client, registration)
    seed = await seed_product_with_options(client, headers)
    product_id = seed["product"]["id"]
    variant_created = await client.post(
        f"/api/v1/catalog/products/{product_id}/variants",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"sku": "SHIRT-BLUE-L", "option_value_ids": [seed["values"]["blue"]["id"], seed["values"]["large"]["id"]]},
    )
    assert variant_created.status_code == 201, variant_created.text
    current = await client.get(f"/api/v1/catalog/products/{product_id}", headers=headers)
    version = current.json()["product"]["version"]
    retire = await client.put(
        f"/api/v1/catalog/products/{product_id}/options",
        headers={**headers, "If-Match": str(version)},
        json={"options": [{"option_id": seed["size"]["id"], "position": 0}]},
    )
    assert retire.status_code == 422, retire.text


async def test_variant_generation_preview_is_read_only_and_matches_the_ten_fields(client, registration):
    headers, _ = await catalog_context(client, registration)
    seed = await seed_product_with_options(client, headers)
    preview = await client.post(
        f"/api/v1/catalog/products/{seed['product']['id']}/variant-generation/preview", headers=headers
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    for field in (
        "options_considered", "theoretical_total", "existing_combinations", "new_combinations",
        "duplicate_combinations", "tenant_limit", "remaining_capacity", "warnings", "estimated_work",
    ):
        assert field in body
    assert body["theoretical_total"] == 4  # 2 colors x 2 sizes
    assert body["new_combinations"] == 4
    assert body["duplicate_combinations"] == 0


async def test_variant_generation_is_durable_not_synchronous_and_worker_creates_combinations(client, registration):
    headers, _ = await catalog_context(client, registration)
    seed = await seed_product_with_options(client, headers)
    current = await client.get(f"/api/v1/catalog/products/{seed['product']['id']}", headers=headers)
    version = current.json()["product"]["version"]

    requested = await client.post(
        f"/api/v1/catalog/products/{seed['product']['id']}/variant-generation",
        headers={**headers, "If-Match": str(version), "Idempotency-Key": str(uuid4())},
    )
    assert requested.status_code == 202, requested.text
    operation_id = requested.json()["operation_id"]

    operation = await client.get(f"/api/v1/operations/{operation_id}", headers=headers)
    assert operation.status_code == 200
    assert operation.json()["status"] == "queued"  # the request never ran the cartesian product inline

    tenant_id = UUID(current.json()["product"]["tenant_id"])
    async with SessionFactory() as db:
        await set_tenant_context(db, tenant_id)
        jobs = await claim_jobs(db, tenant_id, "test-worker")
        assert len(jobs) == 1
        job: JobModel = jobs[0]
        assert job.job_type == "catalog.variant_generation"
        result = await run_variant_generation_job(db, job)
        assert result["created"] == 4  # 2 colors x 2 sizes, default variant already excluded (no Options on it)

    variants = await client.get(f"/api/v1/catalog/products/{seed['product']['id']}/variants?limit=50", headers=headers)
    fingerprints = {item["combination_fingerprint"] for item in variants.json()["items"] if item["combination_fingerprint"]}
    assert len(fingerprints) == 4

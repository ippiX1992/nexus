"""M3.2 Catalog Attributes and Product Specifications: happy-path CRUD,
translations, SELECT/MULTI_SELECT, Product Type assignment, Product values
for every data type, archive/restore, idempotency and outbox evidence -- all
against a real PostgreSQL, no mocks."""

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.infrastructure.database import SessionFactory
from app.infrastructure.tenant_context import set_tenant_context
from app.modules.platform.infrastructure.models import OutboxEventModel
from tests.integration.test_catalog_api import (
    catalog_context,
    create_brand,
    create_product,
    create_store,
    create_type,
)

pytestmark = pytest.mark.integration


async def create_attribute(client, headers, *, code="power", data_type="DECIMAL", **extra):
    response = await client.post(
        "/api/v1/catalog/attributes",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"code": code, "name": code.title(), "data_type": data_type, **extra},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_attribute_option(client, headers, attribute_id, *, code="red", label=None):
    response = await client.post(
        f"/api/v1/catalog/attributes/{attribute_id}/options",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"code": code, "label": label or code.title()},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_attribute_group(client, headers, *, code="general"):
    response = await client.post(
        "/api/v1/catalog/attribute-groups",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"code": code, "name": code.title()},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def seed_product_with_attributes(client, headers):
    await create_store(client, headers)
    product_type = await create_type(client, headers, code="appliances")
    brand = await create_brand(client, headers, code="nexus")
    product_response, _ = await create_product(
        client, headers, product_type["id"], sku="OVEN-BASE", brand_id=brand["id"], code="oven"
    )
    assert product_response.status_code == 201, product_response.text
    detail = product_response.json()

    power = await create_attribute(client, headers, code="power", data_type="DECIMAL", unit="W")
    material = await create_attribute(client, headers, code="material", data_type="SELECT")
    aluminium = await create_attribute_option(client, headers, material["id"], code="aluminium")
    steel = await create_attribute_option(client, headers, material["id"], code="steel")
    finishes = await create_attribute(client, headers, code="finishes", data_type="MULTI_SELECT")
    matte = await create_attribute_option(client, headers, finishes["id"], code="matte")
    glossy = await create_attribute_option(client, headers, finishes["id"], code="glossy")
    installed = await create_attribute(client, headers, code="preinstalled", data_type="BOOLEAN")

    assign = await client.put(
        f"/api/v1/catalog/product-types/{product_type['id']}/attributes",
        headers={**headers, "If-Match": str(product_type["version"])},
        json={
            "attributes": [
                {"attribute_id": power["id"], "position": 0, "required": True},
                {"attribute_id": material["id"], "position": 1, "required": True},
                {"attribute_id": finishes["id"], "position": 2, "required": False},
                {"attribute_id": installed["id"], "position": 3, "required": False},
            ]
        },
    )
    assert assign.status_code == 200, assign.text

    return {
        "product": detail["product"],
        "product_type": product_type,
        "power": power,
        "material": material,
        "aluminium": aluminium,
        "steel": steel,
        "finishes": finishes,
        "matte": matte,
        "glossy": glossy,
        "installed": installed,
    }


async def test_attribute_crud_translation_and_archive_restore(client, registration):
    headers, _ = await catalog_context(client, registration)
    attribute = await create_attribute(client, headers, code="power", data_type="DECIMAL", unit="W")
    assert attribute["data_type"] == "DECIMAL"
    assert attribute["unit"] == "W"

    updated = await client.patch(
        f"/api/v1/catalog/attributes/{attribute['id']}",
        headers={**headers, "If-Match": str(attribute["version"])},
        json={"name": "Power (Watts)", "is_filterable": True},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Power (Watts)"
    assert updated.json()["is_filterable"] is True

    translated = await client.put(
        f"/api/v1/catalog/attributes/{attribute['id']}/translations/en-US",
        headers=headers,
        json={"name": "Power", "description": "Rated power in watts"},
    )
    assert translated.status_code == 200, translated.text
    assert translated.json()["locale"] == "en-US"

    current = await client.get(f"/api/v1/catalog/attributes/{attribute['id']}", headers=headers)
    version = current.json()["version"]

    archived = await client.post(
        f"/api/v1/catalog/attributes/{attribute['id']}/archive", headers={**headers, "If-Match": str(version)}
    )
    assert archived.status_code == 200 and archived.json()["status"] == "archived"

    restored = await client.post(
        f"/api/v1/catalog/attributes/{attribute['id']}/restore",
        headers={**headers, "If-Match": str(archived.json()["version"])},
    )
    assert restored.status_code == 200 and restored.json()["status"] == "active"


async def test_attribute_data_type_is_immutable_after_creation(client, registration):
    headers, _ = await catalog_context(client, registration)
    attribute = await create_attribute(client, headers, code="power", data_type="DECIMAL")
    rejected = await client.patch(
        f"/api/v1/catalog/attributes/{attribute['id']}",
        headers={**headers, "If-Match": str(attribute["version"])},
        json={"data_type": "INTEGER"},
    )
    assert rejected.status_code == 422, rejected.text


async def test_attribute_options_only_allowed_for_select_types(client, registration):
    headers, _ = await catalog_context(client, registration)
    text_attribute = await create_attribute(client, headers, code="material-notes", data_type="TEXT")
    rejected = await client.post(
        f"/api/v1/catalog/attributes/{text_attribute['id']}/options",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"code": "red", "label": "Red"},
    )
    assert rejected.status_code == 422, rejected.text


async def test_attribute_option_crud_and_translation(client, registration):
    headers, _ = await catalog_context(client, registration)
    material = await create_attribute(client, headers, code="material", data_type="SELECT")
    option = await create_attribute_option(client, headers, material["id"], code="aluminium")

    updated = await client.patch(
        f"/api/v1/catalog/attribute-options/{option['id']}",
        headers={**headers, "If-Match": str(option["version"])},
        json={"label": "Aluminium (Anodized)"},
    )
    assert updated.status_code == 200, updated.text

    translated = await client.put(
        f"/api/v1/catalog/attribute-options/{option['id']}/translations/en-US",
        headers=headers,
        json={"label": "Aluminium"},
    )
    assert translated.status_code == 200, translated.text

    listed = await client.get(f"/api/v1/catalog/attributes/{material['id']}/options", headers=headers)
    current_option = next(item for item in listed.json() if item["id"] == option["id"])

    archived = await client.post(
        f"/api/v1/catalog/attribute-options/{option['id']}/archive",
        headers={**headers, "If-Match": str(current_option["version"])},
    )
    assert archived.status_code == 200, archived.text


async def test_attribute_group_crud_archive_restore(client, registration):
    headers, _ = await catalog_context(client, registration)
    group = await create_attribute_group(client, headers, code="general")
    updated = await client.patch(
        f"/api/v1/catalog/attribute-groups/{group['id']}",
        headers={**headers, "If-Match": str(group["version"])},
        json={"name": "General Information"},
    )
    assert updated.status_code == 200, updated.text
    archived = await client.post(
        f"/api/v1/catalog/attribute-groups/{group['id']}/archive",
        headers={**headers, "If-Match": str(updated.json()["version"])},
    )
    assert archived.status_code == 200 and archived.json()["status"] == "archived"
    restored = await client.post(
        f"/api/v1/catalog/attribute-groups/{group['id']}/restore",
        headers={**headers, "If-Match": str(archived.json()["version"])},
    )
    assert restored.status_code == 200 and restored.json()["status"] == "active"


async def test_product_type_attribute_assignment_is_replace_not_append(client, registration):
    headers, _ = await catalog_context(client, registration)
    product_type = await create_type(client, headers, code="appliances")
    power = await create_attribute(client, headers, code="power", data_type="DECIMAL")
    material = await create_attribute(client, headers, code="material", data_type="TEXT")

    first = await client.put(
        f"/api/v1/catalog/product-types/{product_type['id']}/attributes",
        headers={**headers, "If-Match": str(product_type["version"])},
        json={"attributes": [{"attribute_id": power["id"], "position": 0, "required": True}]},
    )
    assert first.status_code == 200
    assert [item["attribute_id"] for item in first.json()] == [power["id"]]

    reloaded_type = await client.get(f"/api/v1/catalog/product-types/{product_type['id']}", headers=headers)
    second = await client.put(
        f"/api/v1/catalog/product-types/{product_type['id']}/attributes",
        headers={**headers, "If-Match": str(reloaded_type.json()["version"])},
        json={"attributes": [{"attribute_id": material["id"], "position": 0}]},
    )
    assert second.status_code == 200, second.text
    assert [item["attribute_id"] for item in second.json()] == [material["id"]]

    listed = await client.get(f"/api/v1/catalog/product-types/{product_type['id']}/attributes", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1


async def test_product_specification_values_for_every_data_type_and_persist_on_reload(client, registration):
    headers, _ = await catalog_context(client, registration)
    seed = await seed_product_with_attributes(client, headers)
    product_id = seed["product"]["id"]

    save = await client.put(
        f"/api/v1/catalog/products/{product_id}/attributes",
        headers={**headers, "If-Match": str(seed["product"]["version"])},
        json={
            "values": [
                {"attribute_id": seed["power"]["id"], "value": "500.5"},
                {"attribute_id": seed["material"]["id"], "value": seed["aluminium"]["id"]},
                {"attribute_id": seed["finishes"]["id"], "value": [seed["matte"]["id"], seed["glossy"]["id"]]},
                {"attribute_id": seed["installed"]["id"], "value": True},
            ]
        },
    )
    assert save.status_code == 200, save.text
    values_by_attribute = {item["attribute_id"]: item for item in save.json()}
    assert Decimal(values_by_attribute[seed["power"]["id"]]["value_decimal"]) == Decimal("500.5")
    assert values_by_attribute[seed["material"]["id"]]["value_option_id"] == seed["aluminium"]["id"]
    assert values_by_attribute[seed["installed"]["id"]]["value_boolean"] is True

    reloaded = await client.get(f"/api/v1/catalog/products/{product_id}/attributes", headers=headers)
    assert reloaded.status_code == 200
    assert len(reloaded.json()) == 4


async def test_product_specification_rejects_wrong_type_and_foreign_option(client, registration):
    headers, _ = await catalog_context(client, registration)
    seed = await seed_product_with_attributes(client, headers)
    product_id = seed["product"]["id"]

    wrong_type = await client.put(
        f"/api/v1/catalog/products/{product_id}/attributes",
        headers={**headers, "If-Match": str(seed["product"]["version"])},
        json={"values": [{"attribute_id": seed["power"]["id"], "value": "not-a-number"}]},
    )
    assert wrong_type.status_code == 422, wrong_type.text

    foreign_option = await client.put(
        f"/api/v1/catalog/products/{product_id}/attributes",
        headers={**headers, "If-Match": str(seed["product"]["version"])},
        json={"values": [{"attribute_id": seed["material"]["id"], "value": seed["matte"]["id"]}]},
    )
    assert foreign_option.status_code == 422, foreign_option.text


async def test_product_specification_enforces_required_attributes(client, registration):
    headers, _ = await catalog_context(client, registration)
    seed = await seed_product_with_attributes(client, headers)
    product_id = seed["product"]["id"]

    missing_required = await client.put(
        f"/api/v1/catalog/products/{product_id}/attributes",
        headers={**headers, "If-Match": str(seed["product"]["version"])},
        json={"values": [{"attribute_id": seed["power"]["id"], "value": "500"}]},
    )
    assert missing_required.status_code == 422, missing_required.text


async def test_archived_attribute_option_kept_on_existing_value_but_rejected_on_new_assignment(client, registration):
    headers, _ = await catalog_context(client, registration)
    seed = await seed_product_with_attributes(client, headers)
    product_id = seed["product"]["id"]

    save = await client.put(
        f"/api/v1/catalog/products/{product_id}/attributes",
        headers={**headers, "If-Match": str(seed["product"]["version"])},
        json={
            "values": [
                {"attribute_id": seed["power"]["id"], "value": "500"},
                {"attribute_id": seed["material"]["id"], "value": seed["aluminium"]["id"]},
            ]
        },
    )
    assert save.status_code == 200, save.text

    current = await client.get(f"/api/v1/catalog/products/{product_id}", headers=headers)
    current_version = current.json()["product"]["version"]

    archive_option = await client.post(
        f"/api/v1/catalog/attribute-options/{seed['aluminium']['id']}/archive",
        headers={**headers, "If-Match": str(seed["aluminium"]["version"])},
    )
    assert archive_option.status_code == 200, archive_option.text

    still_there = await client.get(f"/api/v1/catalog/products/{product_id}/attributes", headers=headers)
    material_value = next(item for item in still_there.json() if item["attribute_id"] == seed["material"]["id"])
    assert material_value["value_option_id"] == seed["aluminium"]["id"]

    resave_with_archived = await client.put(
        f"/api/v1/catalog/products/{product_id}/attributes",
        headers={**headers, "If-Match": str(current_version)},
        json={
            "values": [
                {"attribute_id": seed["power"]["id"], "value": "500"},
                {"attribute_id": seed["material"]["id"], "value": seed["aluminium"]["id"]},
            ]
        },
    )
    assert resave_with_archived.status_code == 422, resave_with_archived.text


async def test_attribute_creation_is_idempotent_and_emits_outbox_event(client, registration):
    headers, tenant = await catalog_context(client, registration)
    key = str(uuid4())
    payload = {"code": "power", "name": "Power", "data_type": "DECIMAL"}
    first = await client.post("/api/v1/catalog/attributes", headers={**headers, "Idempotency-Key": key}, json=payload)
    assert first.status_code == 201, first.text
    second = await client.post("/api/v1/catalog/attributes", headers={**headers, "Idempotency-Key": key}, json=payload)
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]

    async with SessionFactory() as db:
        await set_tenant_context(db, tenant["id"])
        events = (
            await db.execute(
                select(OutboxEventModel).where(
                    OutboxEventModel.tenant_id == tenant["id"],
                    OutboxEventModel.event_type == "catalog.attribute.created.v1",
                )
            )
        ).scalars().all()
        assert len(events) == 1

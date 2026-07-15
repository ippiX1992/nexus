from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.infrastructure.database import SessionFactory
from app.infrastructure.models import AuditLogModel
from app.infrastructure.tenant_context import set_tenant_context
from app.modules.catalog.infrastructure.models import (
    CategoryClosureModel,
    ProductModel,
    ProductVariantModel,
)
from app.modules.platform.infrastructure.models import OutboxEventModel

pytestmark = pytest.mark.integration


async def catalog_context(client, registration):
    registered = await client.post("/api/v1/auth/register", json=registration)
    assert registered.status_code == 201
    tenant = registered.json()["tenant"]
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": registration["email"], "password": registration["password"]},
    )
    selected = await client.post(
        "/api/v1/auth/select-tenant",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        json={"tenant_id": tenant["id"]},
    )
    assert selected.status_code == 200
    return {"Authorization": f"Bearer {selected.json()['access_token']}"}, tenant


async def create_store(client, headers, *, code="main", locale="es-EC", activate=True):
    created = await client.post(
        "/api/v1/stores",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "code": code,
            "name": f"{code.title()} Store",
            "slug": f"{code}-store",
            "default_locale": locale,
            "default_currency": "USD",
            "timezone": "America/Guayaquil",
        },
    )
    assert created.status_code == 201, created.text
    store = created.json()
    if activate:
        activated = await client.post(f"/api/v1/stores/{store['id']}/activate", headers=headers)
        assert activated.status_code == 200, activated.text
        store = activated.json()
    return store


async def create_type(client, headers, *, code="physical"):
    response = await client.post(
        "/api/v1/catalog/product-types",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"code": code, "name": code.title(), "description": "Foundation type"},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_brand(client, headers, *, code="nexus"):
    response = await client.post(
        "/api/v1/catalog/brands",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"code": code, "name": code.title(), "slug": f"{code}-brand"},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_product(
    client,
    headers,
    product_type_id,
    *,
    sku="NX-001",
    brand_id=None,
    code="product-001",
    locale="es-EC",
    key=None,
):
    payload = {
        "product_type_id": product_type_id,
        "brand_id": brand_id,
        "code": code,
        "sku": sku,
        "translation": {
            "locale": locale,
            "name": f"Product {sku}",
            "short_description": "Short",
            "long_description": "Long",
            "slug": f"product-{sku.lower()}",
        },
    }
    response = await client.post(
        "/api/v1/catalog/products",
        headers={**headers, "Idempotency-Key": key or str(uuid4())},
        json=payload,
    )
    return response, payload


async def test_product_foundation_is_atomic_idempotent_versioned_and_audited(
    client, registration
):
    headers, tenant = await catalog_context(client, registration)
    await create_store(client, headers)
    product_type = await create_type(client, headers)
    brand = await create_brand(client, headers)
    key = str(uuid4())
    correlation = str(uuid4())

    created, payload = await create_product(
        client,
        {**headers, "X-Correlation-ID": correlation},
        product_type["id"],
        brand_id=brand["id"],
        key=key,
    )
    assert created.status_code == 201, created.text
    detail = created.json()
    product = detail["product"]
    assert product["status"] == "draft"
    assert len(detail["variants"]) == 1
    default = detail["variants"][0]
    assert default["is_default"] is True
    assert default["sku"] == "NX-001"
    assert detail["translations"][0]["locale"] == "es-EC"

    replay = await client.post(
        "/api/v1/catalog/products",
        headers={**headers, "Idempotency-Key": key},
        json=payload,
    )
    assert replay.status_code == 201
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json()["product"]["id"] == product["id"]

    conflict = await client.post(
        "/api/v1/catalog/products",
        headers={**headers, "Idempotency-Key": key},
        json={**payload, "sku": "NX-DIFFERENT"},
    )
    assert conflict.status_code == 409

    activated = await client.post(
        f"/api/v1/catalog/products/{product['id']}/activate",
        headers={**headers, "If-Match": str(product["version"])},
    )
    assert activated.status_code == 200
    assert activated.json()["status"] == "active"

    stale = await client.patch(
        f"/api/v1/catalog/products/{product['id']}",
        headers={**headers, "If-Match": str(product["version"])},
        json={"code": "stale-write"},
    )
    assert stale.status_code == 409
    assert "Version conflict" in stale.text

    identifier = await client.post(
        f"/api/v1/catalog/variants/{default['id']}/identifiers",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "identifier_type": "ean",
            "value": "1234-5670",
            "is_primary": True,
        },
    )
    assert identifier.status_code == 201, identifier.text
    assert identifier.json()["value"] == "1234-5670"
    listed_identifiers = await client.get(
        f"/api/v1/catalog/variants/{default['id']}/identifiers", headers=headers
    )
    assert len(listed_identifiers.json()) == 1
    removed_identifier = await client.delete(
        f"/api/v1/catalog/identifiers/{identifier.json()['id']}", headers=headers
    )
    assert removed_identifier.status_code == 204
    assert (
        await client.get(
            f"/api/v1/catalog/variants/{default['id']}/identifiers", headers=headers
        )
    ).json() == []

    current = await client.get(
        f"/api/v1/catalog/products/{product['id']}", headers=headers
    )
    current_version = current.json()["product"]["version"]
    disabled_locale = await client.put(
        f"/api/v1/catalog/products/{product['id']}/translations/en-US",
        headers={**headers, "If-Match": str(current_version)},
        json={"name": "English", "slug": "english-product"},
    )
    assert disabled_locale.status_code == 422

    translated = await client.put(
        f"/api/v1/catalog/products/{product['id']}/translations/es-EC",
        headers={**headers, "If-Match": str(current_version)},
        json={
            "name": "Producto actualizado",
            "short_description": "Resumen",
            "long_description": "Descripcion completa",
            "slug": "producto-actualizado",
        },
    )
    assert translated.status_code == 200, translated.text
    assert translated.json()["slug"] == "producto-actualizado"

    after_translation = await client.get(
        f"/api/v1/catalog/products/{product['id']}", headers=headers
    )
    translated_version = after_translation.json()["product"]["version"]
    invalid_seo = await client.put(
        f"/api/v1/catalog/products/{product['id']}/seo/es-EC",
        headers={**headers, "If-Match": str(translated_version)},
        json={
            "title": "SEO",
            "canonical_path": "https://example.com/not-allowed",
        },
    )
    assert invalid_seo.status_code == 422

    seo = await client.put(
        f"/api/v1/catalog/products/{product['id']}/seo/es-EC",
        headers={**headers, "If-Match": str(translated_version)},
        json={
            "title": "Catalog SEO",
            "description": "Catalog metadata",
            "canonical_path": "/products/producto-actualizado",
            "robots_index": True,
            "robots_follow": True,
        },
    )
    assert seo.status_code == 200, seo.text
    assert seo.json()["canonical_path"] == "/products/producto-actualizado"
    localized = await client.get(
        f"/api/v1/catalog/products/{product['id']}", headers=headers
    )
    assert localized.json()["translations"][0]["name"] == "Producto actualizado"
    assert localized.json()["seo"][0]["title"] == "Catalog SEO"

    detail_after = await client.get(
        f"/api/v1/catalog/products/{product['id']}", headers=headers
    )
    archive = await client.post(
        f"/api/v1/catalog/products/{product['id']}/archive",
        headers={
            **headers,
            "If-Match": str(detail_after.json()["product"]["version"]),
        },
    )
    assert archive.status_code == 200
    assert archive.json()["status"] == "archived"

    async with SessionFactory() as db:
        await set_tenant_context(db, UUID(tenant["id"]))
        products = (
            await db.scalars(
                select(ProductModel).where(ProductModel.tenant_id == tenant["id"])
            )
        ).all()
        variants = (
            await db.scalars(
                select(ProductVariantModel).where(
                    ProductVariantModel.tenant_id == tenant["id"]
                )
            )
        ).all()
        events = (
            await db.scalars(
                select(OutboxEventModel).where(
                    OutboxEventModel.tenant_id == tenant["id"]
                )
            )
        ).all()
        audits = (
            await db.scalars(
                select(AuditLogModel).where(AuditLogModel.tenant_id == tenant["id"])
            )
        ).all()

    assert len(products) == 1
    assert len(variants) == 1
    event_types = [event.event_type for event in events]
    assert event_types.count("catalog.product.created.v1") == 1
    assert {
        "catalog.variant.created.v1",
        "catalog.product.activated.v1",
        "catalog.product.archived.v1",
        "catalog.variant.updated.v1",
    } <= set(event_types)
    product_event = next(
        event for event in events if event.event_type == "catalog.product.created.v1"
    )
    assert str(product_event.correlation_id) == correlation
    assert {
        "catalog.product_created",
        "catalog.product_activated",
        "catalog.version_conflict",
        "catalog.identifier_created",
        "catalog.identifier_archived",
        "catalog.product_archived",
    } <= {audit.action for audit in audits}


async def test_catalog_filters_cursor_quota_sku_and_cross_tenant_references(
    client, registration
):
    headers, tenant = await catalog_context(client, registration)
    store = await create_store(client, headers)
    product_type = await create_type(client, headers)
    brand = await create_brand(client, headers)

    first, _ = await create_product(
        client, headers, product_type["id"], sku="SKU-CASE", brand_id=brand["id"]
    )
    assert first.status_code == 201, first.text
    duplicate, _ = await create_product(
        client,
        headers,
        product_type["id"],
        sku="sku-case",
        brand_id=brand["id"],
        code="duplicate",
    )
    assert duplicate.status_code == 409

    second, _ = await create_product(
        client,
        headers,
        product_type["id"],
        sku="SKU-002",
        brand_id=brand["id"],
        code="product-002",
    )
    assert second.status_code == 201, second.text

    page_one = await client.get(
        "/api/v1/catalog/products",
        headers=headers,
        params={"limit": 1, "brand": brand["id"]},
    )
    assert page_one.status_code == 200
    assert page_one.json()["has_more"] is True
    page_two = await client.get(
        "/api/v1/catalog/products",
        headers=headers,
        params={"limit": 1, "cursor": page_one.json()["next_cursor"]},
    )
    assert page_two.status_code == 200
    assert page_two.json()["items"][0]["id"] != page_one.json()["items"][0]["id"]
    search = await client.get(
        "/api/v1/catalog/products", headers=headers, params={"search": "sku-ca"}
    )
    assert [item["default_sku"] for item in search.json()["items"]] == ["SKU-CASE"]
    invalid_cursor = await client.get(
        "/api/v1/catalog/products", headers=headers, params={"cursor": "tampered"}
    )
    assert invalid_cursor.status_code == 400

    await client.put(
        "/api/v1/platform/entitlements/catalog.products.max",
        headers=headers,
        json={"value": 2},
    )
    quota_key = str(uuid4())
    quota, quota_payload = await create_product(
        client,
        headers,
        product_type["id"],
        sku="SKU-003",
        code="product-003",
        key=quota_key,
    )
    assert quota.status_code == 429
    assert "catalog.products.max" in quota.text
    quota_replay = await client.post(
        "/api/v1/catalog/products",
        headers={**headers, "Idempotency-Key": quota_key},
        json=quota_payload,
    )
    assert quota_replay.status_code == 429
    assert quota_replay.headers["Idempotency-Replayed"] == "true"
    assert quota_replay.json() == quota.json()
    usage = await client.get("/api/v1/catalog/usage", headers=headers)
    assert usage.json() == {"products": 2, "product_limit": 2}

    other_registration = {
        **registration,
        "email": "catalog-other@example.com",
        "company": "Catalog Other",
    }
    other_headers, _ = await catalog_context(client, other_registration)
    other_store = await create_store(client, other_headers, code="other")
    other_type = await create_type(client, other_headers, code="other-type")
    other_brand = await create_brand(client, other_headers, code="other-brand")
    same_sku, _ = await create_product(
        client, other_headers, other_type["id"], sku="SKU-CASE", code="other-product"
    )
    assert same_sku.status_code == 201, same_sku.text

    foreign_type, _ = await create_product(
        client, headers, other_type["id"], sku="FOREIGN-TYPE", code="foreign-type"
    )
    foreign_variant = await client.post(
        f"/api/v1/catalog/products/{same_sku.json()['product']['id']}/variants",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"sku": "FOREIGN-VARIANT"},
    )
    assert foreign_variant.status_code == 404
    foreign_store_assignment = await client.put(
        f"/api/v1/catalog/products/{first.json()['product']['id']}/stores/{other_store['id']}",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"status": "draft"},
    )
    assert foreign_store_assignment.status_code == 404
    foreign_product_assignment = await client.put(
        f"/api/v1/catalog/products/{same_sku.json()['product']['id']}/stores/{store['id']}",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"status": "draft"},
    )
    assert foreign_product_assignment.status_code == 404

    foreign_brand, _ = await create_product(
        client,
        headers,
        product_type["id"],
        sku="FOREIGN-BRAND",
        brand_id=other_brand["id"],
        code="foreign-brand",
    )
    assert foreign_type.status_code == 404
    assert foreign_brand.status_code == 404
    assert (
        await client.get(
            f"/api/v1/catalog/products/{same_sku.json()['product']['id']}",
            headers=headers,
        )
    ).status_code == 404
    assert (
        await client.put(
            f"/api/v1/catalog/products/{first.json()['product']['id']}/stores/{store['id']}",
            headers={**headers, "Idempotency-Key": str(uuid4())},
            json={"status": "draft"},
        )
    ).status_code == 200

    async with SessionFactory() as db:
        await set_tenant_context(db, UUID(tenant["id"]))
        denied = await db.scalar(
            select(AuditLogModel).where(
                AuditLogModel.tenant_id == tenant["id"],
                AuditLogModel.action == "catalog.scope_denied",
            )
        )
        assert denied is not None


async def test_taxonomy_closure_primary_category_and_store_assignment(
    client, registration
):
    headers, tenant = await catalog_context(client, registration)
    store = await create_store(client, headers)
    suspended_store = await create_store(client, headers, code="paused")
    await client.post(f"/api/v1/stores/{suspended_store['id']}/suspend", headers=headers)
    product_type = await create_type(client, headers)
    product_response, _ = await create_product(
        client, headers, product_type["id"], sku="TREE-001"
    )
    product = product_response.json()["product"]
    activated = await client.post(
        f"/api/v1/catalog/products/{product['id']}/activate",
        headers={**headers, "If-Match": str(product["version"])},
    )
    assert activated.status_code == 200
    product_version = activated.json()["version"]

    taxonomy_response = await client.post(
        "/api/v1/catalog/taxonomies",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"code": "main", "name": "Main taxonomy"},
    )
    assert taxonomy_response.status_code == 201
    taxonomy = taxonomy_response.json()

    async def category(code, parent_id=None):
        result = await client.post(
            f"/api/v1/catalog/taxonomies/{taxonomy['id']}/categories",
            headers={**headers, "Idempotency-Key": str(uuid4())},
            json={
                "parent_id": parent_id,
                "code": code,
                "name": code.title(),
                "slug": f"{code}-slug",
                "position": 0,
            },
        )
        assert result.status_code == 201, result.text
        return result.json()

    root = await category("root")
    child = await category("child", root["id"])
    leaf = await category("leaf", child["id"])
    sibling = await category("sibling", root["id"])

    cycle = await client.post(
        f"/api/v1/catalog/categories/{root['id']}/move",
        headers={**headers, "If-Match": str(root["version"])},
        json={"parent_id": leaf["id"], "position": 0},
    )
    assert cycle.status_code == 422

    moved = await client.post(
        f"/api/v1/catalog/categories/{leaf['id']}/move",
        headers={**headers, "If-Match": str(leaf["version"])},
        json={"parent_id": root["id"], "position": 1},
    )
    assert moved.status_code == 200
    assert moved.json()["parent_id"] == root["id"]

    duplicate_slug = await client.post(
        f"/api/v1/catalog/taxonomies/{taxonomy['id']}/categories",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "code": "duplicate",
            "name": "Duplicate",
            "slug": root["slug"],
            "position": 0,
        },
    )
    assert duplicate_slug.status_code == 409

    primary_conflict = await client.put(
        f"/api/v1/catalog/products/{product['id']}/categories",
        headers={**headers, "If-Match": str(product_version)},
        json={
            "assignments": [
                {"category_id": child["id"], "is_primary": True, "position": 0},
                {"category_id": sibling["id"], "is_primary": True, "position": 1},
            ]
        },
    )
    assert primary_conflict.status_code == 409

    assigned_categories = await client.put(
        f"/api/v1/catalog/products/{product['id']}/categories",
        headers={**headers, "If-Match": str(product_version)},
        json={
            "assignments": [
                {"category_id": child["id"], "is_primary": True, "position": 0},
                {"category_id": sibling["id"], "is_primary": False, "position": 1},
            ]
        },
    )
    assert assigned_categories.status_code == 200, assigned_categories.text
    assert sum(item["is_primary"] for item in assigned_categories.json()) == 1

    store_key = str(uuid4())
    assignment = await client.put(
        f"/api/v1/catalog/products/{product['id']}/stores/{store['id']}",
        headers={**headers, "Idempotency-Key": store_key},
        json={"status": "active"},
    )
    assert assignment.status_code == 200, assignment.text
    assert assignment.json()["eligible"] is True
    replay = await client.put(
        f"/api/v1/catalog/products/{product['id']}/stores/{store['id']}",
        headers={**headers, "Idempotency-Key": store_key},
        json={"status": "active"},
    )
    assert replay.status_code == 200
    assert replay.headers["Idempotency-Replayed"] == "true"
    paused = await client.put(
        f"/api/v1/catalog/products/{product['id']}/stores/{suspended_store['id']}",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"status": "active"},
    )
    assert paused.status_code == 422

    unassigned = await client.delete(
        f"/api/v1/catalog/products/{product['id']}/stores/{store['id']}",
        headers={**headers, "If-Match": str(assignment.json()["version"])},
    )
    assert unassigned.status_code == 200
    assert unassigned.json()["status"] == "archived"
    assert unassigned.json()["eligible"] is False

    async with SessionFactory() as db:
        await set_tenant_context(db, UUID(tenant["id"]))
        self_links = await db.scalar(
            select(func.count())
            .select_from(CategoryClosureModel)
            .where(
                CategoryClosureModel.tenant_id == tenant["id"],
                CategoryClosureModel.taxonomy_id == taxonomy["id"],
                CategoryClosureModel.depth == 0,
            )
        )
        root_to_leaf = await db.scalar(
            select(CategoryClosureModel.depth).where(
                CategoryClosureModel.tenant_id == tenant["id"],
                CategoryClosureModel.taxonomy_id == taxonomy["id"],
                CategoryClosureModel.ancestor_id == root["id"],
                CategoryClosureModel.descendant_id == leaf["id"],
            )
        )
    assert self_links == 4
    assert root_to_leaf == 1


async def test_viewer_can_read_catalog_but_cannot_manage_it(client, registration):
    headers, tenant = await catalog_context(client, registration)
    viewer = next(
        role
        for role in (await client.get("/api/v1/roles", headers=headers)).json()
        if role["name"] == "viewer"
    )
    invitation = await client.post(
        "/api/v1/members/invitations",
        headers=headers,
        json={"email": "catalog-viewer@example.com", "role_ids": [viewer["id"]]},
    )
    accepted = await client.post(
        "/api/v1/members/invitations/accept",
        json={
            "token": invitation.json()["invitation_token"],
            "password": "Catalog-Viewer-99",
            "full_name": "Catalog Viewer",
        },
    )
    assert accepted.status_code == 200
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "catalog-viewer@example.com",
            "password": "Catalog-Viewer-99",
        },
    )
    selected = await client.post(
        "/api/v1/auth/select-tenant",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        json={"tenant_id": tenant["id"]},
    )
    viewer_headers = {
        "Authorization": f"Bearer {selected.json()['access_token']}"
    }

    assert (
        await client.get("/api/v1/catalog/products", headers=viewer_headers)
    ).status_code == 200
    forbidden = await client.post(
        "/api/v1/catalog/product-types",
        headers={**viewer_headers, "Idempotency-Key": str(uuid4())},
        json={"code": "denied", "name": "Denied"},
    )
    assert forbidden.status_code == 403


async def test_reference_and_variant_lifecycle_preserves_catalog_invariants(
    client, registration
):
    headers, _ = await catalog_context(client, registration)
    await create_store(client, headers)
    product_type = await create_type(client, headers)
    brand = await create_brand(client, headers)

    updated_type = await client.patch(
        f"/api/v1/catalog/product-types/{product_type['id']}",
        headers={**headers, "If-Match": str(product_type["version"])},
        json={"name": "Updated Type"},
    )
    assert updated_type.status_code == 200
    stale_type = await client.patch(
        f"/api/v1/catalog/product-types/{product_type['id']}",
        headers={**headers, "If-Match": str(product_type["version"])},
        json={"name": "Stale Type"},
    )
    assert stale_type.status_code == 409

    updated_brand = await client.patch(
        f"/api/v1/catalog/brands/{brand['id']}",
        headers={**headers, "If-Match": str(brand["version"])},
        json={"name": "Updated Brand", "slug": "updated-brand"},
    )
    assert updated_brand.status_code == 200

    created, _ = await create_product(
        client,
        headers,
        product_type["id"],
        brand_id=brand["id"],
        sku="VARIANT-BASE",
    )
    assert created.status_code == 201
    detail = created.json()
    product = detail["product"]
    default = detail["variants"][0]

    explicit = await client.post(
        f"/api/v1/catalog/products/{product['id']}/variants",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"sku": "VARIANT-EXPLICIT"},
    )
    assert explicit.status_code == 201
    changed = await client.patch(
        f"/api/v1/catalog/variants/{explicit.json()['id']}",
        headers={**headers, "If-Match": str(explicit.json()["version"])},
        json={"sku": "VARIANT-CHANGED"},
    )
    assert changed.status_code == 200
    archived_explicit = await client.post(
        f"/api/v1/catalog/variants/{explicit.json()['id']}/archive",
        headers={**headers, "If-Match": str(changed.json()["version"])},
    )
    assert archived_explicit.status_code == 200

    current = await client.get(
        f"/api/v1/catalog/products/{product['id']}", headers=headers
    )
    activated = await client.post(
        f"/api/v1/catalog/products/{product['id']}/activate",
        headers={
            **headers,
            "If-Match": str(current.json()["product"]["version"]),
        },
    )
    assert activated.status_code == 200
    only_active = await client.post(
        f"/api/v1/catalog/variants/{default['id']}/archive",
        headers={**headers, "If-Match": str(default["version"])},
    )
    assert only_active.status_code == 422

    first_identifier = await client.post(
        f"/api/v1/catalog/variants/{default['id']}/identifiers",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"identifier_type": "ean", "value": "12345670", "is_primary": True},
    )
    assert first_identifier.status_code == 201
    second_primary = await client.post(
        f"/api/v1/catalog/variants/{default['id']}/identifiers",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"identifier_type": "ean", "value": "87654321", "is_primary": True},
    )
    assert second_primary.status_code == 409
    assert (
        await client.delete(
            f"/api/v1/catalog/identifiers/{first_identifier.json()['id']}",
            headers=headers,
        )
    ).status_code == 204
    reserved_identifier = await client.post(
        f"/api/v1/catalog/variants/{default['id']}/identifiers",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"identifier_type": "ean", "value": "1234-5670", "is_primary": False},
    )
    assert reserved_identifier.status_code == 409

    archived_brand = await client.post(
        f"/api/v1/catalog/brands/{brand['id']}/archive",
        headers={**headers, "If-Match": str(updated_brand.json()["version"])},
    )
    archived_type = await client.post(
        f"/api/v1/catalog/product-types/{product_type['id']}/archive",
        headers={**headers, "If-Match": str(updated_type.json()["version"])},
    )
    assert archived_brand.status_code == 200
    assert archived_type.status_code == 200
    archived_reference, _ = await create_product(
        client,
        headers,
        product_type["id"],
        brand_id=brand["id"],
        sku="ARCHIVED-REFERENCE",
        code="archived-reference",
    )
    assert archived_reference.status_code == 422

    existing = await client.get(
        f"/api/v1/catalog/products/{product['id']}", headers=headers
    )
    assert existing.status_code == 200
    assert existing.json()["product"]["brand_id"] == brand["id"]

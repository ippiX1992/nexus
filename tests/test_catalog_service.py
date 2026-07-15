from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.modules.catalog.application.services import CatalogActor, CatalogService
from app.modules.catalog.domain.policies import (
    CatalogConflict,
    CatalogNotFound,
    CatalogPolicyError,
    CatalogQuotaExceeded,
    CatalogVersionConflict,
    CategoryCycle,
)

REPOSITORY_METHODS = (
    "lock_tenant",
    "entitlement_limit",
    "count_products",
    "count_variants",
    "count_active_variants",
    "get_product_type",
    "get_brand",
    "get_product",
    "get_variant",
    "get_taxonomy",
    "get_category",
    "get_identifier",
    "get_store",
    "get_store_assignment",
    "locale_enabled",
    "list_product_stores",
    "list_categories",
    "list_product_categories",
    "create_product_type",
    "create_brand",
    "create_product",
    "create_variant",
    "create_identifier",
    "upsert_translation",
    "upsert_seo",
    "create_taxonomy",
    "create_category",
    "add_category_closure",
    "move_category_closure",
    "category_would_cycle",
    "replace_product_categories",
    "create_store_assignment",
    "add_event",
    "flush",
)


def row(**values):
    defaults = {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "status": "active",
        "version": 1,
        "archived_at": None,
        "updated_by": None,
    }
    return SimpleNamespace(**{**defaults, **values})


def service_fixture():
    actor = CatalogActor(
        user_id=uuid4(),
        session_id=uuid4(),
        tenant_id=uuid4(),
        correlation_id=uuid4(),
    )
    repository = SimpleNamespace(
        **{name: AsyncMock(name=name) for name in REPOSITORY_METHODS}
    )
    repository.entitlement_limit.return_value = 100
    repository.count_products.return_value = 0
    repository.count_variants.return_value = 1
    repository.count_active_variants.return_value = 1
    repository.locale_enabled.return_value = True
    repository.list_product_stores.return_value = []
    repository.list_categories.return_value = []
    repository.list_product_categories.return_value = []
    audit_session = Mock()
    return CatalogService(repository, actor, audit_session), repository, actor, audit_session


async def test_product_type_and_brand_services_cover_lifecycle_and_denials():
    service, repository, actor, audit_session = service_fixture()
    product_type = row(
        tenant_id=actor.tenant_id,
        code="physical",
        name="Physical",
        description=None,
    )
    brand = row(
        tenant_id=actor.tenant_id,
        code="nexus",
        name="Nexus",
        slug="nexus",
    )
    repository.create_product_type.return_value = product_type
    repository.get_product_type.return_value = product_type
    repository.create_brand.return_value = brand
    repository.get_brand.return_value = brand

    assert (
        await service.create_product_type(
            {"code": "PHYSICAL", "name": " Physical ", "description": None}
        )
        is product_type
    )
    updated_type = await service.update_product_type(
        product_type.id,
        1,
        {"name": " Updated ", "description": " Description "},
    )
    assert updated_type.name == "Updated"
    assert updated_type.description == "Description"
    assert updated_type.version == 2
    archived_type = await service.archive_product_type(product_type.id, 2)
    assert archived_type.status == "archived"
    assert archived_type.archived_at is not None
    assert await service.archive_product_type(product_type.id, 3) is product_type

    assert (
        await service.create_brand(
            {"code": "NEXUS", "name": " Nexus ", "slug": "Nexus Brand"}
        )
        is brand
    )
    updated_brand = await service.update_brand(
        brand.id,
        1,
        {"name": " Updated Brand ", "slug": "Updated Brand"},
    )
    assert updated_brand.name == "Updated Brand"
    assert updated_brand.slug == "updated-brand"
    archived_brand = await service.archive_brand(brand.id, 2)
    assert archived_brand.status == "archived"
    assert await service.archive_brand(brand.id, 3) is brand

    repository.get_product_type.return_value = None
    with pytest.raises(CatalogNotFound):
        await service.update_product_type(uuid4(), 1, {"name": "Missing"})
    repository.get_brand.return_value = row(version=4)
    with pytest.raises(CatalogVersionConflict):
        await service.update_brand(repository.get_brand.return_value.id, 3, {"name": "Stale"})
    with pytest.raises(CatalogQuotaExceeded):
        await service._quota("catalog.products.max", 2, 2)

    assert audit_session.add.call_count >= 9
    event_types = [call.args[0].event_type for call in repository.add_event.await_args_list]
    assert {
        "catalog.product_type.created.v1",
        "catalog.product_type.updated.v1",
        "catalog.product_type.archived.v1",
        "catalog.brand.created.v1",
        "catalog.brand.updated.v1",
        "catalog.brand.archived.v1",
    } <= set(event_types)


async def test_product_variant_identifier_translation_and_seo_services():
    service, repository, actor, _ = service_fixture()
    product_type = row(
        tenant_id=actor.tenant_id,
        code="physical",
        name="Physical",
    )
    brand = row(tenant_id=actor.tenant_id, code="brand", name="Brand", slug="brand")
    replacement_brand = row(
        tenant_id=actor.tenant_id,
        code="replacement",
        name="Replacement",
        slug="replacement",
    )
    product = row(
        tenant_id=actor.tenant_id,
        product_type_id=product_type.id,
        brand_id=brand.id,
        code="product",
        status="draft",
    )
    default_variant = row(
        tenant_id=actor.tenant_id,
        product_id=product.id,
        sku="BASE-SKU",
        sku_normalized="base-sku",
        is_default=True,
        status="active",
    )
    explicit_variant = row(
        tenant_id=actor.tenant_id,
        product_id=product.id,
        sku="EXPLICIT-SKU",
        sku_normalized="explicit-sku",
        is_default=False,
        status="active",
    )
    translation = row(
        tenant_id=actor.tenant_id,
        product_id=product.id,
        locale="es-EC",
        name="Product",
        slug="product",
    )
    seo = row(
        tenant_id=actor.tenant_id,
        product_id=product.id,
        locale="es-EC",
        title="SEO",
    )
    identifier = row(
        tenant_id=actor.tenant_id,
        variant_id=default_variant.id,
        identifier_type="ean",
        value="12345670",
        normalized_value="12345670",
        source_system=None,
        is_primary=True,
    )
    assignment = row(
        tenant_id=actor.tenant_id,
        product_id=product.id,
        store_id=uuid4(),
        status="active",
        eligible=True,
    )

    repository.get_product_type.return_value = product_type
    repository.get_brand.return_value = brand
    repository.create_product.return_value = product
    repository.create_variant.side_effect = [default_variant, explicit_variant]
    repository.upsert_translation.return_value = translation
    repository.get_product.return_value = product
    repository.create_identifier.return_value = identifier
    repository.get_identifier.return_value = identifier
    repository.upsert_seo.return_value = seo

    created_product, created_default = await service.create_product(
        {
            "product_type_id": product_type.id,
            "brand_id": brand.id,
            "code": " Product ",
            "sku": " BASE-SKU ",
            "translation": {
                "locale": "es-ec",
                "name": " Product ",
                "short_description": "Short",
                "long_description": "Long",
                "slug": "Product Slug",
            },
        }
    )
    assert created_product is product
    assert created_default is default_variant

    repository.get_brand.return_value = replacement_brand
    updated = await service.update_product(
        product.id,
        1,
        {"code": "Updated-Product", "brand_id": replacement_brand.id},
    )
    assert updated.code == "updated-product"
    assert updated.brand_id == replacement_brand.id
    assert updated.version == 2

    activated = await service.activate_product(product.id, 2)
    assert activated.status == "active"
    assert activated.version == 3
    assert await service.activate_product(product.id, 3) is product

    created_variant = await service.create_variant(
        product.id, {"sku": " EXPLICIT-SKU "}
    )
    assert created_variant is explicit_variant
    assert product.version == 4

    repository.get_variant.return_value = explicit_variant
    changed_variant = await service.update_variant(
        explicit_variant.id,
        1,
        {"sku": "CHANGED-SKU"},
    )
    assert changed_variant.sku == "CHANGED-SKU"
    assert changed_variant.version == 2
    assert product.version == 5

    repository.count_active_variants.return_value = 2
    archived_variant = await service.archive_variant(explicit_variant.id, 2)
    assert archived_variant.status == "archived"
    assert archived_variant.version == 3
    assert product.version == 6
    assert await service.archive_variant(explicit_variant.id, 3) is explicit_variant

    repository.get_variant.return_value = default_variant
    created_identifier = await service.create_identifier(
        default_variant.id,
        {
            "identifier_type": "EAN",
            "value": "1234-5670",
            "source_system": None,
            "is_primary": True,
        },
    )
    assert created_identifier is identifier
    assert product.version == 7

    archived_identifier = await service.archive_identifier(identifier.id)
    assert archived_identifier.archived_at is not None
    assert archived_identifier.is_primary is False
    assert product.version == 8
    assert await service.archive_identifier(identifier.id) is identifier

    translated = await service.upsert_translation(
        product.id,
        "es-ec",
        8,
        {
            "name": " Updated ",
            "short_description": None,
            "long_description": None,
            "slug": "Updated Slug",
        },
    )
    assert translated is translation
    assert product.version == 9

    with pytest.raises(CatalogPolicyError, match="canonical_path"):
        await service.upsert_seo(
            product.id,
            "es-EC",
            9,
            {
                "title": "Invalid",
                "canonical_path": "https://example.com/product",
                "robots_index": True,
                "robots_follow": True,
            },
        )
    assert (
        await service.upsert_seo(
            product.id,
            "es-EC",
            9,
            {
                "title": "SEO",
                "description": "Description",
                "canonical_path": "/product",
                "robots_index": True,
                "robots_follow": True,
            },
        )
        is seo
    )
    assert product.version == 10

    repository.list_product_stores.return_value = [assignment]
    archived_product = await service.archive_product(product.id, 10)
    assert archived_product.status == "archived"
    assert assignment.status == "suspended"
    assert assignment.eligible is False
    assert product.version == 11
    assert await service.archive_product(product.id, 11) is product

    with pytest.raises(CatalogPolicyError, match="Archived products"):
        await service.update_product(product.id, 11, {"code": "forbidden"})

    event_types = [call.args[0].event_type for call in repository.add_event.await_args_list]
    assert {
        "catalog.product.created.v1",
        "catalog.product.updated.v1",
        "catalog.product.activated.v1",
        "catalog.product.archived.v1",
        "catalog.variant.created.v1",
        "catalog.variant.updated.v1",
        "catalog.variant.archived.v1",
    } <= set(event_types)


async def test_product_service_rejects_bad_references_locales_and_quotas():
    service, repository, actor, _ = service_fixture()
    product_type = row(tenant_id=actor.tenant_id)
    repository.get_product_type.return_value = None

    with pytest.raises(CatalogNotFound):
        await service.create_product(
            {
                "product_type_id": uuid4(),
                "brand_id": None,
                "code": "missing",
                "sku": "MISSING",
                "translation": None,
            }
        )

    repository.get_product_type.return_value = product_type
    repository.get_brand.return_value = None
    with pytest.raises(CatalogNotFound):
        await service.create_product(
            {
                "product_type_id": product_type.id,
                "brand_id": uuid4(),
                "code": "brand-missing",
                "sku": "BRAND-MISSING",
                "translation": None,
            }
        )

    repository.get_brand.return_value = row(status="archived")
    with pytest.raises(CatalogPolicyError, match="Archived Brand"):
        await service.create_product(
            {
                "product_type_id": product_type.id,
                "brand_id": repository.get_brand.return_value.id,
                "code": "brand-archived",
                "sku": "BRAND-ARCHIVED",
                "translation": None,
            }
        )

    repository.get_brand.return_value = None
    repository.locale_enabled.return_value = False
    with pytest.raises(CatalogPolicyError, match="Locale"):
        await service.create_product(
            {
                "product_type_id": product_type.id,
                "brand_id": None,
                "code": "locale",
                "sku": "LOCALE",
                "translation": {
                    "locale": "en-US",
                    "name": "English",
                    "slug": "english",
                },
            }
        )

    repository.locale_enabled.return_value = True
    repository.entitlement_limit.return_value = 1
    repository.count_products.return_value = 1
    with pytest.raises(CatalogQuotaExceeded):
        await service.create_product(
            {
                "product_type_id": product_type.id,
                "brand_id": None,
                "code": "quota",
                "sku": "QUOTA",
                "translation": None,
            }
        )


async def test_taxonomy_category_and_assignment_services():
    service, repository, actor, _ = service_fixture()
    taxonomy = row(
        tenant_id=actor.tenant_id,
        code="main",
        name="Main",
        status="active",
    )
    root = row(
        tenant_id=actor.tenant_id,
        taxonomy_id=taxonomy.id,
        parent_id=None,
        code="root",
        name="Root",
        slug="root",
        position=0,
        status="active",
    )
    child = row(
        tenant_id=actor.tenant_id,
        taxonomy_id=taxonomy.id,
        parent_id=root.id,
        code="child",
        name="Child",
        slug="child",
        position=0,
        status="active",
    )
    product = row(
        tenant_id=actor.tenant_id,
        product_type_id=uuid4(),
        brand_id=None,
        code="product",
        status="active",
    )
    category_assignment = SimpleNamespace(
        product_id=product.id,
        category_id=child.id,
        taxonomy_id=taxonomy.id,
        is_primary=True,
        position=0,
    )
    store = row(
        tenant_id=actor.tenant_id,
        code="store",
        name="Store",
        status="active",
    )
    store_assignment = row(
        tenant_id=actor.tenant_id,
        product_id=product.id,
        store_id=store.id,
        status="active",
        eligible=True,
    )
    category_map = {root.id: root, child.id: child}

    repository.create_taxonomy.return_value = taxonomy
    repository.get_taxonomy.return_value = taxonomy
    repository.create_category.side_effect = [root, child]
    repository.get_category.side_effect = (
        lambda _tenant, resource_id, **_kwargs: category_map.get(resource_id)
    )
    repository.get_product.return_value = product
    repository.list_product_categories.return_value = [category_assignment]
    repository.get_store.return_value = store
    repository.get_store_assignment.return_value = None
    repository.create_store_assignment.return_value = store_assignment

    assert (
        await service.create_taxonomy({"code": "MAIN", "name": " Main "})
        is taxonomy
    )
    assert (
        await service.create_category(
            taxonomy.id,
            {
                "parent_id": None,
                "code": "ROOT",
                "name": " Root ",
                "slug": "Root Category",
                "position": 0,
            },
        )
        is root
    )
    assert (
        await service.create_category(
            taxonomy.id,
            {
                "parent_id": root.id,
                "code": "CHILD",
                "name": " Child ",
                "slug": "Child Category",
                "position": 1,
            },
        )
        is child
    )
    assert taxonomy.version == 3

    updated = await service.update_category(
        child.id,
        1,
        {"name": " Updated Child ", "slug": "Updated Child", "position": 2},
    )
    assert updated.name == "Updated Child"
    assert updated.slug == "updated-child"
    assert updated.position == 2
    assert updated.version == 2
    assert taxonomy.version == 4

    repository.category_would_cycle.return_value = True
    with pytest.raises(CategoryCycle):
        await service.move_category(root.id, 1, child.id, 0)

    repository.category_would_cycle.return_value = False
    moved = await service.move_category(child.id, 2, root.id, 3)
    assert moved.parent_id == root.id
    assert moved.position == 3
    assert moved.version == 3
    assert taxonomy.version == 5

    repository.list_categories.return_value = [
        root,
        child,
        row(parent_id=child.id, status="active"),
    ]
    with pytest.raises(CatalogConflict, match="active children"):
        await service.archive_category(child.id, 3)

    repository.list_categories.return_value = [root, child]
    archived = await service.archive_category(child.id, 3)
    assert archived.status == "archived"
    assert archived.version == 4
    assert taxonomy.version == 6
    assert await service.archive_category(child.id, 4) is child

    child.status = "active"
    child.archived_at = None
    duplicate_assignments = [
        {"category_id": root.id, "is_primary": True, "position": 0},
        {"category_id": child.id, "is_primary": True, "position": 1},
    ]
    with pytest.raises(CatalogConflict, match="Only one primary"):
        await service.assign_categories(product.id, 1, duplicate_assignments)

    assignments = [
        {"category_id": child.id, "is_primary": True, "position": 0}
    ]
    result = await service.assign_categories(product.id, 1, assignments)
    assert result == [category_assignment]
    assert product.version == 2

    assigned_store = await service.assign_store(
        product.id,
        store.id,
        {"status": "active", "version": None},
    )
    assert assigned_store is store_assignment
    assert assigned_store.eligible is True
    assert product.version == 3

    repository.get_store_assignment.return_value = store_assignment
    updated_store = await service.assign_store(
        product.id,
        store.id,
        {"status": "draft", "version": 1},
    )
    assert updated_store.status == "draft"
    assert updated_store.eligible is False
    assert updated_store.version == 2
    assert product.version == 4

    unassigned = await service.unassign_store(product.id, store.id, 2)
    assert unassigned.status == "archived"
    assert unassigned.eligible is False
    assert unassigned.version == 3
    assert product.version == 5
    assert await service.unassign_store(product.id, store.id, 3) is store_assignment

    store.status = "suspended"
    with pytest.raises(CatalogPolicyError, match="Only active stores"):
        await service.assign_store(
            product.id,
            store.id,
            {"status": "active", "version": 3},
        )

    event_types = [call.args[0].event_type for call in repository.add_event.await_args_list]
    assert {
        "catalog.taxonomy.created.v1",
        "catalog.category.created.v1",
        "catalog.category.updated.v1",
        "catalog.category.moved.v1",
        "catalog.category.archived.v1",
        "catalog.product.assigned_to_category.v1",
        "catalog.product.assigned_to_store.v1",
        "catalog.product.unassigned_from_store.v1",
    } <= set(event_types)

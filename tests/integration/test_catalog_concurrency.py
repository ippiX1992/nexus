import asyncio
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.infrastructure.database import SessionFactory
from app.infrastructure.tenant_context import set_tenant_context
from app.main import app
from app.modules.catalog.application.services import CatalogActor, CatalogService
from app.modules.catalog.infrastructure.models import ProductModel, ProductVariantModel
from app.modules.catalog.infrastructure.repositories import SqlAlchemyCatalogRepository
from app.modules.platform.infrastructure.models import OutboxEventModel
from tests.integration.test_catalog_api import (
    catalog_context,
    create_product,
    create_store,
    create_type,
)

pytestmark = pytest.mark.integration


async def isolated_client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def test_concurrent_same_sku_has_one_atomic_winner(client, registration):
    headers, tenant = await catalog_context(client, registration)
    await create_store(client, headers)
    product_type = await create_type(client, headers)

    async def create(code):
        async with await isolated_client() as caller:
            return await create_product(
                caller,
                headers,
                product_type["id"],
                sku="RACE-SKU",
                code=code,
            )

    (first, _), (second, _) = await asyncio.gather(
        create("race-first"), create("race-second")
    )
    assert sorted([first.status_code, second.status_code]) == [201, 409]

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
                    OutboxEventModel.tenant_id == tenant["id"],
                    OutboxEventModel.event_type == "catalog.product.created.v1",
                )
            )
        ).all()

    assert len(products) == 1
    assert len(variants) == 1
    assert len(events) == 1


async def test_concurrent_version_and_variant_quota_are_serialized(client, registration):
    headers, _ = await catalog_context(client, registration)
    await create_store(client, headers)
    product_type = await create_type(client, headers)
    created, _ = await create_product(
        client, headers, product_type["id"], sku="SERIAL-BASE"
    )
    product = created.json()["product"]

    async def update(code):
        async with await isolated_client() as caller:
            return await caller.patch(
                f"/api/v1/catalog/products/{product['id']}",
                headers={**headers, "If-Match": str(product["version"])},
                json={"code": code},
            )

    first, second = await asyncio.gather(update("winner-a"), update("winner-b"))
    assert sorted([first.status_code, second.status_code]) == [200, 409]

    override = await client.put(
        "/api/v1/platform/entitlements/catalog.variants.max_per_product",
        headers=headers,
        json={"value": 2},
    )
    assert override.status_code == 200

    async def create_variant(sku):
        async with await isolated_client() as caller:
            return await caller.post(
                f"/api/v1/catalog/products/{product['id']}/variants",
                headers={**headers, "Idempotency-Key": str(uuid4())},
                json={"sku": sku},
            )

    variant_a, variant_b = await asyncio.gather(
        create_variant("SERIAL-A"), create_variant("SERIAL-B")
    )
    assert sorted([variant_a.status_code, variant_b.status_code]) == [201, 429]
    listed = await client.get(
        f"/api/v1/catalog/products/{product['id']}/variants", headers=headers
    )
    assert len(listed.json()["items"]) == 2


async def test_archived_sku_stays_reserved_and_rollback_leaves_no_orphans(
    client, registration
):
    headers, tenant = await catalog_context(client, registration)
    await create_store(client, headers)
    product_type = await create_type(client, headers)
    created, _ = await create_product(
        client, headers, product_type["id"], sku="ROLLBACK-BASE"
    )
    product = created.json()["product"]

    explicit = await client.post(
        f"/api/v1/catalog/products/{product['id']}/variants",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"sku": "RESERVED-SKU"},
    )
    assert explicit.status_code == 201
    archived = await client.post(
        f"/api/v1/catalog/variants/{explicit.json()['id']}/archive",
        headers={**headers, "If-Match": str(explicit.json()["version"])},
    )
    assert archived.status_code == 200
    reused = await client.post(
        f"/api/v1/catalog/products/{product['id']}/variants",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"sku": "reserved-sku"},
    )
    assert reused.status_code == 409

    me = await client.get("/api/v1/me", headers=headers)
    tenant_id = UUID(tenant["id"])
    async with SessionFactory() as db:
        await set_tenant_context(db, tenant_id)
        db.add(
            ProductVariantModel(
                tenant_id=tenant_id,
                product_id=UUID(product["id"]),
                sku="SECOND-DEFAULT",
                sku_normalized="second-default",
                is_default=True,
                status="active",
            )
        )
        with pytest.raises(IntegrityError):
            await db.flush()
        await db.rollback()

    rollback_correlation = uuid4()
    async with SessionFactory() as db:
        await set_tenant_context(db, tenant_id)
        service = CatalogService(
            SqlAlchemyCatalogRepository(db),
            CatalogActor(
                user_id=UUID(me.json()["id"]),
                session_id=None,
                tenant_id=tenant_id,
                correlation_id=rollback_correlation,
            ),
            db,
        )
        await service.create_product(
            {
                "product_type_id": UUID(product_type["id"]),
                "brand_id": None,
                "code": "must-rollback",
                "sku": "ROLLBACK-SKU",
                "translation": None,
            }
        )
        await db.rollback()

    async with SessionFactory() as db:
        await set_tenant_context(db, tenant_id)
        assert (
            await db.scalar(
                select(ProductModel).where(ProductModel.code == "must-rollback")
            )
            is None
        )
        assert (
            await db.scalar(
                select(ProductVariantModel).where(
                    ProductVariantModel.sku_normalized == "rollback-sku"
                )
            )
            is None
        )
        assert (
            await db.scalar(
                select(OutboxEventModel).where(OutboxEventModel.correlation_id == rollback_correlation)
            )
            is None
        )

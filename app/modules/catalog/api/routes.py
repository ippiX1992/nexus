from typing import Annotated, Any, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_permission
from app.application.authorization import TenantContext
from app.infrastructure.database import get_session
from app.infrastructure.tenant_context import set_store_context
from app.modules.catalog.api.schemas import (
    BrandCreate,
    BrandPage,
    BrandResponse,
    BrandUpdate,
    CatalogUsageResponse,
    CategoryCreate,
    CategoryMove,
    CategoryResponse,
    CategoryUpdate,
    IdentifierCreate,
    IdentifierResponse,
    ProductCategoriesPut,
    ProductCategoryResponse,
    ProductCreate,
    ProductDetail,
    ProductPage,
    ProductResponse,
    ProductSeoPut,
    ProductSeoResponse,
    ProductStorePut,
    ProductStoreResponse,
    ProductSummary,
    ProductTranslationPut,
    ProductTranslationResponse,
    ProductTypeCreate,
    ProductTypePage,
    ProductTypeResponse,
    ProductTypeUpdate,
    ProductUpdate,
    TaxonomyCreate,
    TaxonomyPage,
    TaxonomyResponse,
    VariantCreate,
    VariantPage,
    VariantResponse,
    VariantUpdate,
)
from app.modules.catalog.application.services import CatalogActor, CatalogService
from app.modules.catalog.domain.policies import (
    CatalogConflict,
    CatalogNotFound,
    CatalogPolicyError,
    CatalogQuotaExceeded,
    CatalogVersionConflict,
    CategoryCycle,
)
from app.modules.catalog.domain.values import decode_cursor, encode_cursor
from app.modules.catalog.infrastructure.repositories import SqlAlchemyCatalogRepository
from app.modules.platform.application.idempotency import (
    IdempotencyConflict,
    IdempotencyInProgress,
    begin_idempotent,
    complete_idempotent,
)

router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])


def _actor(request: Request, ctx: TenantContext) -> CatalogActor:
    return CatalogActor(ctx.user_id, ctx.session_id, ctx.tenant_id, request.state.correlation_id)


def _service(
    request: Request, ctx: TenantContext, db: AsyncSession
) -> tuple[CatalogService, SqlAlchemyCatalogRepository]:
    repository = SqlAlchemyCatalogRepository(db)
    return CatalogService(repository, _actor(request, ctx), db), repository


def _expected_version(value: str) -> int:
    normalized = value.strip()
    if normalized.startswith("W/"):
        normalized = normalized[2:]
    normalized = normalized.strip('"')
    try:
        version = int(normalized)
    except ValueError as exc:
        raise HTTPException(400, "If-Match must contain a positive integer version") from exc
    if version < 1:
        raise HTTPException(400, "If-Match must contain a positive integer version")
    return version


def _cursor(value: str | None) -> tuple[Any, UUID] | None:
    if value is None:
        return None
    try:
        return decode_cursor(value)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def _next_cursor(rows: list[Any], has_more: bool) -> str | None:
    if not rows or not has_more:
        return None
    return encode_cursor(rows[-1].created_at, rows[-1].id)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, CatalogNotFound):
        return HTTPException(404, str(exc))
    if isinstance(exc, CatalogQuotaExceeded):
        return HTTPException(429, str(exc))
    if isinstance(exc, (CatalogVersionConflict, CatalogConflict, IdempotencyConflict)):
        return HTTPException(409, str(exc))
    if isinstance(exc, IdempotencyInProgress):
        return HTTPException(409, str(exc), headers={"Retry-After": "1"})
    if isinstance(exc, CategoryCycle):
        return HTTPException(422, str(exc))
    if isinstance(exc, IntegrityError):
        return HTTPException(409, "Catalog resource conflicts with an existing tenant-scoped value")
    if isinstance(exc, CatalogPolicyError):
        return HTTPException(422, str(exc))
    return HTTPException(400, str(exc))


async def _begin_create(
    db: AsyncSession,
    ctx: TenantContext,
    key: str,
    method: str,
    endpoint: str,
    payload: dict[str, Any],
) -> Any:
    try:
        result = await begin_idempotent(
            db,
            tenant_id=ctx.tenant_id,
            actor_id=ctx.user_id,
            method=method,
            endpoint=endpoint,
            key=key,
            payload=payload,
        )
    except (IdempotencyConflict, IdempotencyInProgress) as exc:
        raise _http_error(exc) from exc
    if result.replay_body is not None:
        return JSONResponse(
            result.replay_body,
            status_code=result.replay_code or 200,
            headers={"Idempotency-Replayed": "true"},
        )
    return result.record


async def _finish_create(db: AsyncSession, record: Any, response: Any, code: int = 201) -> Any:
    body = response.model_dump(mode="json")
    complete_idempotent(record, body, code)
    await db.commit()
    return response


async def _creation_failure(db: AsyncSession, record: Any, exc: Exception) -> NoReturn:
    if isinstance(exc, CatalogPolicyError):
        error = _http_error(exc)
        complete_idempotent(record, {"detail": str(exc)}, error.status_code)
        await db.commit()
    else:
        await db.rollback()
    raise _http_error(exc) from exc


async def _mutation_failure(db: AsyncSession, exc: Exception) -> NoReturn:
    if isinstance(exc, CatalogPolicyError):
        await db.commit()
    else:
        await db.rollback()
    raise _http_error(exc) from exc


async def _finish_mutation[SchemaT: BaseModel](
    db: AsyncSession, row: Any, schema: type[SchemaT]
) -> SchemaT:
    try:
        await db.flush()
        await db.refresh(row)
    except IntegrityError as exc:
        await db.rollback()
        raise _http_error(exc) from exc
    response = schema.model_validate(row)
    await db.commit()
    return response


async def _product_detail(repository: SqlAlchemyCatalogRepository, product: Any) -> ProductDetail:
    variants, _ = await repository.list_variants(
        product.tenant_id, product.id, limit=100, cursor=None
    )
    return ProductDetail(
        product=ProductResponse.model_validate(product),
        variants=[VariantResponse.model_validate(row) for row in variants],
        translations=[
            ProductTranslationResponse.model_validate(row)
            for row in await repository.list_translations(product.tenant_id, product.id)
        ],
        seo=[
            ProductSeoResponse.model_validate(row)
            for row in await repository.list_seo(product.tenant_id, product.id)
        ],
        categories=[
            ProductCategoryResponse.model_validate(row)
            for row in await repository.list_product_categories(product.tenant_id, product.id)
        ],
        stores=[
            ProductStoreResponse.model_validate(row)
            for row in await repository.list_product_stores(product.tenant_id, product.id)
        ],
    )


@router.get("/product-types", response_model=ProductTypePage)
async def list_product_types(
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.product_type.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
    status: str | None = None,
) -> ProductTypePage:
    rows, has_more = await SqlAlchemyCatalogRepository(db).list_resources(
        "product_type", ctx.tenant_id, limit=limit, cursor=_cursor(cursor), status=status
    )
    return ProductTypePage(
        items=[ProductTypeResponse.model_validate(row) for row in rows],
        next_cursor=_next_cursor(rows, has_more),
        has_more=has_more,
    )


@router.post("/product-types", response_model=ProductTypeResponse, status_code=201)
async def create_product_type(
    payload: ProductTypeCreate,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.product_type.manage"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Any:
    record = await _begin_create(
        db, ctx, idempotency_key, "POST", "/api/v1/catalog/product-types", payload.model_dump(mode="json")
    )
    if isinstance(record, JSONResponse):
        return record
    service, _ = _service(request, ctx, db)
    try:
        row = await service.create_product_type(payload.model_dump())
        await db.flush()
        response = ProductTypeResponse.model_validate(row)
    except (CatalogPolicyError, IntegrityError, ValueError) as exc:
        await _creation_failure(db, record, exc)
    return await _finish_create(db, record, response)


@router.get("/product-types/{resource_id}", response_model=ProductTypeResponse)
async def get_product_type(
    resource_id: UUID,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.product_type.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> ProductTypeResponse:
    row = await SqlAlchemyCatalogRepository(db).get_product_type(ctx.tenant_id, resource_id)
    if row is None:
        raise HTTPException(404, "Product Type not found")
    return ProductTypeResponse.model_validate(row)


@router.patch("/product-types/{resource_id}", response_model=ProductTypeResponse)
async def update_product_type(
    resource_id: UUID,
    payload: ProductTypeUpdate,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.product_type.manage"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> ProductTypeResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.update_product_type(
            resource_id, _expected_version(if_match), payload.model_dump(exclude_unset=True)
        )
    except CatalogPolicyError as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, ProductTypeResponse)


@router.post("/product-types/{resource_id}/archive", response_model=ProductTypeResponse)
async def archive_product_type(
    resource_id: UUID,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.product_type.manage"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> ProductTypeResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.archive_product_type(resource_id, _expected_version(if_match))
    except CatalogPolicyError as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, ProductTypeResponse)


@router.get("/brands", response_model=BrandPage)
async def list_brands(
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.brand.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
    status: str | None = None,
) -> BrandPage:
    rows, has_more = await SqlAlchemyCatalogRepository(db).list_resources(
        "brand", ctx.tenant_id, limit=limit, cursor=_cursor(cursor), status=status
    )
    return BrandPage(
        items=[BrandResponse.model_validate(row) for row in rows],
        next_cursor=_next_cursor(rows, has_more),
        has_more=has_more,
    )


@router.post("/brands", response_model=BrandResponse, status_code=201)
async def create_brand(
    payload: BrandCreate,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.brand.manage"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Any:
    record = await _begin_create(
        db, ctx, idempotency_key, "POST", "/api/v1/catalog/brands", payload.model_dump(mode="json")
    )
    if isinstance(record, JSONResponse):
        return record
    service, _ = _service(request, ctx, db)
    try:
        row = await service.create_brand(payload.model_dump())
        await db.flush()
        response = BrandResponse.model_validate(row)
    except (CatalogPolicyError, IntegrityError, ValueError) as exc:
        await _creation_failure(db, record, exc)
    return await _finish_create(db, record, response)


@router.get("/brands/{resource_id}", response_model=BrandResponse)
async def get_brand(
    resource_id: UUID,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.brand.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> BrandResponse:
    row = await SqlAlchemyCatalogRepository(db).get_brand(ctx.tenant_id, resource_id)
    if row is None:
        raise HTTPException(404, "Brand not found")
    return BrandResponse.model_validate(row)


@router.patch("/brands/{resource_id}", response_model=BrandResponse)
async def update_brand(
    resource_id: UUID,
    payload: BrandUpdate,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.brand.manage"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> BrandResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.update_brand(resource_id, _expected_version(if_match), payload.model_dump(exclude_unset=True))
    except CatalogPolicyError as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, BrandResponse)


@router.post("/brands/{resource_id}/archive", response_model=BrandResponse)
async def archive_brand(
    resource_id: UUID,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.brand.manage"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> BrandResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.archive_brand(resource_id, _expected_version(if_match))
    except CatalogPolicyError as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, BrandResponse)


@router.get("/products", response_model=ProductPage)
async def list_products(
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.product.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
    status: str | None = None,
    product_type: UUID | None = None,
    brand: UUID | None = None,
    store: UUID | None = None,
    search: Annotated[str | None, Query(max_length=160)] = None,
) -> ProductPage:
    repository = SqlAlchemyCatalogRepository(db)
    rows, has_more = await repository.list_products(
        ctx.tenant_id,
        limit=limit,
        cursor=_cursor(cursor),
        status=status,
        product_type_id=product_type,
        brand_id=brand,
        store_id=store,
        search=search,
    )
    items: list[ProductSummary] = []
    for row in rows:
        translations = await repository.list_translations(ctx.tenant_id, row.id)
        variants, _ = await repository.list_variants(ctx.tenant_id, row.id, limit=100, cursor=None)
        default = next((variant for variant in variants if variant.is_default), None)
        items.append(
            ProductSummary(
                **ProductResponse.model_validate(row).model_dump(),
                name=translations[0].name if translations else None,
                default_sku=default.sku if default else None,
            )
        )
    return ProductPage(items=items, next_cursor=_next_cursor(rows, has_more), has_more=has_more)


@router.post("/products", response_model=ProductDetail, status_code=201)
async def create_product(
    payload: ProductCreate,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.product.create"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Any:
    record = await _begin_create(
        db, ctx, idempotency_key, "POST", "/api/v1/catalog/products", payload.model_dump(mode="json")
    )
    if isinstance(record, JSONResponse):
        return record
    service, repository = _service(request, ctx, db)
    try:
        product, _ = await service.create_product(payload.model_dump())
        await db.flush()
        response = await _product_detail(repository, product)
    except (CatalogPolicyError, IntegrityError, ValueError) as exc:
        await _creation_failure(db, record, exc)
    return await _finish_create(db, record, response)


@router.get("/products/{product_id}", response_model=ProductDetail)
async def get_product(
    product_id: UUID,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.product.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> ProductDetail:
    repository = SqlAlchemyCatalogRepository(db)
    row = await repository.get_product(ctx.tenant_id, product_id)
    if row is None:
        raise HTTPException(404, "Product not found")
    return await _product_detail(repository, row)


@router.patch("/products/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: UUID,
    payload: ProductUpdate,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.product.update"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> ProductResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.update_product(product_id, _expected_version(if_match), payload.model_dump(exclude_unset=True))
    except CatalogPolicyError as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, ProductResponse)


@router.post("/products/{product_id}/activate", response_model=ProductResponse)
async def activate_product(
    product_id: UUID,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.product.update"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> ProductResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.activate_product(product_id, _expected_version(if_match))
    except CatalogPolicyError as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, ProductResponse)


@router.post("/products/{product_id}/archive", response_model=ProductResponse)
async def archive_product(
    product_id: UUID,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.product.archive"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> ProductResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.archive_product(product_id, _expected_version(if_match))
    except CatalogPolicyError as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, ProductResponse)


@router.get("/products/{product_id}/variants", response_model=VariantPage)
async def list_variants(
    product_id: UUID,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.variant.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> VariantPage:
    repository = SqlAlchemyCatalogRepository(db)
    if await repository.get_product(ctx.tenant_id, product_id) is None:
        raise HTTPException(404, "Product not found")
    rows, has_more = await repository.list_variants(
        ctx.tenant_id, product_id, limit=limit, cursor=_cursor(cursor)
    )
    return VariantPage(
        items=[VariantResponse.model_validate(row) for row in rows],
        next_cursor=_next_cursor(rows, has_more),
        has_more=has_more,
    )


@router.post("/products/{product_id}/variants", response_model=VariantResponse, status_code=201)
async def create_variant(
    product_id: UUID,
    payload: VariantCreate,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.variant.create"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Any:
    endpoint = f"/api/v1/catalog/products/{product_id}/variants"
    record = await _begin_create(db, ctx, idempotency_key, "POST", endpoint, payload.model_dump(mode="json"))
    if isinstance(record, JSONResponse):
        return record
    service, _ = _service(request, ctx, db)
    try:
        row = await service.create_variant(product_id, payload.model_dump())
        await db.flush()
        response = VariantResponse.model_validate(row)
    except (CatalogPolicyError, IntegrityError, ValueError) as exc:
        await _creation_failure(db, record, exc)
    return await _finish_create(db, record, response)


@router.get("/variants/{variant_id}", response_model=VariantResponse)
async def get_variant(
    variant_id: UUID,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.variant.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> VariantResponse:
    row = await SqlAlchemyCatalogRepository(db).get_variant(ctx.tenant_id, variant_id)
    if row is None:
        raise HTTPException(404, "Variant not found")
    return VariantResponse.model_validate(row)


@router.patch("/variants/{variant_id}", response_model=VariantResponse)
async def update_variant(
    variant_id: UUID,
    payload: VariantUpdate,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.variant.update"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> VariantResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.update_variant(variant_id, _expected_version(if_match), payload.model_dump(exclude_unset=True))
    except CatalogPolicyError as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, VariantResponse)


@router.post("/variants/{variant_id}/archive", response_model=VariantResponse)
async def archive_variant(
    variant_id: UUID,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.variant.archive"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> VariantResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.archive_variant(variant_id, _expected_version(if_match))
    except CatalogPolicyError as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, VariantResponse)


@router.get("/variants/{variant_id}/identifiers", response_model=list[IdentifierResponse])
async def list_identifiers(
    variant_id: UUID,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.variant.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[IdentifierResponse]:
    repository = SqlAlchemyCatalogRepository(db)
    if await repository.get_variant(ctx.tenant_id, variant_id) is None:
        raise HTTPException(404, "Variant not found")
    return [
        IdentifierResponse.model_validate(row)
        for row in await repository.list_identifiers(ctx.tenant_id, variant_id)
    ]


@router.post("/variants/{variant_id}/identifiers", response_model=IdentifierResponse, status_code=201)
async def create_identifier(
    variant_id: UUID,
    payload: IdentifierCreate,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.variant.update"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Any:
    endpoint = f"/api/v1/catalog/variants/{variant_id}/identifiers"
    record = await _begin_create(db, ctx, idempotency_key, "POST", endpoint, payload.model_dump(mode="json"))
    if isinstance(record, JSONResponse):
        return record
    service, _ = _service(request, ctx, db)
    try:
        row = await service.create_identifier(variant_id, payload.model_dump())
        await db.flush()
        response = IdentifierResponse.model_validate(row)
    except (CatalogPolicyError, IntegrityError, ValueError) as exc:
        await _creation_failure(db, record, exc)
    return await _finish_create(db, record, response)


@router.delete("/identifiers/{identifier_id}", status_code=204)
async def archive_identifier(
    identifier_id: UUID,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.variant.update"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    service, _ = _service(request, ctx, db)
    try:
        await service.archive_identifier(identifier_id)
        await db.commit()
    except CatalogPolicyError as exc:
        await _mutation_failure(db, exc)
    return Response(status_code=204)


@router.get("/products/{product_id}/translations", response_model=list[ProductTranslationResponse])
async def list_translations(
    product_id: UUID,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.product.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[ProductTranslationResponse]:
    repository = SqlAlchemyCatalogRepository(db)
    if await repository.get_product(ctx.tenant_id, product_id) is None:
        raise HTTPException(404, "Product not found")
    return [
        ProductTranslationResponse.model_validate(row)
        for row in await repository.list_translations(ctx.tenant_id, product_id)
    ]


@router.put("/products/{product_id}/translations/{locale}", response_model=ProductTranslationResponse)
async def upsert_translation(
    product_id: UUID,
    locale: str,
    payload: ProductTranslationPut,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.product.update"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> ProductTranslationResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.upsert_translation(
            product_id, locale, _expected_version(if_match), payload.model_dump()
        )
    except (CatalogPolicyError, ValueError) as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, ProductTranslationResponse)


@router.put("/products/{product_id}/seo/{locale}", response_model=ProductSeoResponse)
async def upsert_seo(
    product_id: UUID,
    locale: str,
    payload: ProductSeoPut,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.product.update"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> ProductSeoResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.upsert_seo(product_id, locale, _expected_version(if_match), payload.model_dump())
    except (CatalogPolicyError, ValueError) as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, ProductSeoResponse)


@router.get("/taxonomies", response_model=TaxonomyPage)
async def list_taxonomies(
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.taxonomy.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
    status: str | None = None,
) -> TaxonomyPage:
    rows, has_more = await SqlAlchemyCatalogRepository(db).list_resources(
        "taxonomy", ctx.tenant_id, limit=limit, cursor=_cursor(cursor), status=status
    )
    return TaxonomyPage(
        items=[TaxonomyResponse.model_validate(row) for row in rows],
        next_cursor=_next_cursor(rows, has_more),
        has_more=has_more,
    )


@router.post("/taxonomies", response_model=TaxonomyResponse, status_code=201)
async def create_taxonomy(
    payload: TaxonomyCreate,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.taxonomy.manage"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Any:
    record = await _begin_create(
        db, ctx, idempotency_key, "POST", "/api/v1/catalog/taxonomies", payload.model_dump(mode="json")
    )
    if isinstance(record, JSONResponse):
        return record
    service, _ = _service(request, ctx, db)
    try:
        row = await service.create_taxonomy(payload.model_dump())
        await db.flush()
        response = TaxonomyResponse.model_validate(row)
    except (CatalogPolicyError, IntegrityError, ValueError) as exc:
        await _creation_failure(db, record, exc)
    return await _finish_create(db, record, response)


@router.get("/taxonomies/{taxonomy_id}/categories", response_model=list[CategoryResponse])
async def list_categories(
    taxonomy_id: UUID,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.category.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[CategoryResponse]:
    repository = SqlAlchemyCatalogRepository(db)
    if await repository.get_taxonomy(ctx.tenant_id, taxonomy_id) is None:
        raise HTTPException(404, "Taxonomy not found")
    return [
        CategoryResponse.model_validate(row)
        for row in await repository.list_categories(ctx.tenant_id, taxonomy_id)
    ]


@router.post("/taxonomies/{taxonomy_id}/categories", response_model=CategoryResponse, status_code=201)
async def create_category(
    taxonomy_id: UUID,
    payload: CategoryCreate,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.category.manage"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Any:
    endpoint = f"/api/v1/catalog/taxonomies/{taxonomy_id}/categories"
    record = await _begin_create(db, ctx, idempotency_key, "POST", endpoint, payload.model_dump(mode="json"))
    if isinstance(record, JSONResponse):
        return record
    service, _ = _service(request, ctx, db)
    try:
        row = await service.create_category(taxonomy_id, payload.model_dump())
        await db.flush()
        response = CategoryResponse.model_validate(row)
    except (CatalogPolicyError, IntegrityError, ValueError) as exc:
        await _creation_failure(db, record, exc)
    return await _finish_create(db, record, response)


@router.patch("/categories/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: UUID,
    payload: CategoryUpdate,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.category.manage"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> CategoryResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.update_category(
            category_id, _expected_version(if_match), payload.model_dump(exclude_unset=True)
        )
    except CatalogPolicyError as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, CategoryResponse)


@router.post("/categories/{category_id}/move", response_model=CategoryResponse)
async def move_category(
    category_id: UUID,
    payload: CategoryMove,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.category.manage"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> CategoryResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.move_category(
            category_id, _expected_version(if_match), payload.parent_id, payload.position
        )
    except CatalogPolicyError as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, CategoryResponse)


@router.post("/categories/{category_id}/archive", response_model=CategoryResponse)
async def archive_category(
    category_id: UUID,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.category.manage"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> CategoryResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.archive_category(category_id, _expected_version(if_match))
    except CatalogPolicyError as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, CategoryResponse)


@router.get("/products/{product_id}/categories", response_model=list[ProductCategoryResponse])
async def list_product_categories(
    product_id: UUID,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.assignment.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[ProductCategoryResponse]:
    repository = SqlAlchemyCatalogRepository(db)
    if await repository.get_product(ctx.tenant_id, product_id) is None:
        raise HTTPException(404, "Product not found")
    return [
        ProductCategoryResponse.model_validate(row)
        for row in await repository.list_product_categories(ctx.tenant_id, product_id)
    ]


@router.put("/products/{product_id}/categories", response_model=list[ProductCategoryResponse])
async def assign_product_categories(
    product_id: UUID,
    payload: ProductCategoriesPut,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.assignment.manage"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> list[ProductCategoryResponse]:
    service, _ = _service(request, ctx, db)
    try:
        rows = await service.assign_categories(
            product_id,
            _expected_version(if_match),
            [item.model_dump() for item in payload.assignments],
        )
        await db.commit()
    except (CatalogPolicyError, IntegrityError) as exc:
        await _mutation_failure(db, exc)
    return [ProductCategoryResponse.model_validate(row) for row in rows]


@router.get("/products/{product_id}/stores", response_model=list[ProductStoreResponse])
async def list_product_stores(
    product_id: UUID,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.assignment.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[ProductStoreResponse]:
    repository = SqlAlchemyCatalogRepository(db)
    if await repository.get_product(ctx.tenant_id, product_id) is None:
        raise HTTPException(404, "Product not found")
    return [
        ProductStoreResponse.model_validate(row)
        for row in await repository.list_product_stores(ctx.tenant_id, product_id)
    ]


@router.put("/products/{product_id}/stores/{store_id}", response_model=ProductStoreResponse)
async def assign_product_store(
    product_id: UUID,
    store_id: UUID,
    payload: ProductStorePut,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.assignment.manage"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Any:
    await set_store_context(db, store_id)
    endpoint = f"/api/v1/catalog/products/{product_id}/stores/{store_id}"
    record = await _begin_create(db, ctx, idempotency_key, "PUT", endpoint, payload.model_dump(mode="json"))
    if isinstance(record, JSONResponse):
        return record
    service, _ = _service(request, ctx, db)
    try:
        row = await service.assign_store(product_id, store_id, payload.model_dump())
        await db.flush()
        response = ProductStoreResponse.model_validate(row)
    except (CatalogPolicyError, IntegrityError) as exc:
        await _creation_failure(db, record, exc)
    return await _finish_create(db, record, response, code=200)


@router.delete("/products/{product_id}/stores/{store_id}", response_model=ProductStoreResponse)
async def unassign_product_store(
    product_id: UUID,
    store_id: UUID,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.assignment.manage"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> ProductStoreResponse:
    await set_store_context(db, store_id)
    service, _ = _service(request, ctx, db)
    try:
        row = await service.unassign_store(product_id, store_id, _expected_version(if_match))
    except CatalogPolicyError as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, ProductStoreResponse)


@router.get("/usage", response_model=CatalogUsageResponse)
async def catalog_usage(
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.product.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> CatalogUsageResponse:
    repository = SqlAlchemyCatalogRepository(db)
    return CatalogUsageResponse(
        products=await repository.count_products(ctx.tenant_id),
        product_limit=await repository.entitlement_limit(ctx.tenant_id, "catalog.products.max"),
    )

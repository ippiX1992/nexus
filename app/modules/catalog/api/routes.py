from typing import Annotated, Any, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_permission
from app.application.authorization import TenantContext
from app.infrastructure.database import get_session
from app.infrastructure.tenant_context import set_store_context
from app.modules.catalog.api.schemas import (
    AttributeCreate,
    AttributeGroupCreate,
    AttributeGroupPage,
    AttributeGroupResponse,
    AttributeGroupTranslationPut,
    AttributeGroupTranslationResponse,
    AttributeGroupUpdate,
    AttributeOptionCreate,
    AttributeOptionResponse,
    AttributeOptionTranslationPut,
    AttributeOptionTranslationResponse,
    AttributeOptionUpdate,
    AttributePage,
    AttributeResponse,
    AttributeTranslationPut,
    AttributeTranslationResponse,
    AttributeUpdate,
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
    OptionCreate,
    OptionPage,
    OptionResponse,
    OptionTranslationPut,
    OptionTranslationResponse,
    OptionUpdate,
    OptionValueCreate,
    OptionValueResponse,
    OptionValueTranslationPut,
    OptionValueTranslationResponse,
    OptionValueUpdate,
    ProductAttributeValueOptionResponse,
    ProductAttributeValueResponse,
    ProductAttributeValuesPut,
    ProductCategoriesPut,
    ProductCategoryResponse,
    ProductCreate,
    ProductDetail,
    ProductOptionResponse,
    ProductOptionsPut,
    ProductPage,
    ProductResponse,
    ProductSeoPut,
    ProductSeoResponse,
    ProductStorePut,
    ProductStoreResponse,
    ProductSummary,
    ProductTranslationPut,
    ProductTranslationResponse,
    ProductTypeAttributeResponse,
    ProductTypeAttributesPut,
    ProductTypeCreate,
    ProductTypePage,
    ProductTypeResponse,
    ProductTypeUpdate,
    ProductUpdate,
    TaxonomyCreate,
    TaxonomyPage,
    TaxonomyResponse,
    VariantCreate,
    VariantGenerationAccepted,
    VariantGenerationPreviewResponse,
    VariantOptionValueResponse,
    VariantPage,
    VariantResponse,
    VariantUpdate,
)
from app.modules.catalog.application.generation import create_generation_operation
from app.modules.catalog.application.services import CatalogActor, CatalogService
from app.modules.catalog.domain.policies import (
    CatalogAttributesQuotaExceeded,
    CatalogConflict,
    CatalogNotFound,
    CatalogOptionsQuotaExceeded,
    CatalogPolicyError,
    CatalogQuotaExceeded,
    CatalogVersionConflict,
    CategoryCycle,
    ensure_generation_within_limits,
    ensure_product_mutable,
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
    if isinstance(exc, (CatalogOptionsQuotaExceeded, CatalogAttributesQuotaExceeded)):
        # M3.1/M3.2 convention: quota errors are 409, never 429 (reserved for
        # transport rate limiting) -- checked before the generic
        # CatalogQuotaExceeded branch, which M3.0's own entitlements still use
        # and are tested against as 429.
        return HTTPException(409, str(exc))
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
        # Primary category name (for the admin list column).
        category = (
            await db.execute(
                text(
                    "SELECT c.name FROM catalog_product_categories pc "
                    "JOIN catalog_categories c ON c.id = pc.category_id AND c.tenant_id = pc.tenant_id "
                    "WHERE pc.product_id = :pid AND pc.tenant_id = :tenant "
                    "ORDER BY pc.is_primary DESC NULLS LAST LIMIT 1"
                ),
                {"pid": row.id, "tenant": ctx.tenant_id},
            )
        ).scalar()
        # Available stock across the default variant's locations.
        stock = None
        if default is not None:
            stock = (
                await db.execute(
                    text("SELECT COALESCE(SUM(available), 0) FROM inventory_stock_levels WHERE variant_id = :vid AND tenant_id = :tenant"),
                    {"vid": default.id, "tenant": ctx.tenant_id},
                )
            ).scalar()
        items.append(
            ProductSummary(
                **ProductResponse.model_validate(row).model_dump(),
                name=translations[0].name if translations else None,
                default_sku=default.sku if default else None,
                category=category,
                stock=int(stock) if stock is not None else None,
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
        if payload.option_value_ids:
            # Assigning a combination emits an extra UPDATE on this same row
            # (combination_fingerprint), which expires onupdate columns like
            # updated_at -- refresh before validating, same as _finish_mutation
            # already does for PATCH/archive endpoints.
            await db.refresh(row)
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


@router.get("/variants/{variant_id}/options", response_model=list[VariantOptionValueResponse])
async def list_variant_option_values(
    variant_id: UUID,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.variant.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[VariantOptionValueResponse]:
    repository = SqlAlchemyCatalogRepository(db)
    if await repository.get_variant(ctx.tenant_id, variant_id) is None:
        raise HTTPException(404, "Variant not found")
    return [
        VariantOptionValueResponse.model_validate(row)
        for row in await repository.list_variant_option_values(ctx.tenant_id, variant_id)
    ]


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


@router.get("/variant-labels")
async def variant_labels(
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.product.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[dict]:
    # One query for every default variant's human label, so admin screens that key
    # on variant id (inventory, pricing) don't fall back to raw UUIDs or fan out
    # into a detail request per product.
    rows = (
        await db.execute(
            text(
                """
                SELECT v.id::text AS variant_id, COALESCE(t.name, p.code, v.sku) AS name, v.sku AS sku
                FROM catalog_product_variants v
                JOIN catalog_products p ON p.id = v.product_id AND p.tenant_id = v.tenant_id
                LEFT JOIN catalog_product_translations t
                  ON t.product_id = p.id AND t.tenant_id = p.tenant_id AND t.locale = 'es-EC'
                WHERE v.is_default AND v.archived_at IS NULL
                """
            )
        )
    ).all()
    return [{"variant_id": row.variant_id, "label": f"{row.name} · {row.sku}"} for row in rows]


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
    rows = await repository.list_categories(ctx.tenant_id, taxonomy_id)
    counts = {
        str(cid): int(n)
        for cid, n in (
            await db.execute(
                text("SELECT category_id, COUNT(*) FROM catalog_product_categories WHERE tenant_id = :tenant GROUP BY category_id"),
                {"tenant": str(ctx.tenant_id)},
            )
        ).all()
    }
    result: list[CategoryResponse] = []
    for row in rows:
        resp = CategoryResponse.model_validate(row)
        resp.product_count = counts.get(str(row.id), 0)
        result.append(resp)
    return result


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


# --- M3.1 Options and Variant Combinations ---


@router.get("/options", response_model=OptionPage)
async def list_options(
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.option.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
    status: str | None = None,
) -> OptionPage:
    rows, has_more = await SqlAlchemyCatalogRepository(db).list_resources(
        "option", ctx.tenant_id, limit=limit, cursor=_cursor(cursor), status=status
    )
    return OptionPage(
        items=[OptionResponse.model_validate(row) for row in rows],
        next_cursor=_next_cursor(rows, has_more),
        has_more=has_more,
    )


@router.post("/options", response_model=OptionResponse, status_code=201)
async def create_option(
    payload: OptionCreate,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.option.create"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Any:
    record = await _begin_create(db, ctx, idempotency_key, "POST", "/api/v1/catalog/options", payload.model_dump(mode="json"))
    if isinstance(record, JSONResponse):
        return record
    service, _ = _service(request, ctx, db)
    try:
        row = await service.create_option(payload.model_dump())
        await db.flush()
        response = OptionResponse.model_validate(row)
    except (CatalogPolicyError, IntegrityError, ValueError) as exc:
        await _creation_failure(db, record, exc)
    return await _finish_create(db, record, response)


@router.get("/options/{resource_id}", response_model=OptionResponse)
async def get_option(
    resource_id: UUID,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.option.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> OptionResponse:
    row = await SqlAlchemyCatalogRepository(db).get_option(ctx.tenant_id, resource_id)
    if row is None:
        raise HTTPException(404, "Option not found")
    return OptionResponse.model_validate(row)


@router.patch("/options/{resource_id}", response_model=OptionResponse)
async def update_option(
    resource_id: UUID,
    payload: OptionUpdate,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.option.update"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> OptionResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.update_option(resource_id, _expected_version(if_match), payload.model_dump(exclude_unset=True))
    except CatalogPolicyError as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, OptionResponse)


@router.post("/options/{resource_id}/archive", response_model=OptionResponse)
async def archive_option(
    resource_id: UUID,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.option.archive"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> OptionResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.archive_option(resource_id, _expected_version(if_match))
    except CatalogPolicyError as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, OptionResponse)


@router.put("/options/{resource_id}/translations/{locale}", response_model=OptionTranslationResponse)
async def upsert_option_translation(
    resource_id: UUID,
    locale: str,
    payload: OptionTranslationPut,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.option.update"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> OptionTranslationResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.upsert_option_translation(resource_id, locale, payload.model_dump())
        await db.commit()
    except (CatalogPolicyError, ValueError) as exc:
        await _mutation_failure(db, exc)
    return OptionTranslationResponse.model_validate(row)


@router.get("/options/{resource_id}/values", response_model=list[OptionValueResponse])
async def list_option_values(
    resource_id: UUID,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.option_value.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[OptionValueResponse]:
    repository = SqlAlchemyCatalogRepository(db)
    if await repository.get_option(ctx.tenant_id, resource_id) is None:
        raise HTTPException(404, "Option not found")
    return [OptionValueResponse.model_validate(row) for row in await repository.list_option_values(ctx.tenant_id, resource_id)]


@router.post("/options/{resource_id}/values", response_model=OptionValueResponse, status_code=201)
async def create_option_value(
    resource_id: UUID,
    payload: OptionValueCreate,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.option_value.create"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Any:
    endpoint = f"/api/v1/catalog/options/{resource_id}/values"
    record = await _begin_create(db, ctx, idempotency_key, "POST", endpoint, payload.model_dump(mode="json"))
    if isinstance(record, JSONResponse):
        return record
    service, _ = _service(request, ctx, db)
    try:
        row = await service.create_option_value(resource_id, payload.model_dump())
        await db.flush()
        response = OptionValueResponse.model_validate(row)
    except (CatalogPolicyError, IntegrityError, ValueError) as exc:
        await _creation_failure(db, record, exc)
    return await _finish_create(db, record, response)


@router.patch("/option-values/{resource_id}", response_model=OptionValueResponse)
async def update_option_value(
    resource_id: UUID,
    payload: OptionValueUpdate,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.option_value.update"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> OptionValueResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.update_option_value(
            resource_id, _expected_version(if_match), payload.model_dump(exclude_unset=True)
        )
    except (CatalogPolicyError, ValueError) as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, OptionValueResponse)


@router.post("/option-values/{resource_id}/archive", response_model=OptionValueResponse)
async def archive_option_value(
    resource_id: UUID,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.option_value.archive"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> OptionValueResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.archive_option_value(resource_id, _expected_version(if_match))
    except CatalogPolicyError as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, OptionValueResponse)


@router.put("/option-values/{resource_id}/translations/{locale}", response_model=OptionValueTranslationResponse)
async def upsert_option_value_translation(
    resource_id: UUID,
    locale: str,
    payload: OptionValueTranslationPut,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.option_value.update"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> OptionValueTranslationResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.upsert_option_value_translation(resource_id, locale, payload.model_dump())
        await db.commit()
    except (CatalogPolicyError, ValueError) as exc:
        await _mutation_failure(db, exc)
    return OptionValueTranslationResponse.model_validate(row)


@router.get("/products/{product_id}/options", response_model=list[ProductOptionResponse])
async def list_product_options(
    product_id: UUID,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.product_option.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[ProductOptionResponse]:
    repository = SqlAlchemyCatalogRepository(db)
    if await repository.get_product(ctx.tenant_id, product_id) is None:
        raise HTTPException(404, "Product not found")
    return [
        ProductOptionResponse.model_validate(row)
        for row in await repository.list_product_options(ctx.tenant_id, product_id)
    ]


@router.put("/products/{product_id}/options", response_model=list[ProductOptionResponse])
async def set_product_options(
    product_id: UUID,
    payload: ProductOptionsPut,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.product_option.manage"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> list[ProductOptionResponse]:
    service, _ = _service(request, ctx, db)
    try:
        rows = await service.set_product_options(
            product_id, _expected_version(if_match), [item.model_dump() for item in payload.options]
        )
        await db.commit()
    except (CatalogPolicyError, IntegrityError) as exc:
        await _mutation_failure(db, exc)
    return [ProductOptionResponse.model_validate(row) for row in rows]


@router.post("/products/{product_id}/variant-generation/preview", response_model=VariantGenerationPreviewResponse)
async def preview_variant_generation(
    product_id: UUID,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.variant_combination.create"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    request: Request,
) -> VariantGenerationPreviewResponse:
    service, _ = _service(request, ctx, db)
    try:
        preview = await service.preview_variant_generation(product_id)
    except CatalogPolicyError as exc:
        raise _http_error(exc) from exc
    return VariantGenerationPreviewResponse(**preview)


@router.post("/products/{product_id}/variant-generation", response_model=VariantGenerationAccepted, status_code=202)
async def request_variant_generation(
    product_id: UUID,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.variant_combination.generate"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Any:
    endpoint = f"/api/v1/catalog/products/{product_id}/variant-generation"
    record = await _begin_create(db, ctx, idempotency_key, "POST", endpoint, {"if_match": if_match})
    if isinstance(record, JSONResponse):
        return record
    service, repository = _service(request, ctx, db)
    try:
        product = await repository.get_product(ctx.tenant_id, product_id, lock=True)
        if product is None:
            await service._missing("product", product_id)  # noqa: SLF001
        await service._version("product", product, _expected_version(if_match))  # noqa: SLF001
        ensure_product_mutable(product.status)
        preview = await service.preview_variant_generation(product_id)
        per_operation_limit = await repository.entitlement_limit(
            ctx.tenant_id, "catalog.combination_generation.max_per_operation"
        )
        ensure_generation_within_limits(preview["estimated_work"], per_operation_limit, preview["remaining_capacity"])
        operation = await create_generation_operation(
            db,
            tenant_id=ctx.tenant_id,
            actor_id=ctx.user_id,
            product_id=product_id,
            correlation_id=request.state.correlation_id,
            idempotency_key=idempotency_key,
        )
        await db.flush()
        response = VariantGenerationAccepted(operation_id=operation.id, status=operation.status)
    except (CatalogPolicyError, IntegrityError, ValueError) as exc:
        await _creation_failure(db, record, exc)
    return await _finish_create(db, record, response, code=202)


# --- M3.2 Attributes and Product Specifications ---


@router.get("/attributes", response_model=AttributePage)
async def list_attributes(
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.attribute.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
    status: str | None = None,
) -> AttributePage:
    rows, has_more = await SqlAlchemyCatalogRepository(db).list_resources(
        "attribute", ctx.tenant_id, limit=limit, cursor=_cursor(cursor), status=status
    )
    return AttributePage(
        items=[AttributeResponse.model_validate(row) for row in rows],
        next_cursor=_next_cursor(rows, has_more),
        has_more=has_more,
    )


@router.post("/attributes", response_model=AttributeResponse, status_code=201)
async def create_attribute(
    payload: AttributeCreate,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.attribute.create"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Any:
    record = await _begin_create(db, ctx, idempotency_key, "POST", "/api/v1/catalog/attributes", payload.model_dump(mode="json"))
    if isinstance(record, JSONResponse):
        return record
    service, _ = _service(request, ctx, db)
    try:
        row = await service.create_attribute(payload.model_dump())
        await db.flush()
        response = AttributeResponse.model_validate(row)
    except (CatalogPolicyError, IntegrityError, ValueError) as exc:
        await _creation_failure(db, record, exc)
    return await _finish_create(db, record, response)


@router.get("/attributes/{resource_id}", response_model=AttributeResponse)
async def get_attribute(
    resource_id: UUID,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.attribute.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> AttributeResponse:
    row = await SqlAlchemyCatalogRepository(db).get_attribute(ctx.tenant_id, resource_id)
    if row is None:
        raise HTTPException(404, "Attribute not found")
    return AttributeResponse.model_validate(row)


@router.patch("/attributes/{resource_id}", response_model=AttributeResponse)
async def update_attribute(
    resource_id: UUID,
    payload: AttributeUpdate,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.attribute.update"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> AttributeResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.update_attribute(resource_id, _expected_version(if_match), payload.model_dump(exclude_unset=True))
    except CatalogPolicyError as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, AttributeResponse)


@router.post("/attributes/{resource_id}/archive", response_model=AttributeResponse)
async def archive_attribute(
    resource_id: UUID,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.attribute.archive"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> AttributeResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.archive_attribute(resource_id, _expected_version(if_match))
    except CatalogPolicyError as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, AttributeResponse)


@router.post("/attributes/{resource_id}/restore", response_model=AttributeResponse)
async def restore_attribute(
    resource_id: UUID,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.attribute.archive"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> AttributeResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.restore_attribute(resource_id, _expected_version(if_match))
    except CatalogPolicyError as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, AttributeResponse)


@router.put("/attributes/{resource_id}/translations/{locale}", response_model=AttributeTranslationResponse)
async def upsert_attribute_translation(
    resource_id: UUID,
    locale: str,
    payload: AttributeTranslationPut,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.attribute.update"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> AttributeTranslationResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.upsert_attribute_translation(resource_id, locale, payload.model_dump())
        await db.commit()
    except (CatalogPolicyError, ValueError) as exc:
        await _mutation_failure(db, exc)
    return AttributeTranslationResponse.model_validate(row)


@router.get("/attributes/{resource_id}/options", response_model=list[AttributeOptionResponse])
async def list_attribute_options(
    resource_id: UUID,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.attribute_option.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[AttributeOptionResponse]:
    repository = SqlAlchemyCatalogRepository(db)
    if await repository.get_attribute(ctx.tenant_id, resource_id) is None:
        raise HTTPException(404, "Attribute not found")
    return [
        AttributeOptionResponse.model_validate(row)
        for row in await repository.list_attribute_options(ctx.tenant_id, resource_id)
    ]


@router.post("/attributes/{resource_id}/options", response_model=AttributeOptionResponse, status_code=201)
async def create_attribute_option(
    resource_id: UUID,
    payload: AttributeOptionCreate,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.attribute_option.create"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Any:
    endpoint = f"/api/v1/catalog/attributes/{resource_id}/options"
    record = await _begin_create(db, ctx, idempotency_key, "POST", endpoint, payload.model_dump(mode="json"))
    if isinstance(record, JSONResponse):
        return record
    service, _ = _service(request, ctx, db)
    try:
        row = await service.create_attribute_option(resource_id, payload.model_dump())
        await db.flush()
        response = AttributeOptionResponse.model_validate(row)
    except (CatalogPolicyError, IntegrityError, ValueError) as exc:
        await _creation_failure(db, record, exc)
    return await _finish_create(db, record, response)


@router.patch("/attribute-options/{resource_id}", response_model=AttributeOptionResponse)
async def update_attribute_option(
    resource_id: UUID,
    payload: AttributeOptionUpdate,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.attribute_option.update"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> AttributeOptionResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.update_attribute_option(resource_id, _expected_version(if_match), payload.model_dump(exclude_unset=True))
    except CatalogPolicyError as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, AttributeOptionResponse)


@router.post("/attribute-options/{resource_id}/archive", response_model=AttributeOptionResponse)
async def archive_attribute_option(
    resource_id: UUID,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.attribute_option.archive"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> AttributeOptionResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.archive_attribute_option(resource_id, _expected_version(if_match))
    except CatalogPolicyError as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, AttributeOptionResponse)


@router.put("/attribute-options/{resource_id}/translations/{locale}", response_model=AttributeOptionTranslationResponse)
async def upsert_attribute_option_translation(
    resource_id: UUID,
    locale: str,
    payload: AttributeOptionTranslationPut,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.attribute_option.update"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> AttributeOptionTranslationResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.upsert_attribute_option_translation(resource_id, locale, payload.model_dump())
        await db.commit()
    except (CatalogPolicyError, ValueError) as exc:
        await _mutation_failure(db, exc)
    return AttributeOptionTranslationResponse.model_validate(row)


@router.get("/attribute-groups", response_model=AttributeGroupPage)
async def list_attribute_groups(
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.attribute_group.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
    status: str | None = None,
) -> AttributeGroupPage:
    rows, has_more = await SqlAlchemyCatalogRepository(db).list_resources(
        "attribute_group", ctx.tenant_id, limit=limit, cursor=_cursor(cursor), status=status
    )
    return AttributeGroupPage(
        items=[AttributeGroupResponse.model_validate(row) for row in rows],
        next_cursor=_next_cursor(rows, has_more),
        has_more=has_more,
    )


@router.post("/attribute-groups", response_model=AttributeGroupResponse, status_code=201)
async def create_attribute_group(
    payload: AttributeGroupCreate,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.attribute_group.create"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Any:
    record = await _begin_create(db, ctx, idempotency_key, "POST", "/api/v1/catalog/attribute-groups", payload.model_dump(mode="json"))
    if isinstance(record, JSONResponse):
        return record
    service, _ = _service(request, ctx, db)
    try:
        row = await service.create_attribute_group(payload.model_dump())
        await db.flush()
        response = AttributeGroupResponse.model_validate(row)
    except (CatalogPolicyError, IntegrityError, ValueError) as exc:
        await _creation_failure(db, record, exc)
    return await _finish_create(db, record, response)


@router.get("/attribute-groups/{resource_id}", response_model=AttributeGroupResponse)
async def get_attribute_group(
    resource_id: UUID,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.attribute_group.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> AttributeGroupResponse:
    row = await SqlAlchemyCatalogRepository(db).get_attribute_group(ctx.tenant_id, resource_id)
    if row is None:
        raise HTTPException(404, "Attribute Group not found")
    return AttributeGroupResponse.model_validate(row)


@router.patch("/attribute-groups/{resource_id}", response_model=AttributeGroupResponse)
async def update_attribute_group(
    resource_id: UUID,
    payload: AttributeGroupUpdate,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.attribute_group.update"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> AttributeGroupResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.update_attribute_group(resource_id, _expected_version(if_match), payload.model_dump(exclude_unset=True))
    except CatalogPolicyError as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, AttributeGroupResponse)


@router.post("/attribute-groups/{resource_id}/archive", response_model=AttributeGroupResponse)
async def archive_attribute_group(
    resource_id: UUID,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.attribute_group.archive"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> AttributeGroupResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.archive_attribute_group(resource_id, _expected_version(if_match))
    except CatalogPolicyError as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, AttributeGroupResponse)


@router.post("/attribute-groups/{resource_id}/restore", response_model=AttributeGroupResponse)
async def restore_attribute_group(
    resource_id: UUID,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.attribute_group.archive"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> AttributeGroupResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.restore_attribute_group(resource_id, _expected_version(if_match))
    except CatalogPolicyError as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, AttributeGroupResponse)


@router.put("/attribute-groups/{resource_id}/translations/{locale}", response_model=AttributeGroupTranslationResponse)
async def upsert_attribute_group_translation(
    resource_id: UUID,
    locale: str,
    payload: AttributeGroupTranslationPut,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.attribute_group.update"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> AttributeGroupTranslationResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.upsert_attribute_group_translation(resource_id, locale, payload.model_dump())
        await db.commit()
    except (CatalogPolicyError, ValueError) as exc:
        await _mutation_failure(db, exc)
    return AttributeGroupTranslationResponse.model_validate(row)


@router.get("/product-types/{product_type_id}/attributes", response_model=list[ProductTypeAttributeResponse])
async def list_product_type_attributes(
    product_type_id: UUID,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.product_type_attribute.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[ProductTypeAttributeResponse]:
    repository = SqlAlchemyCatalogRepository(db)
    if await repository.get_product_type(ctx.tenant_id, product_type_id) is None:
        raise HTTPException(404, "Product Type not found")
    return [
        ProductTypeAttributeResponse.model_validate(row)
        for row in await repository.list_product_type_attributes(ctx.tenant_id, product_type_id)
    ]


@router.put("/product-types/{product_type_id}/attributes", response_model=list[ProductTypeAttributeResponse])
async def set_product_type_attributes(
    product_type_id: UUID,
    payload: ProductTypeAttributesPut,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.product_type_attribute.manage"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> list[ProductTypeAttributeResponse]:
    service, _ = _service(request, ctx, db)
    try:
        rows = await service.set_product_type_attributes(
            product_type_id, _expected_version(if_match), [item.model_dump() for item in payload.attributes]
        )
        await db.commit()
    except (CatalogPolicyError, IntegrityError) as exc:
        await _mutation_failure(db, exc)
    return [ProductTypeAttributeResponse.model_validate(row) for row in rows]


@router.get("/products/{product_id}/attributes", response_model=list[ProductAttributeValueResponse])
async def list_product_attribute_values(
    product_id: UUID,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.product_attribute_value.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[ProductAttributeValueResponse]:
    repository = SqlAlchemyCatalogRepository(db)
    if await repository.get_product(ctx.tenant_id, product_id) is None:
        raise HTTPException(404, "Product not found")
    return [
        ProductAttributeValueResponse.model_validate(row)
        for row in await repository.list_product_attribute_values(ctx.tenant_id, product_id)
    ]


@router.get("/products/{product_id}/attribute-value-options", response_model=list[ProductAttributeValueOptionResponse])
async def list_product_attribute_value_options(
    product_id: UUID,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.product_attribute_value.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[ProductAttributeValueOptionResponse]:
    repository = SqlAlchemyCatalogRepository(db)
    if await repository.get_product(ctx.tenant_id, product_id) is None:
        raise HTTPException(404, "Product not found")
    return [
        ProductAttributeValueOptionResponse.model_validate(row)
        for row in await repository.list_product_attribute_value_options(ctx.tenant_id, product_id)
    ]


@router.put("/products/{product_id}/attributes", response_model=list[ProductAttributeValueResponse])
async def set_product_attribute_values(
    product_id: UUID,
    payload: ProductAttributeValuesPut,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("catalog.product_attribute_value.manage"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> list[ProductAttributeValueResponse]:
    service, _ = _service(request, ctx, db)
    try:
        rows = await service.set_product_attribute_values(
            product_id, _expected_version(if_match), [item.model_dump() for item in payload.values]
        )
        await db.commit()
    except (CatalogPolicyError, IntegrityError, ValueError) as exc:
        await _mutation_failure(db, exc)
    return [ProductAttributeValueResponse.model_validate(row) for row in rows]

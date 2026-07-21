from datetime import datetime
from typing import Annotated, Any, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_permission
from app.application.authorization import TenantContext
from app.infrastructure.database import get_session
from app.modules.catalog.domain.values import decode_cursor, encode_cursor
from app.modules.platform.application.idempotency import (
    IdempotencyConflict,
    IdempotencyInProgress,
    begin_idempotent,
    complete_idempotent,
)
from app.modules.pricing.api.schemas import (
    AssignmentCreate,
    AssignmentPage,
    AssignmentResponse,
    OverrideCreate,
    OverridePage,
    OverrideResponse,
    PriceHistoryPage,
    PriceHistoryResponse,
    PriceListCreate,
    PriceListEntryPage,
    PriceListEntryResponse,
    PriceListEntrySet,
    PriceListPage,
    PriceListResponse,
    PriceListUpdate,
    ResolvedPriceResponse,
)
from app.modules.pricing.application.services import PricingActor, PricingService
from app.modules.pricing.domain.policies import (
    PricingConflict,
    PricingNotFound,
    PricingPolicyError,
    PricingVersionConflict,
)
from app.modules.pricing.infrastructure.repositories import SqlAlchemyPricingRepository

router = APIRouter(prefix="/api/v1/pricing", tags=["pricing"])


def _actor(request: Request, ctx: TenantContext) -> PricingActor:
    return PricingActor(ctx.user_id, ctx.session_id, ctx.tenant_id, request.state.correlation_id)


def _service(request: Request, ctx: TenantContext, db: AsyncSession) -> tuple[PricingService, SqlAlchemyPricingRepository]:
    repository = SqlAlchemyPricingRepository(db)
    return PricingService(repository, _actor(request, ctx), db), repository


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


def _next_cursor(rows: list[Any], has_more: bool, *, timestamp_field: str = "created_at") -> str | None:
    if not rows or not has_more:
        return None
    return encode_cursor(getattr(rows[-1], timestamp_field), rows[-1].id)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PricingNotFound):
        return HTTPException(404, str(exc))
    if isinstance(exc, (PricingVersionConflict, PricingConflict, IdempotencyConflict)):
        return HTTPException(409, str(exc))
    if isinstance(exc, IdempotencyInProgress):
        return HTTPException(409, str(exc), headers={"Retry-After": "1"})
    if isinstance(exc, IntegrityError):
        return HTTPException(409, "Pricing resource conflicts with an existing tenant-scoped value")
    if isinstance(exc, PricingPolicyError):
        return HTTPException(422, str(exc))
    return HTTPException(400, str(exc))


async def _begin_create(
    db: AsyncSession, ctx: TenantContext, key: str, method: str, endpoint: str, payload: dict[str, Any]
) -> Any:
    try:
        result = await begin_idempotent(
            db, tenant_id=ctx.tenant_id, actor_id=ctx.user_id, method=method, endpoint=endpoint, key=key, payload=payload
        )
    except (IdempotencyConflict, IdempotencyInProgress) as exc:
        raise _http_error(exc) from exc
    if result.replay_body is not None:
        return JSONResponse(result.replay_body, status_code=result.replay_code or 200, headers={"Idempotency-Replayed": "true"})
    return result.record


async def _finish_create(db: AsyncSession, record: Any, response: Any, code: int = 201) -> Any:
    body = response.model_dump(mode="json")
    complete_idempotent(record, body, code)
    await db.commit()
    return response


async def _creation_failure(db: AsyncSession, record: Any, exc: Exception) -> NoReturn:
    if isinstance(exc, PricingPolicyError):
        error = _http_error(exc)
        complete_idempotent(record, {"detail": str(exc)}, error.status_code)
        await db.commit()
    else:
        await db.rollback()
    raise _http_error(exc) from exc


async def _mutation_failure(db: AsyncSession, exc: Exception) -> NoReturn:
    if isinstance(exc, PricingPolicyError):
        await db.commit()
    else:
        await db.rollback()
    raise _http_error(exc) from exc


async def _finish_mutation[SchemaT: BaseModel](db: AsyncSession, row: Any, schema: type[SchemaT]) -> SchemaT:
    try:
        await db.flush()
        await db.refresh(row)
    except IntegrityError as exc:
        await db.rollback()
        raise _http_error(exc) from exc
    response = schema.model_validate(row)
    await db.commit()
    return response


# --- Price Lists ---


@router.post("/price-lists", response_model=PriceListResponse, status_code=201)
async def create_price_list(
    payload: PriceListCreate,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("pricing.price_list.create"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Any:
    record = await _begin_create(db, ctx, idempotency_key, "POST", "/api/v1/pricing/price-lists", payload.model_dump(mode="json"))
    if isinstance(record, JSONResponse):
        return record
    service, _ = _service(request, ctx, db)
    try:
        row = await service.create_price_list(payload.model_dump())
        await db.flush()
        response = PriceListResponse.model_validate(row)
    except (PricingPolicyError, IntegrityError, ValueError) as exc:
        await _creation_failure(db, record, exc)
    return await _finish_create(db, record, response)


@router.get("/price-lists", response_model=PriceListPage)
async def list_price_lists(
    ctx: Annotated[TenantContext, Depends(require_permission("pricing.price_list.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
    status: str | None = None,
) -> PriceListPage:
    rows, has_more = await SqlAlchemyPricingRepository(db).list_price_lists(
        ctx.tenant_id, limit=limit, cursor=_cursor(cursor), status=status
    )
    return PriceListPage(
        items=[PriceListResponse.model_validate(row) for row in rows],
        next_cursor=_next_cursor(rows, has_more),
        has_more=has_more,
    )


@router.get("/price-lists/{resource_id}", response_model=PriceListResponse)
async def get_price_list(
    resource_id: UUID,
    ctx: Annotated[TenantContext, Depends(require_permission("pricing.price_list.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> PriceListResponse:
    row = await SqlAlchemyPricingRepository(db).get_price_list(ctx.tenant_id, resource_id)
    if row is None:
        raise HTTPException(404, "Price List not found")
    return PriceListResponse.model_validate(row)


@router.patch("/price-lists/{resource_id}", response_model=PriceListResponse)
async def update_price_list(
    resource_id: UUID,
    payload: PriceListUpdate,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("pricing.price_list.update"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> PriceListResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.update_price_list(resource_id, _expected_version(if_match), payload.model_dump(exclude_unset=True))
    except (PricingPolicyError, IntegrityError) as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, PriceListResponse)


@router.post("/price-lists/{resource_id}/archive", response_model=PriceListResponse)
async def archive_price_list(
    resource_id: UUID,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("pricing.price_list.archive"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> PriceListResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.archive_price_list(resource_id, _expected_version(if_match))
    except PricingPolicyError as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, PriceListResponse)


# --- Price List Entries ---


@router.put("/price-lists/{price_list_id}/entries/{variant_id}", response_model=PriceListEntryResponse)
async def set_price_list_entry(
    price_list_id: UUID,
    variant_id: UUID,
    payload: PriceListEntrySet,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("pricing.price_list_entry.manage"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> PriceListEntryResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.set_price_list_entry(price_list_id, variant_id, payload.model_dump())
    except (PricingPolicyError, IntegrityError, ValueError) as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, PriceListEntryResponse)


@router.get("/price-lists/{price_list_id}/entries", response_model=PriceListEntryPage)
async def list_price_list_entries(
    price_list_id: UUID,
    ctx: Annotated[TenantContext, Depends(require_permission("pricing.price_list_entry.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> PriceListEntryPage:
    rows, has_more = await SqlAlchemyPricingRepository(db).list_price_list_entries(
        ctx.tenant_id, price_list_id, limit=limit, cursor=_cursor(cursor)
    )
    return PriceListEntryPage(
        items=[PriceListEntryResponse.model_validate(row) for row in rows],
        next_cursor=_next_cursor(rows, has_more),
        has_more=has_more,
    )


# --- Assignments ---


@router.post("/assignments", response_model=AssignmentResponse, status_code=201)
async def create_assignment(
    payload: AssignmentCreate,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("pricing.assignment.manage"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Any:
    record = await _begin_create(db, ctx, idempotency_key, "POST", "/api/v1/pricing/assignments", payload.model_dump(mode="json"))
    if isinstance(record, JSONResponse):
        return record
    service, _ = _service(request, ctx, db)
    try:
        row = await service.create_assignment(payload.model_dump())
        await db.flush()
        response = AssignmentResponse.model_validate(row)
    except (PricingPolicyError, IntegrityError, ValueError) as exc:
        await _creation_failure(db, record, exc)
    return await _finish_create(db, record, response)


@router.get("/assignments", response_model=AssignmentPage)
async def list_assignments(
    ctx: Annotated[TenantContext, Depends(require_permission("pricing.assignment.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
    price_list_id: UUID | None = None,
    status: str | None = None,
) -> AssignmentPage:
    rows, has_more = await SqlAlchemyPricingRepository(db).list_assignments(
        ctx.tenant_id, limit=limit, cursor=_cursor(cursor), price_list_id=price_list_id, status=status
    )
    return AssignmentPage(
        items=[AssignmentResponse.model_validate(row) for row in rows],
        next_cursor=_next_cursor(rows, has_more),
        has_more=has_more,
    )


@router.get("/assignments/{resource_id}", response_model=AssignmentResponse)
async def get_assignment(
    resource_id: UUID,
    ctx: Annotated[TenantContext, Depends(require_permission("pricing.assignment.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> AssignmentResponse:
    row = await SqlAlchemyPricingRepository(db).get_assignment(ctx.tenant_id, resource_id)
    if row is None:
        raise HTTPException(404, "Assignment not found")
    return AssignmentResponse.model_validate(row)


@router.post("/assignments/{resource_id}/archive", response_model=AssignmentResponse)
async def archive_assignment(
    resource_id: UUID,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("pricing.assignment.manage"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> AssignmentResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.archive_assignment(resource_id, _expected_version(if_match))
    except PricingPolicyError as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, AssignmentResponse)


# --- Variant Price Overrides ---


@router.post("/variant-overrides", response_model=OverrideResponse, status_code=201)
async def create_override(
    payload: OverrideCreate,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("pricing.variant_override.manage"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Any:
    record = await _begin_create(
        db, ctx, idempotency_key, "POST", "/api/v1/pricing/variant-overrides", payload.model_dump(mode="json")
    )
    if isinstance(record, JSONResponse):
        return record
    service, _ = _service(request, ctx, db)
    try:
        row = await service.create_override(payload.model_dump())
        await db.flush()
        response = OverrideResponse.model_validate(row)
    except (PricingPolicyError, IntegrityError, ValueError) as exc:
        await _creation_failure(db, record, exc)
    return await _finish_create(db, record, response)


@router.get("/variant-overrides", response_model=OverridePage)
async def list_overrides(
    ctx: Annotated[TenantContext, Depends(require_permission("pricing.variant_override.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
    variant_id: UUID | None = None,
    status: str | None = None,
) -> OverridePage:
    rows, has_more = await SqlAlchemyPricingRepository(db).list_overrides(
        ctx.tenant_id, limit=limit, cursor=_cursor(cursor), variant_id=variant_id, status=status
    )
    return OverridePage(
        items=[OverrideResponse.model_validate(row) for row in rows],
        next_cursor=_next_cursor(rows, has_more),
        has_more=has_more,
    )


@router.get("/variant-overrides/{resource_id}", response_model=OverrideResponse)
async def get_override(
    resource_id: UUID,
    ctx: Annotated[TenantContext, Depends(require_permission("pricing.variant_override.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> OverrideResponse:
    row = await SqlAlchemyPricingRepository(db).get_override(ctx.tenant_id, resource_id)
    if row is None:
        raise HTTPException(404, "Variant Price Override not found")
    return OverrideResponse.model_validate(row)


@router.post("/variant-overrides/{resource_id}/archive", response_model=OverrideResponse)
async def archive_override(
    resource_id: UUID,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("pricing.variant_override.manage"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> OverrideResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.archive_override(resource_id, _expected_version(if_match))
    except PricingPolicyError as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, OverrideResponse)


# --- Resolution ---


@router.get("/resolve", response_model=ResolvedPriceResponse)
async def resolve_price(
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("pricing.price.resolve"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    variant_id: UUID,
    store_id: UUID | None = None,
    channel_id: UUID | None = None,
    market_id: UUID | None = None,
    at: datetime | None = None,
) -> ResolvedPriceResponse:
    service, _ = _service(request, ctx, db)
    try:
        resolved = await service.resolve_price(
            variant_id, store_id=store_id, channel_id=channel_id, market_id=market_id, at=at
        )
    except PricingPolicyError as exc:
        await db.commit()
        raise _http_error(exc) from exc
    await db.commit()
    if resolved is None:
        raise HTTPException(404, "No price is configured for this Variant in the given scope")
    return ResolvedPriceResponse.model_validate(resolved)


# --- History ---


@router.get("/price-history", response_model=PriceHistoryPage)
async def list_price_history(
    ctx: Annotated[TenantContext, Depends(require_permission("pricing.price_list_entry.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
    variant_id: UUID | None = None,
    price_list_id: UUID | None = None,
) -> PriceHistoryPage:
    rows, has_more = await SqlAlchemyPricingRepository(db).list_history(
        ctx.tenant_id, limit=limit, cursor=_cursor(cursor), variant_id=variant_id, price_list_id=price_list_id
    )
    return PriceHistoryPage(
        items=[PriceHistoryResponse.model_validate(row) for row in rows],
        next_cursor=_next_cursor(rows, has_more, timestamp_field="changed_at"),
        has_more=has_more,
    )

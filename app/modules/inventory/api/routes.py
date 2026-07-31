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
from app.modules.inventory.api.schemas import (
    AllocationLine,
    AllocationPlanResponse,
    FulfillmentScopeCreate,
    FulfillmentScopePage,
    FulfillmentScopeResponse,
    LedgerEntryResponse,
    LedgerPage,
    LocationCreate,
    LocationPage,
    LocationResponse,
    ReservationBatchResponse,
    ReservationCreate,
    ReservationPage,
    ReservationResponse,
    StockAdjust,
    StockLevelPage,
    StockLevelResponse,
    StockReceive,
    StockRecount,
    TransferCreate,
    TransferPage,
    TransferResponse,
    WarehouseCreate,
    WarehousePage,
    WarehouseResponse,
)
from app.modules.inventory.application.services import InventoryActor, InventoryService
from app.modules.inventory.domain.policies import (
    InsufficientStock,
    InventoryConflict,
    InventoryNotFound,
    InventoryPolicyError,
    InventoryVersionConflict,
)
from app.modules.inventory.infrastructure.repositories import SqlAlchemyInventoryRepository
from app.modules.platform.application.idempotency import (
    IdempotencyConflict,
    IdempotencyInProgress,
    begin_idempotent,
    complete_idempotent,
)

router = APIRouter(prefix="/api/v1/inventory", tags=["inventory"])


def _actor(request: Request, ctx: TenantContext) -> InventoryActor:
    return InventoryActor(ctx.user_id, ctx.session_id, ctx.tenant_id, request.state.correlation_id)


def _service(request: Request, ctx: TenantContext, db: AsyncSession) -> tuple[InventoryService, SqlAlchemyInventoryRepository]:
    repository = SqlAlchemyInventoryRepository(db)
    return InventoryService(repository, _actor(request, ctx), db), repository


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
    if isinstance(exc, InventoryNotFound):
        return HTTPException(404, str(exc))
    if isinstance(exc, (InventoryVersionConflict, InsufficientStock, InventoryConflict, IdempotencyConflict)):
        return HTTPException(409, str(exc))
    if isinstance(exc, IdempotencyInProgress):
        return HTTPException(409, str(exc), headers={"Retry-After": "1"})
    if isinstance(exc, IntegrityError):
        return HTTPException(409, "Inventory resource conflicts with an existing tenant-scoped value")
    if isinstance(exc, InventoryPolicyError):
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
    if isinstance(exc, InventoryPolicyError):
        error = _http_error(exc)
        complete_idempotent(record, {"detail": str(exc)}, error.status_code)
        await db.commit()
    else:
        await db.rollback()
    raise _http_error(exc) from exc


async def _mutation_failure(db: AsyncSession, exc: Exception) -> NoReturn:
    if isinstance(exc, InventoryPolicyError):
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


# --- Warehouses ---


@router.post("/warehouses", response_model=WarehouseResponse, status_code=201)
async def create_warehouse(
    payload: WarehouseCreate,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("inventory.warehouse.create"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Any:
    record = await _begin_create(db, ctx, idempotency_key, "POST", "/api/v1/inventory/warehouses", payload.model_dump(mode="json"))
    if isinstance(record, JSONResponse):
        return record
    service, _ = _service(request, ctx, db)
    try:
        row = await service.create_warehouse(payload.model_dump())
        await db.flush()
        response = WarehouseResponse.model_validate(row)
    except (InventoryPolicyError, IntegrityError, ValueError) as exc:
        await _creation_failure(db, record, exc)
    return await _finish_create(db, record, response)


@router.get("/warehouses", response_model=WarehousePage)
async def list_warehouses(
    ctx: Annotated[TenantContext, Depends(require_permission("inventory.warehouse.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
    status: str | None = None,
) -> WarehousePage:
    rows, has_more = await SqlAlchemyInventoryRepository(db).list_warehouses(
        ctx.tenant_id, limit=limit, cursor=_cursor(cursor), status=status
    )
    return WarehousePage(
        items=[WarehouseResponse.model_validate(row) for row in rows],
        next_cursor=_next_cursor(rows, has_more),
        has_more=has_more,
    )


@router.get("/warehouses/{resource_id}", response_model=WarehouseResponse)
async def get_warehouse(
    resource_id: UUID,
    ctx: Annotated[TenantContext, Depends(require_permission("inventory.warehouse.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> WarehouseResponse:
    row = await SqlAlchemyInventoryRepository(db).get_warehouse(ctx.tenant_id, resource_id)
    if row is None:
        raise HTTPException(404, "Warehouse not found")
    return WarehouseResponse.model_validate(row)


@router.post("/warehouses/{resource_id}/archive", response_model=WarehouseResponse)
async def archive_warehouse(
    resource_id: UUID,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("inventory.warehouse.archive"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> WarehouseResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.archive_warehouse(resource_id, _expected_version(if_match))
    except InventoryPolicyError as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, WarehouseResponse)


# --- Locations ---


@router.post("/warehouses/{warehouse_id}/locations", response_model=LocationResponse, status_code=201)
async def create_location(
    warehouse_id: UUID,
    payload: LocationCreate,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("inventory.location.create"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Any:
    endpoint = f"/api/v1/inventory/warehouses/{warehouse_id}/locations"
    record = await _begin_create(db, ctx, idempotency_key, "POST", endpoint, payload.model_dump(mode="json"))
    if isinstance(record, JSONResponse):
        return record
    service, _ = _service(request, ctx, db)
    try:
        row = await service.create_location(warehouse_id, payload.model_dump())
        await db.flush()
        response = LocationResponse.model_validate(row)
    except (InventoryPolicyError, IntegrityError, ValueError) as exc:
        await _creation_failure(db, record, exc)
    return await _finish_create(db, record, response)


@router.get("/locations", response_model=LocationPage)
async def list_locations(
    ctx: Annotated[TenantContext, Depends(require_permission("inventory.location.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
    warehouse_id: UUID | None = None,
) -> LocationPage:
    rows, has_more = await SqlAlchemyInventoryRepository(db).list_locations(
        ctx.tenant_id, limit=limit, cursor=_cursor(cursor), warehouse_id=warehouse_id
    )
    return LocationPage(
        items=[LocationResponse.model_validate(row) for row in rows],
        next_cursor=_next_cursor(rows, has_more),
        has_more=has_more,
    )


# --- Stock ---


@router.get("/stock", response_model=StockLevelPage)
async def list_stock(
    ctx: Annotated[TenantContext, Depends(require_permission("inventory.stock.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
    variant_id: UUID | None = None,
    location_id: UUID | None = None,
) -> StockLevelPage:
    rows, has_more = await SqlAlchemyInventoryRepository(db).list_stock_levels(
        ctx.tenant_id, limit=limit, cursor=_cursor(cursor), variant_id=variant_id, location_id=location_id
    )
    return StockLevelPage(
        items=[StockLevelResponse.model_validate(row) for row in rows],
        next_cursor=_next_cursor(rows, has_more),
        has_more=has_more,
    )


@router.post("/locations/{location_id}/variants/{variant_id}/adjust", response_model=StockLevelResponse)
async def adjust_stock(
    location_id: UUID,
    variant_id: UUID,
    payload: StockAdjust,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("inventory.stock.adjust"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> StockLevelResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.adjust_stock(location_id, variant_id, payload.delta, payload.reason)
    except (InventoryPolicyError, IntegrityError, ValueError) as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, StockLevelResponse)


@router.post("/locations/{location_id}/variants/{variant_id}/receive", response_model=StockLevelResponse)
async def receive_stock(
    location_id: UUID,
    variant_id: UUID,
    payload: StockReceive,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("inventory.stock.adjust"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> StockLevelResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.receive_stock(location_id, variant_id, payload.quantity, payload.reason)
    except (InventoryPolicyError, IntegrityError, ValueError) as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, StockLevelResponse)


@router.post("/locations/{location_id}/variants/{variant_id}/recount", response_model=StockLevelResponse)
async def recount_stock(
    location_id: UUID,
    variant_id: UUID,
    payload: StockRecount,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("inventory.stock.recount"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> StockLevelResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.recount_stock(location_id, variant_id, payload.counted, payload.reason)
    except (InventoryPolicyError, IntegrityError, ValueError) as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, StockLevelResponse)


@router.get("/ledger", response_model=LedgerPage)
async def list_ledger(
    ctx: Annotated[TenantContext, Depends(require_permission("inventory.stock.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
    variant_id: UUID | None = None,
    location_id: UUID | None = None,
) -> LedgerPage:
    rows, has_more = await SqlAlchemyInventoryRepository(db).list_ledger(
        ctx.tenant_id, limit=limit, cursor=_cursor(cursor), variant_id=variant_id, location_id=location_id
    )
    return LedgerPage(
        items=[LedgerEntryResponse.model_validate(row) for row in rows],
        next_cursor=_next_cursor(rows, has_more),
        has_more=has_more,
    )


# --- Transfers ---


@router.post("/transfers", response_model=TransferResponse, status_code=201)
async def create_transfer(
    payload: TransferCreate,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("inventory.transfer.manage"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Any:
    record = await _begin_create(db, ctx, idempotency_key, "POST", "/api/v1/inventory/transfers", payload.model_dump(mode="json"))
    if isinstance(record, JSONResponse):
        return record
    service, _ = _service(request, ctx, db)
    try:
        row = await service.create_transfer(payload.model_dump())
        await db.flush()
        response = TransferResponse.model_validate(row)
    except (InventoryPolicyError, IntegrityError, ValueError) as exc:
        await _creation_failure(db, record, exc)
    return await _finish_create(db, record, response)


@router.get("/transfers", response_model=TransferPage)
async def list_transfers(
    ctx: Annotated[TenantContext, Depends(require_permission("inventory.transfer.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
    status: str | None = None,
) -> TransferPage:
    rows, has_more = await SqlAlchemyInventoryRepository(db).list_transfers(
        ctx.tenant_id, limit=limit, cursor=_cursor(cursor), status=status
    )
    return TransferPage(
        items=[TransferResponse.model_validate(row) for row in rows],
        next_cursor=_next_cursor(rows, has_more),
        has_more=has_more,
    )


@router.post("/transfers/{resource_id}/complete", response_model=TransferResponse)
async def complete_transfer(
    resource_id: UUID,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("inventory.transfer.manage"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> TransferResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.complete_transfer(resource_id, _expected_version(if_match))
    except InventoryPolicyError as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, TransferResponse)


@router.post("/transfers/{resource_id}/cancel", response_model=TransferResponse)
async def cancel_transfer(
    resource_id: UUID,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("inventory.transfer.manage"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> TransferResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.cancel_transfer(resource_id, _expected_version(if_match))
    except InventoryPolicyError as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, TransferResponse)


# --- Reservations ---


@router.post("/reservations", response_model=ReservationBatchResponse, status_code=201)
async def create_reservation(
    payload: ReservationCreate,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("inventory.reservation.manage"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Any:
    record = await _begin_create(db, ctx, idempotency_key, "POST", "/api/v1/inventory/reservations", payload.model_dump(mode="json"))
    if isinstance(record, JSONResponse):
        return record
    service, _ = _service(request, ctx, db)
    try:
        rows = await service.reserve_for_scope(payload.model_dump())
        await db.flush()
        response = ReservationBatchResponse(items=[ReservationResponse.model_validate(row) for row in rows])
    except (InventoryPolicyError, IntegrityError, ValueError) as exc:
        await _creation_failure(db, record, exc)
    return await _finish_create(db, record, response)


@router.get("/reservations", response_model=ReservationPage)
async def list_reservations(
    ctx: Annotated[TenantContext, Depends(require_permission("inventory.reservation.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
    variant_id: UUID | None = None,
    status: str | None = None,
) -> ReservationPage:
    rows, has_more = await SqlAlchemyInventoryRepository(db).list_reservations(
        ctx.tenant_id, limit=limit, cursor=_cursor(cursor), variant_id=variant_id, status=status
    )
    return ReservationPage(
        items=[ReservationResponse.model_validate(row) for row in rows],
        next_cursor=_next_cursor(rows, has_more),
        has_more=has_more,
    )


@router.post("/reservations/{resource_id}/release", response_model=ReservationResponse)
async def release_reservation(
    resource_id: UUID,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("inventory.reservation.manage"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> ReservationResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.release_reservation(resource_id, _expected_version(if_match))
    except InventoryPolicyError as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, ReservationResponse)


@router.post("/reservations/{resource_id}/commit", response_model=ReservationResponse)
async def commit_reservation(
    resource_id: UUID,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("inventory.reservation.manage"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> ReservationResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.commit_reservation(resource_id, _expected_version(if_match))
    except InventoryPolicyError as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, ReservationResponse)


# --- Fulfillment scopes ---


@router.post("/fulfillment-scopes", response_model=FulfillmentScopeResponse, status_code=201)
async def create_fulfillment_scope(
    payload: FulfillmentScopeCreate,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("inventory.fulfillment_scope.manage"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Any:
    record = await _begin_create(
        db, ctx, idempotency_key, "POST", "/api/v1/inventory/fulfillment-scopes", payload.model_dump(mode="json")
    )
    if isinstance(record, JSONResponse):
        return record
    service, _ = _service(request, ctx, db)
    try:
        row = await service.create_fulfillment_scope(payload.model_dump())
        await db.flush()
        response = FulfillmentScopeResponse.model_validate(row)
    except (InventoryPolicyError, IntegrityError, ValueError) as exc:
        await _creation_failure(db, record, exc)
    return await _finish_create(db, record, response)


@router.get("/fulfillment-scopes", response_model=FulfillmentScopePage)
async def list_fulfillment_scopes(
    ctx: Annotated[TenantContext, Depends(require_permission("inventory.fulfillment_scope.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
    warehouse_id: UUID | None = None,
) -> FulfillmentScopePage:
    rows, has_more = await SqlAlchemyInventoryRepository(db).list_fulfillment_scopes(
        ctx.tenant_id, limit=limit, cursor=_cursor(cursor), warehouse_id=warehouse_id
    )
    return FulfillmentScopePage(
        items=[FulfillmentScopeResponse.model_validate(row) for row in rows],
        next_cursor=_next_cursor(rows, has_more),
        has_more=has_more,
    )


@router.post("/fulfillment-scopes/{resource_id}/archive", response_model=FulfillmentScopeResponse)
async def archive_fulfillment_scope(
    resource_id: UUID,
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("inventory.fulfillment_scope.manage"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
) -> FulfillmentScopeResponse:
    service, _ = _service(request, ctx, db)
    try:
        row = await service.archive_fulfillment_scope(resource_id, _expected_version(if_match))
    except InventoryPolicyError as exc:
        await _mutation_failure(db, exc)
    return await _finish_mutation(db, row, FulfillmentScopeResponse)


# --- Allocation ---


@router.get("/allocate", response_model=AllocationPlanResponse)
async def allocate_stock(
    request: Request,
    ctx: Annotated[TenantContext, Depends(require_permission("inventory.allocation.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    variant_id: UUID,
    quantity: Annotated[int, Query(ge=1)],
    scope_type: str,
    scope_id: UUID,
) -> AllocationPlanResponse:
    service, _ = _service(request, ctx, db)
    try:
        plan = await service.allocate_for_scope(variant_id, quantity, scope_type, scope_id)
    except InventoryPolicyError as exc:
        await db.commit()
        raise _http_error(exc) from exc
    await db.commit()
    return AllocationPlanResponse(
        requested=plan.requested,
        allocated=plan.allocated,
        shortfall=plan.shortfall,
        fully_allocated=plan.fully_allocated,
        allocations=[
            AllocationLine(location_id=a.location_id, warehouse_id=a.warehouse_id, quantity=a.quantity)
            for a in plan.allocations
        ],
    )

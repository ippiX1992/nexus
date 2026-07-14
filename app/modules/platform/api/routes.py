from typing import Annotated, Any, NoReturn, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_permission
from app.application.auth import audit
from app.application.authorization import TenantContext
from app.infrastructure.database import get_session
from app.infrastructure.models import MembershipModel
from app.infrastructure.tenant_context import set_store_context
from app.modules.platform.api.schemas import (
    ChannelCreate,
    ChannelResponse,
    ChannelUpdate,
    EntitlementOverrideRequest,
    EntitlementResponse,
    EnvironmentCreate,
    EnvironmentResponse,
    EnvironmentUpdate,
    MarketCreate,
    MarketResponse,
    MarketUpdate,
    OperationResponse,
    SiteCreate,
    SiteResponse,
    SiteUpdate,
    StoreCreate,
    StoreResponse,
    StoreUpdate,
    UsageResponse,
)
from app.modules.platform.application.idempotency import (
    IdempotencyConflict,
    IdempotencyInProgress,
    begin_idempotent,
    complete_idempotent,
)
from app.modules.platform.application.services import PlatformActor, PlatformNotFound, PlatformService
from app.modules.platform.domain.policies import PlatformPolicyError, QuotaExceeded
from app.modules.platform.infrastructure.models import (
    EntitlementDefinitionModel,
    EntitlementOverrideModel,
    OperationModel,
)
from app.modules.platform.infrastructure.repositories import SqlAlchemyPlatformRepository

router = APIRouter(prefix="/api/v1", tags=["platform"])
SchemaT = TypeVar("SchemaT")


def _actor(request: Request, ctx: TenantContext) -> PlatformActor:
    return PlatformActor(ctx.user_id, ctx.session_id, ctx.tenant_id, request.state.correlation_id)


def _service(request: Request, ctx: TenantContext, db: AsyncSession) -> tuple[PlatformService, SqlAlchemyPlatformRepository]:
    repository = SqlAlchemyPlatformRepository(db)
    return PlatformService(repository, _actor(request, ctx), db), repository


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PlatformNotFound):
        return HTTPException(404, str(exc))
    if isinstance(exc, QuotaExceeded):
        return HTTPException(409, str(exc))
    if isinstance(exc, IdempotencyConflict):
        return HTTPException(409, str(exc))
    if isinstance(exc, IdempotencyInProgress):
        return HTTPException(409, str(exc), headers={"Retry-After": "1"})
    if isinstance(exc, IntegrityError):
        return HTTPException(409, "Resource conflicts with an existing tenant-scoped value")
    return HTTPException(400, str(exc))


async def _begin_create(
    db: AsyncSession,
    ctx: TenantContext,
    key: str,
    endpoint: str,
    payload: dict[str, Any],
) -> Any:
    try:
        result = await begin_idempotent(db, tenant_id=ctx.tenant_id, actor_id=ctx.user_id, method="POST", endpoint=endpoint, key=key, payload=payload)
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


async def _creation_failure(db: AsyncSession, record: Any, exc: Exception) -> None:
    if isinstance(exc, (QuotaExceeded, PlatformNotFound)):
        code = 409 if isinstance(exc, QuotaExceeded) else 404
        complete_idempotent(record, {"detail": str(exc)}, code)
        await db.commit()
    else:
        await db.rollback()
    raise _http_error(exc) from exc


async def _mutation_failure(db: AsyncSession, exc: PlatformPolicyError) -> None:
    if isinstance(exc, PlatformNotFound):
        await db.commit()
    else:
        await db.rollback()
    raise _http_error(exc) from exc


async def _scope_not_found(
    db: AsyncSession,
    ctx: TenantContext,
    request: Request,
    kind: str,
    resource_id: UUID,
) -> NoReturn:
    await audit(
        db,
        "platform.scope_denied",
        "denied",
        ctx.user_id,
        ctx.tenant_id,
        resource=str(resource_id),
        metadata={"kind": kind, "correlation_id": str(request.state.correlation_id)},
    )
    await db.commit()
    raise HTTPException(404, f"{kind.title()} not found")


@router.get("/stores", response_model=list[StoreResponse])
async def list_stores(ctx: Annotated[TenantContext, Depends(require_permission("store.read"))], db: Annotated[AsyncSession, Depends(get_session)]) -> list[StoreResponse]:
    rows = await SqlAlchemyPlatformRepository(db).list_resources("store", ctx.tenant_id)
    return [StoreResponse.model_validate(row) for row in rows]


@router.post("/stores", response_model=StoreResponse, status_code=201)
async def create_store(payload: StoreCreate, request: Request, ctx: Annotated[TenantContext, Depends(require_permission("store.create"))], db: Annotated[AsyncSession, Depends(get_session)], idempotency_key: Annotated[str, Header(alias="Idempotency-Key")]) -> Any:
    record = await _begin_create(db, ctx, idempotency_key, "/api/v1/stores", payload.model_dump(mode="json"))
    if isinstance(record, JSONResponse): return record
    service, _ = _service(request, ctx, db)
    try:
        row = await service.create_store(payload.model_dump())
        return await _finish_create(db, record, StoreResponse.model_validate(row))
    except (PlatformPolicyError, IntegrityError) as exc:
        await _creation_failure(db, record, exc)


@router.get("/stores/{store_id}", response_model=StoreResponse)
async def get_store(store_id: UUID, request: Request, ctx: Annotated[TenantContext, Depends(require_permission("store.read"))], db: Annotated[AsyncSession, Depends(get_session)]) -> StoreResponse:
    row = await SqlAlchemyPlatformRepository(db).get_store(ctx.tenant_id, store_id)
    if row is None: await _scope_not_found(db, ctx, request, "store", store_id)
    return StoreResponse.model_validate(row)


@router.patch("/stores/{store_id}", response_model=StoreResponse)
async def update_store(store_id: UUID, payload: StoreUpdate, request: Request, ctx: Annotated[TenantContext, Depends(require_permission("store.update"))], db: Annotated[AsyncSession, Depends(get_session)]) -> StoreResponse:
    service, _ = _service(request, ctx, db)
    try: row = await service.update("store", store_id, payload.model_dump(exclude_unset=True))
    except PlatformPolicyError as exc: await _mutation_failure(db, exc)
    await db.flush(); await db.refresh(row); response = StoreResponse.model_validate(row); await db.commit(); return response


async def _transition_store(store_id: UUID, target: str, request: Request, ctx: TenantContext, db: AsyncSession) -> StoreResponse:
    service, _ = _service(request, ctx, db)
    try: row = await service.transition_store(store_id, target)
    except PlatformPolicyError as exc: await _mutation_failure(db, exc)
    await db.flush(); await db.refresh(row); response = StoreResponse.model_validate(row); await db.commit(); return response


@router.post("/stores/{store_id}/activate", response_model=StoreResponse)
async def activate_store(store_id: UUID, request: Request, ctx: Annotated[TenantContext, Depends(require_permission("store.update"))], db: Annotated[AsyncSession, Depends(get_session)]) -> StoreResponse:
    return await _transition_store(store_id, "active", request, ctx, db)


@router.post("/stores/{store_id}/suspend", response_model=StoreResponse)
async def suspend_store(store_id: UUID, request: Request, ctx: Annotated[TenantContext, Depends(require_permission("store.update"))], db: Annotated[AsyncSession, Depends(get_session)]) -> StoreResponse:
    return await _transition_store(store_id, "suspended", request, ctx, db)


@router.post("/stores/{store_id}/archive", response_model=StoreResponse)
async def archive_store(store_id: UUID, request: Request, ctx: Annotated[TenantContext, Depends(require_permission("store.archive"))], db: Annotated[AsyncSession, Depends(get_session)]) -> StoreResponse:
    return await _transition_store(store_id, "archived", request, ctx, db)


async def _child_list(kind: str, store_id: UUID, request: Request, ctx: TenantContext, db: AsyncSession) -> list[Any]:
    repo = SqlAlchemyPlatformRepository(db)
    if await repo.get_store(ctx.tenant_id, store_id) is None: await _scope_not_found(db, ctx, request, "store", store_id)
    await set_store_context(db, store_id)
    return await repo.list_resources(kind, ctx.tenant_id, store_id)


async def _child_get(kind: str, resource_id: UUID, request: Request, ctx: TenantContext, db: AsyncSession) -> Any:
    row = await SqlAlchemyPlatformRepository(db).get_resource(kind, ctx.tenant_id, resource_id)
    if row is None: await _scope_not_found(db, ctx, request, kind, resource_id)
    await set_store_context(db, row.store_id)
    return row


@router.get("/stores/{store_id}/sites", response_model=list[SiteResponse])
async def list_sites(store_id: UUID, request: Request, ctx: Annotated[TenantContext, Depends(require_permission("site.read"))], db: Annotated[AsyncSession, Depends(get_session)]) -> list[SiteResponse]:
    return [SiteResponse.model_validate(row) for row in await _child_list("site", store_id, request, ctx, db)]


@router.post("/stores/{store_id}/sites", response_model=SiteResponse, status_code=201)
async def create_site(store_id: UUID, payload: SiteCreate, request: Request, ctx: Annotated[TenantContext, Depends(require_permission("site.create"))], db: Annotated[AsyncSession, Depends(get_session)], idempotency_key: Annotated[str, Header(alias="Idempotency-Key")]) -> Any:
    await set_store_context(db, store_id)
    endpoint = f"/api/v1/stores/{store_id}/sites"; record = await _begin_create(db, ctx, idempotency_key, endpoint, payload.model_dump(mode="json"))
    if isinstance(record, JSONResponse): return record
    service, _ = _service(request, ctx, db)
    try: row = await service.create_site(store_id, payload.model_dump())
    except (PlatformPolicyError, IntegrityError) as exc: await _creation_failure(db, record, exc)
    return await _finish_create(db, record, SiteResponse.model_validate(row))


@router.get("/sites/{site_id}", response_model=SiteResponse)
async def get_site(site_id: UUID, request: Request, ctx: Annotated[TenantContext, Depends(require_permission("site.read"))], db: Annotated[AsyncSession, Depends(get_session)]) -> SiteResponse:
    return SiteResponse.model_validate(await _child_get("site", site_id, request, ctx, db))


@router.patch("/sites/{site_id}", response_model=SiteResponse)
async def update_site(site_id: UUID, payload: SiteUpdate, request: Request, ctx: Annotated[TenantContext, Depends(require_permission("site.update"))], db: Annotated[AsyncSession, Depends(get_session)]) -> SiteResponse:
    service, _ = _service(request, ctx, db)
    try: row = await service.update("site", site_id, payload.model_dump(exclude_unset=True))
    except PlatformPolicyError as exc: await _mutation_failure(db, exc)
    await db.flush(); await db.refresh(row); response = SiteResponse.model_validate(row); await db.commit(); return response


@router.post("/sites/{site_id}/archive", response_model=SiteResponse)
async def archive_site(site_id: UUID, request: Request, ctx: Annotated[TenantContext, Depends(require_permission("site.archive"))], db: Annotated[AsyncSession, Depends(get_session)]) -> SiteResponse:
    service, _ = _service(request, ctx, db)
    try: row = await service.archive("site", site_id)
    except PlatformPolicyError as exc: await _mutation_failure(db, exc)
    await db.flush(); await db.refresh(row); response = SiteResponse.model_validate(row); await db.commit(); return response


@router.get("/stores/{store_id}/channels", response_model=list[ChannelResponse])
async def list_channels(store_id: UUID, request: Request, ctx: Annotated[TenantContext, Depends(require_permission("channel.read"))], db: Annotated[AsyncSession, Depends(get_session)]) -> list[ChannelResponse]:
    return [ChannelResponse.model_validate(row) for row in await _child_list("channel", store_id, request, ctx, db)]


@router.post("/stores/{store_id}/channels", response_model=ChannelResponse, status_code=201)
async def create_channel(store_id: UUID, payload: ChannelCreate, request: Request, ctx: Annotated[TenantContext, Depends(require_permission("channel.create"))], db: Annotated[AsyncSession, Depends(get_session)], idempotency_key: Annotated[str, Header(alias="Idempotency-Key")]) -> Any:
    await set_store_context(db, store_id)
    endpoint = f"/api/v1/stores/{store_id}/channels"; record = await _begin_create(db, ctx, idempotency_key, endpoint, payload.model_dump(mode="json"))
    if isinstance(record, JSONResponse): return record
    service, _ = _service(request, ctx, db)
    try: row = await service.create_channel(store_id, payload.model_dump())
    except (PlatformPolicyError, IntegrityError) as exc: await _creation_failure(db, record, exc)
    return await _finish_create(db, record, ChannelResponse.model_validate(row))


@router.get("/channels/{channel_id}", response_model=ChannelResponse)
async def get_channel(channel_id: UUID, request: Request, ctx: Annotated[TenantContext, Depends(require_permission("channel.read"))], db: Annotated[AsyncSession, Depends(get_session)]) -> ChannelResponse:
    return ChannelResponse.model_validate(await _child_get("channel", channel_id, request, ctx, db))


@router.patch("/channels/{channel_id}", response_model=ChannelResponse)
async def update_channel(channel_id: UUID, payload: ChannelUpdate, request: Request, ctx: Annotated[TenantContext, Depends(require_permission("channel.update"))], db: Annotated[AsyncSession, Depends(get_session)]) -> ChannelResponse:
    service, _ = _service(request, ctx, db)
    try: row = await service.update("channel", channel_id, payload.model_dump(exclude_unset=True))
    except PlatformPolicyError as exc: await _mutation_failure(db, exc)
    await db.flush(); await db.refresh(row); response = ChannelResponse.model_validate(row); await db.commit(); return response


@router.post("/channels/{channel_id}/archive", response_model=ChannelResponse)
async def archive_channel(channel_id: UUID, request: Request, ctx: Annotated[TenantContext, Depends(require_permission("channel.archive"))], db: Annotated[AsyncSession, Depends(get_session)]) -> ChannelResponse:
    service, _ = _service(request, ctx, db)
    try: row = await service.archive("channel", channel_id)
    except PlatformPolicyError as exc: await _mutation_failure(db, exc)
    await db.flush(); await db.refresh(row); response = ChannelResponse.model_validate(row); await db.commit(); return response


@router.get("/stores/{store_id}/environments", response_model=list[EnvironmentResponse])
async def list_environments(store_id: UUID, request: Request, ctx: Annotated[TenantContext, Depends(require_permission("environment.read"))], db: Annotated[AsyncSession, Depends(get_session)]) -> list[EnvironmentResponse]:
    return [EnvironmentResponse.model_validate(row) for row in await _child_list("environment", store_id, request, ctx, db)]


@router.post("/stores/{store_id}/environments", response_model=EnvironmentResponse, status_code=201)
async def create_environment(store_id: UUID, payload: EnvironmentCreate, request: Request, ctx: Annotated[TenantContext, Depends(require_permission("environment.create"))], db: Annotated[AsyncSession, Depends(get_session)], idempotency_key: Annotated[str, Header(alias="Idempotency-Key")]) -> Any:
    await set_store_context(db, store_id)
    endpoint = f"/api/v1/stores/{store_id}/environments"; record = await _begin_create(db, ctx, idempotency_key, endpoint, payload.model_dump(mode="json"))
    if isinstance(record, JSONResponse): return record
    service, _ = _service(request, ctx, db)
    try: row = await service.create_environment(store_id, payload.model_dump())
    except (PlatformPolicyError, IntegrityError) as exc: await _creation_failure(db, record, exc)
    return await _finish_create(db, record, EnvironmentResponse.model_validate(row))


@router.patch("/environments/{environment_id}", response_model=EnvironmentResponse)
async def update_environment(environment_id: UUID, payload: EnvironmentUpdate, request: Request, ctx: Annotated[TenantContext, Depends(require_permission("environment.update"))], db: Annotated[AsyncSession, Depends(get_session)]) -> EnvironmentResponse:
    service, _ = _service(request, ctx, db)
    try: row = await service.update("environment", environment_id, payload.model_dump(exclude_unset=True))
    except PlatformPolicyError as exc: await _mutation_failure(db, exc)
    await db.flush(); await db.refresh(row); response = EnvironmentResponse.model_validate(row); await db.commit(); return response


@router.post("/environments/{environment_id}/archive", response_model=EnvironmentResponse)
async def archive_environment(environment_id: UUID, request: Request, ctx: Annotated[TenantContext, Depends(require_permission("environment.archive"))], db: Annotated[AsyncSession, Depends(get_session)]) -> EnvironmentResponse:
    service, _ = _service(request, ctx, db)
    try: row = await service.archive("environment", environment_id)
    except PlatformPolicyError as exc: await _mutation_failure(db, exc)
    await db.flush(); await db.refresh(row); response = EnvironmentResponse.model_validate(row); await db.commit(); return response


@router.get("/stores/{store_id}/markets", response_model=list[MarketResponse])
async def list_markets(store_id: UUID, request: Request, ctx: Annotated[TenantContext, Depends(require_permission("market.read"))], db: Annotated[AsyncSession, Depends(get_session)]) -> list[MarketResponse]:
    return [MarketResponse.model_validate(row) for row in await _child_list("market", store_id, request, ctx, db)]


@router.post("/stores/{store_id}/markets", response_model=MarketResponse, status_code=201)
async def create_market(store_id: UUID, payload: MarketCreate, request: Request, ctx: Annotated[TenantContext, Depends(require_permission("market.create"))], db: Annotated[AsyncSession, Depends(get_session)], idempotency_key: Annotated[str, Header(alias="Idempotency-Key")]) -> Any:
    await set_store_context(db, store_id)
    endpoint = f"/api/v1/stores/{store_id}/markets"; record = await _begin_create(db, ctx, idempotency_key, endpoint, payload.model_dump(mode="json"))
    if isinstance(record, JSONResponse): return record
    service, _ = _service(request, ctx, db)
    try: row = await service.create_market(store_id, payload.model_dump())
    except (PlatformPolicyError, IntegrityError) as exc: await _creation_failure(db, record, exc)
    return await _finish_create(db, record, MarketResponse.model_validate(row))


@router.get("/markets/{market_id}", response_model=MarketResponse)
async def get_market(market_id: UUID, request: Request, ctx: Annotated[TenantContext, Depends(require_permission("market.read"))], db: Annotated[AsyncSession, Depends(get_session)]) -> MarketResponse:
    return MarketResponse.model_validate(await _child_get("market", market_id, request, ctx, db))


@router.patch("/markets/{market_id}", response_model=MarketResponse)
async def update_market(market_id: UUID, payload: MarketUpdate, request: Request, ctx: Annotated[TenantContext, Depends(require_permission("market.update"))], db: Annotated[AsyncSession, Depends(get_session)]) -> MarketResponse:
    service, _ = _service(request, ctx, db)
    try: row = await service.update("market", market_id, payload.model_dump(exclude_unset=True))
    except PlatformPolicyError as exc: await _mutation_failure(db, exc)
    await db.flush(); await db.refresh(row); response = MarketResponse.model_validate(row); await db.commit(); return response


@router.post("/markets/{market_id}/archive", response_model=MarketResponse)
async def archive_market(market_id: UUID, request: Request, ctx: Annotated[TenantContext, Depends(require_permission("market.archive"))], db: Annotated[AsyncSession, Depends(get_session)]) -> MarketResponse:
    service, _ = _service(request, ctx, db)
    try: row = await service.archive("market", market_id)
    except PlatformPolicyError as exc: await _mutation_failure(db, exc)
    await db.flush(); await db.refresh(row); response = MarketResponse.model_validate(row); await db.commit(); return response


@router.get("/operations", response_model=list[OperationResponse])
async def list_operations(ctx: Annotated[TenantContext, Depends(require_permission("operation.read"))], db: Annotated[AsyncSession, Depends(get_session)]) -> list[OperationResponse]:
    rows = (await db.scalars(select(OperationModel).where(OperationModel.tenant_id == ctx.tenant_id).order_by(OperationModel.created_at.desc()).limit(100))).all()
    return [OperationResponse.model_validate(row) for row in rows]


@router.get("/operations/{operation_id}", response_model=OperationResponse)
async def get_operation(operation_id: UUID, ctx: Annotated[TenantContext, Depends(require_permission("operation.read"))], db: Annotated[AsyncSession, Depends(get_session)]) -> OperationResponse:
    row = await db.scalar(select(OperationModel).where(OperationModel.tenant_id == ctx.tenant_id, OperationModel.id == operation_id))
    if row is None: raise HTTPException(404, "Operation not found")
    return OperationResponse.model_validate(row)


@router.get("/platform/entitlements", response_model=list[EntitlementResponse])
async def entitlements(ctx: Annotated[TenantContext, Depends(require_permission("entitlement.read"))], db: Annotated[AsyncSession, Depends(get_session)]) -> list[EntitlementResponse]:
    rows = (await db.execute(select(EntitlementDefinitionModel, EntitlementOverrideModel).outerjoin(EntitlementOverrideModel, (EntitlementOverrideModel.key == EntitlementDefinitionModel.key) & (EntitlementOverrideModel.tenant_id == ctx.tenant_id)).order_by(EntitlementDefinitionModel.key))).all()
    return [EntitlementResponse(key=definition.key, value=override.value if override else definition.default_value, source="override" if override else "default") for definition, override in rows]


@router.put("/platform/entitlements/{key}", response_model=EntitlementResponse)
async def set_entitlement(key: str, payload: EntitlementOverrideRequest, request: Request, ctx: Annotated[TenantContext, Depends(require_permission("entitlement.manage"))], db: Annotated[AsyncSession, Depends(get_session)]) -> EntitlementResponse:
    definition = await db.get(EntitlementDefinitionModel, key)
    if definition is None: raise HTTPException(404, "Entitlement not found")
    override = await db.get(EntitlementOverrideModel, (ctx.tenant_id, key))
    before = override.value if override else definition.default_value
    if override is None:
        override = EntitlementOverrideModel(tenant_id=ctx.tenant_id, key=key, value=payload.value, updated_by=ctx.user_id)
        db.add(override)
    else:
        override.value = payload.value; override.updated_by = ctx.user_id
    await audit(db, "platform.entitlement_changed", "success", ctx.user_id, ctx.tenant_id, resource=key, metadata={"before": before, "after": payload.value, "correlation_id": str(request.state.correlation_id)})
    await db.commit()
    return EntitlementResponse(key=key, value=payload.value, source="override")


@router.get("/platform/usage", response_model=UsageResponse)
async def usage(ctx: Annotated[TenantContext, Depends(require_permission("entitlement.read"))], db: Annotated[AsyncSession, Depends(get_session)]) -> UsageResponse:
    repo = SqlAlchemyPlatformRepository(db)
    users = int(await db.scalar(select(func.count()).select_from(MembershipModel).where(MembershipModel.tenant_id == ctx.tenant_id, MembershipModel.is_active.is_(True))) or 0)
    return UsageResponse(
        stores=await repo.count_resources("store", ctx.tenant_id),
        sites=await repo.count_resources("site", ctx.tenant_id),
        channels=await repo.count_resources("channel", ctx.tenant_id),
        environments=await repo.count_resources("environment", ctx.tenant_id),
        markets=await repo.count_resources("market", ctx.tenant_id),
        users=users,
    )

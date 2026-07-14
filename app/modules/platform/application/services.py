from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.application.auth import audit
from app.modules.platform.contracts.events import EventActor, EventEnvelope
from app.modules.platform.contracts.repositories import PlatformRepository
from app.modules.platform.domain.policies import (
    PlatformPolicyError,
    QuotaExceeded,
    ensure_environment_flags,
    ensure_quota,
    ensure_store_accepts_configuration,
    ensure_store_transition,
)
from app.modules.platform.domain.values import (
    MoneyConfiguration,
    normalize_code,
    validate_country,
    validate_locale,
    validate_timezone,
)
from app.modules.platform.infrastructure.models import (
    ChannelModel,
    EnvironmentModel,
    MarketCurrencyModel,
    MarketLocaleModel,
    MarketModel,
    SiteModel,
    StoreCurrencyModel,
    StoreLocaleModel,
    StoreModel,
)


@dataclass(frozen=True, slots=True)
class PlatformActor:
    user_id: UUID
    session_id: UUID | None
    tenant_id: UUID
    correlation_id: UUID


class PlatformNotFound(PlatformPolicyError):
    pass


class PlatformService:
    def __init__(self, repository: PlatformRepository, actor: PlatformActor, audit_session: Any) -> None:
        self.repository = repository
        self.actor = actor
        self.audit_session = audit_session

    async def _quota(self, key: str, kind: str, store_id: UUID | None = None) -> None:
        limit = await self.repository.entitlement_limit(self.actor.tenant_id, key)
        current = await self.repository.count_resources(kind, self.actor.tenant_id, store_id)
        try:
            ensure_quota(key, current, limit)
        except QuotaExceeded:
            await audit(
                self.audit_session, "platform.quota_exceeded", "denied", self.actor.user_id,
                self.actor.tenant_id, resource=str(store_id) if store_id else None,
                metadata={"entitlement": key, "limit": limit, "correlation_id": str(self.actor.correlation_id)},
            )
            raise

    def _event(self, event_type: str, kind: str, resource_id: UUID, store_id: UUID | None, data: dict[str, Any]) -> EventEnvelope:
        return EventEnvelope.create(
            event_type=event_type,
            tenant_id=self.actor.tenant_id,
            store_id=store_id,
            aggregate_type=kind,
            aggregate_id=resource_id,
            correlation_id=self.actor.correlation_id,
            actor=EventActor(self.actor.user_id, self.actor.session_id),
            data=data,
        )

    async def _store_and_scope(self, store_id: UUID) -> tuple[StoreModel, Any]:
        store = await self.repository.get_store(self.actor.tenant_id, store_id, lock=True)
        if store is None:
            await audit(self.audit_session, "platform.scope_denied", "denied", self.actor.user_id, self.actor.tenant_id, resource=str(store_id), metadata={"correlation_id": str(self.actor.correlation_id)})
            raise PlatformNotFound("Store not found")
        ensure_store_accepts_configuration(store.status)
        scope = await self.repository.get_scope(self.actor.tenant_id, "store", store.id)
        if scope is None:
            raise PlatformPolicyError("Store scope is missing")
        return store, scope

    async def create_store(self, data: dict[str, Any]) -> StoreModel:
        await self._quota("stores.max", "store")
        locale = validate_locale(data["default_locale"])
        money = MoneyConfiguration.from_currency(data["default_currency"])
        timezone = validate_timezone(data["timezone"])
        store = StoreModel(
            tenant_id=self.actor.tenant_id,
            code=normalize_code(data["code"]),
            name=data["name"].strip(),
            slug=normalize_code(data["slug"]),
            status="draft",
            default_locale=locale,
            default_currency=money.currency_code,
            timezone=timezone,
            created_by=self.actor.user_id,
            updated_by=self.actor.user_id,
        )
        await self.repository.add(store)
        await self.repository.flush()
        tenant_scope = await self.repository.get_scope(self.actor.tenant_id, "tenant", self.actor.tenant_id)
        if tenant_scope is None:
            await self.repository.add_scope(self.actor.tenant_id, "tenant", self.actor.tenant_id, None)
            await self.repository.flush()
            tenant_scope = await self.repository.get_scope(self.actor.tenant_id, "tenant", self.actor.tenant_id)
        await self.repository.add_scope(self.actor.tenant_id, "store", store.id, tenant_scope.id if tenant_scope else None)
        await self.repository.add(StoreLocaleModel(tenant_id=self.actor.tenant_id, store_id=store.id, locale_code=locale, is_default=True))
        await self.repository.add(StoreCurrencyModel(tenant_id=self.actor.tenant_id, store_id=store.id, currency_code=money.currency_code, minor_unit=money.minor_unit, rounding_mode=money.rounding_mode, is_default=True))
        await self.repository.add_event(self._event("platform.store.created.v1", "store", store.id, store.id, {"code": store.code, "name": store.name, "status": store.status}))
        await audit(self.audit_session, "platform.store_created", "success", self.actor.user_id, self.actor.tenant_id, resource=str(store.id), metadata={"correlation_id": str(self.actor.correlation_id)})
        return store

    async def create_site(self, store_id: UUID, data: dict[str, Any]) -> SiteModel:
        _, scope = await self._store_and_scope(store_id)
        await self._quota("sites.max_per_store", "site", store_id)
        site = SiteModel(tenant_id=self.actor.tenant_id, store_id=store_id, code=normalize_code(data["code"]), name=data["name"].strip(), slug=normalize_code(data["slug"]), site_type=data["site_type"], status="draft", primary_domain_placeholder=data.get("primary_domain_placeholder"), created_by=self.actor.user_id, updated_by=self.actor.user_id)
        await self.repository.add(site); await self.repository.flush()
        await self.repository.add_scope(self.actor.tenant_id, "site", site.id, scope.id)
        await self.repository.add_event(self._event("platform.site.created.v1", "site", site.id, store_id, {"code": site.code, "name": site.name, "site_type": site.site_type}))
        await audit(self.audit_session, "platform.site_created", "success", self.actor.user_id, self.actor.tenant_id, resource=str(site.id), metadata={"store_id": str(store_id), "correlation_id": str(self.actor.correlation_id)})
        return site

    async def create_channel(self, store_id: UUID, data: dict[str, Any]) -> ChannelModel:
        _, scope = await self._store_and_scope(store_id)
        await self._quota("channels.max_per_store", "channel", store_id)
        channel = ChannelModel(tenant_id=self.actor.tenant_id, store_id=store_id, code=normalize_code(data["code"]), name=data["name"].strip(), channel_type=data["channel_type"], status="draft", created_by=self.actor.user_id, updated_by=self.actor.user_id)
        await self.repository.add(channel); await self.repository.flush()
        await self.repository.add_scope(self.actor.tenant_id, "channel", channel.id, scope.id)
        await self.repository.add_event(self._event("platform.channel.created.v1", "channel", channel.id, store_id, {"code": channel.code, "name": channel.name, "channel_type": channel.channel_type}))
        await audit(self.audit_session, "platform.channel_created", "success", self.actor.user_id, self.actor.tenant_id, resource=str(channel.id), metadata={"store_id": str(store_id), "correlation_id": str(self.actor.correlation_id)})
        return channel

    async def create_environment(self, store_id: UUID, data: dict[str, Any]) -> EnvironmentModel:
        _, scope = await self._store_and_scope(store_id)
        await self._quota("environments.max_per_store", "environment", store_id)
        is_production = data["environment_type"] == "production"
        ensure_environment_flags(data["environment_type"], is_production)
        environment = EnvironmentModel(tenant_id=self.actor.tenant_id, store_id=store_id, code=normalize_code(data["code"]), name=data["name"].strip(), environment_type=data["environment_type"], is_production=is_production, status="active", created_by=self.actor.user_id, updated_by=self.actor.user_id)
        await self.repository.add(environment); await self.repository.flush()
        await self.repository.add_scope(self.actor.tenant_id, "environment", environment.id, scope.id)
        await self.repository.add_event(self._event("platform.environment.created.v1", "environment", environment.id, store_id, {"code": environment.code, "name": environment.name, "environment_type": environment.environment_type}))
        await audit(self.audit_session, "platform.environment_created", "success", self.actor.user_id, self.actor.tenant_id, resource=str(environment.id), metadata={"store_id": str(store_id), "correlation_id": str(self.actor.correlation_id)})
        return environment

    async def create_market(self, store_id: UUID, data: dict[str, Any]) -> MarketModel:
        _, scope = await self._store_and_scope(store_id)
        await self._quota("markets.max_per_store", "market", store_id)
        locale = validate_locale(data["default_locale"])
        country = validate_country(data["country_code"])
        money = MoneyConfiguration.from_currency(data["currency_code"])
        timezone = validate_timezone(data["timezone"])
        market = MarketModel(tenant_id=self.actor.tenant_id, store_id=store_id, code=normalize_code(data["code"]), name=data["name"].strip(), country_code=country, currency_code=money.currency_code, default_locale=locale, timezone=timezone, status="draft", created_by=self.actor.user_id, updated_by=self.actor.user_id)
        await self.repository.add(market); await self.repository.flush()
        await self.repository.add_scope(self.actor.tenant_id, "market", market.id, scope.id)
        await self.repository.add(MarketLocaleModel(tenant_id=self.actor.tenant_id, market_id=market.id, locale_code=locale, is_default=True))
        await self.repository.add(MarketCurrencyModel(tenant_id=self.actor.tenant_id, market_id=market.id, currency_code=money.currency_code, minor_unit=money.minor_unit, rounding_mode=money.rounding_mode, is_default=True))
        await self.repository.add_event(self._event("platform.market.created.v1", "market", market.id, store_id, {"code": market.code, "name": market.name, "country_code": country, "currency_code": money.currency_code}))
        await audit(self.audit_session, "platform.market_created", "success", self.actor.user_id, self.actor.tenant_id, resource=str(market.id), metadata={"store_id": str(store_id), "correlation_id": str(self.actor.correlation_id)})
        return market

    async def update(self, kind: str, resource_id: UUID, data: dict[str, Any]) -> Any:
        resource = await self.repository.get_resource(kind, self.actor.tenant_id, resource_id)
        if resource is None:
            await audit(self.audit_session, "platform.scope_denied", "denied", self.actor.user_id, self.actor.tenant_id, resource=str(resource_id), metadata={"kind": kind, "correlation_id": str(self.actor.correlation_id)})
            raise PlatformNotFound(f"{kind.title()} not found")
        if resource.status == "archived":
            raise PlatformPolicyError("Archived resources cannot be updated")
        safe = {"name", "slug", "primary_domain_placeholder", "default_locale", "default_currency", "timezone"}
        before = {key: getattr(resource, key) for key in data if key in safe and hasattr(resource, key)}
        for key, value in data.items():
            if key not in safe or value is None or not hasattr(resource, key):
                continue
            if key == "slug": value = normalize_code(value)
            if key == "default_locale": value = validate_locale(value)
            if key == "default_currency": value = MoneyConfiguration.from_currency(value).currency_code
            if key == "timezone": value = validate_timezone(value)
            setattr(resource, key, value.strip() if isinstance(value, str) else value)
        resource.updated_by = self.actor.user_id
        await self.repository.add_event(self._event(f"platform.{kind}.updated.v1", kind, resource.id, resource.id if kind == "store" else resource.store_id, {"changes": sorted(before)}))
        await audit(self.audit_session, f"platform.{kind}_updated", "success", self.actor.user_id, self.actor.tenant_id, resource=str(resource.id), metadata={"before": before, "correlation_id": str(self.actor.correlation_id)})
        return resource

    async def transition_store(self, store_id: UUID, target: str) -> StoreModel:
        store = await self.repository.get_store(self.actor.tenant_id, store_id, lock=True)
        if store is None:
            await audit(self.audit_session, "platform.scope_denied", "denied", self.actor.user_id, self.actor.tenant_id, resource=str(store_id), metadata={"kind": "store", "correlation_id": str(self.actor.correlation_id)})
            raise PlatformNotFound("Store not found")
        ensure_store_transition(store.status, target)
        store.status = target; store.updated_by = self.actor.user_id
        if target == "archived": store.archived_at = datetime.now(UTC)
        event_action = {"active": "activated", "suspended": "suspended", "archived": "archived"}[target]
        await self.repository.add_event(self._event(f"platform.store.{event_action}.v1", "store", store.id, store.id, {"status": target}))
        await audit(self.audit_session, f"platform.store_{event_action}", "success", self.actor.user_id, self.actor.tenant_id, resource=str(store.id), metadata={"correlation_id": str(self.actor.correlation_id)})
        return store

    async def archive(self, kind: str, resource_id: UUID) -> Any:
        resource = await self.repository.get_resource(kind, self.actor.tenant_id, resource_id)
        if resource is None:
            await audit(self.audit_session, "platform.scope_denied", "denied", self.actor.user_id, self.actor.tenant_id, resource=str(resource_id), metadata={"kind": kind, "correlation_id": str(self.actor.correlation_id)})
            raise PlatformNotFound(f"{kind.title()} not found")
        if resource.status != "archived":
            resource.status = "archived"; resource.archived_at = datetime.now(UTC); resource.updated_by = self.actor.user_id
            scope = await self.repository.get_scope(self.actor.tenant_id, kind, resource.id)
            if scope: scope.status = "archived"
            await self.repository.add_event(self._event(f"platform.{kind}.archived.v1", kind, resource.id, resource.store_id, {"status": "archived"}))
            await audit(self.audit_session, f"platform.{kind}_archived", "success", self.actor.user_id, self.actor.tenant_id, resource=str(resource.id), metadata={"correlation_id": str(self.actor.correlation_id)})
        return resource

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.infrastructure.database import SessionFactory
from app.infrastructure.models import AuditLogModel
from app.infrastructure.tenant_context import set_tenant_context
from app.modules.platform.application.messaging import (
    DurableOperationConsumer,
    InternalEventPublisher,
    OutboxDispatcher,
)
from app.modules.platform.infrastructure.models import (
    MarketLocaleModel,
    OutboxEventModel,
    ResourceScopeModel,
    StoreCurrencyModel,
    StoreLocaleModel,
)

pytestmark = pytest.mark.integration


async def platform_context(client, registration):
    registered = await client.post("/api/v1/auth/register", json=registration)
    tenant = registered.json()["tenant"]
    login = await client.post("/api/v1/auth/login", json={"email": registration["email"], "password": registration["password"]})
    selected = await client.post("/api/v1/auth/select-tenant", headers={"Authorization": f"Bearer {login.json()['access_token']}"}, json={"tenant_id": tenant["id"]})
    return {"Authorization": f"Bearer {selected.json()['access_token']}"}, tenant


def store_payload(**changes):
    return {"code": "main", "name": "Main Store", "slug": "main-store", "default_locale": "es-EC", "default_currency": "USD", "timezone": "America/Guayaquil", **changes}


async def create_store(client, headers, **changes):
    return await client.post("/api/v1/stores", headers={**headers, "Idempotency-Key": str(uuid4())}, json=store_payload(**changes))


async def test_store_lifecycle_idempotency_outbox_and_correlation(client, registration):
    headers, tenant = await platform_context(client, registration)
    correlation = str(uuid4())
    key = str(uuid4())
    created = await client.post("/api/v1/stores", headers={**headers, "Idempotency-Key": key, "X-Correlation-ID": correlation}, json=store_payload())
    assert created.status_code == 201
    assert created.headers["X-Correlation-ID"] == correlation
    store = created.json()
    replay = await client.post("/api/v1/stores", headers={**headers, "Idempotency-Key": key}, json=store_payload())
    assert replay.status_code == 201 and replay.json()["id"] == store["id"]
    assert replay.headers["Idempotency-Replayed"] == "true"
    conflict = await client.post("/api/v1/stores", headers={**headers, "Idempotency-Key": key}, json=store_payload(name="Changed"))
    assert conflict.status_code == 409
    assert len((await client.get("/api/v1/stores", headers=headers)).json()) == 1
    updated = await client.patch(f"/api/v1/stores/{store['id']}", headers=headers, json={"name": "Renamed"})
    assert updated.status_code == 200 and updated.json()["name"] == "Renamed"
    assert (await client.post(f"/api/v1/stores/{store['id']}/activate", headers=headers)).json()["status"] == "active"
    assert (await client.post(f"/api/v1/stores/{store['id']}/suspend", headers=headers)).json()["status"] == "suspended"
    assert (await client.post(f"/api/v1/stores/{store['id']}/archive", headers=headers)).json()["status"] == "archived"
    rejected = await client.post(f"/api/v1/stores/{store['id']}/sites", headers={**headers, "Idempotency-Key": str(uuid4())}, json={"code": "site", "name": "Site", "slug": "site", "site_type": "commerce"})
    assert rejected.status_code == 400
    async with SessionFactory() as db:
        await set_tenant_context(db, tenant["id"])
        events = (await db.scalars(select(OutboxEventModel).where(OutboxEventModel.tenant_id == tenant["id"]))).all()
        scopes = (await db.scalars(select(ResourceScopeModel).where(ResourceScopeModel.tenant_id == tenant["id"]))).all()
        assert {event.event_type for event in events} >= {"platform.store.created.v1", "platform.store.activated.v1", "platform.store.archived.v1"}
        assert {scope.scope_type for scope in scopes} >= {"tenant", "store"}


async def test_sites_channels_environments_markets_and_operations(client, registration):
    headers, tenant = await platform_context(client, registration)
    store = (await create_store(client, headers)).json(); store_id = store["id"]
    site = await client.post(f"/api/v1/stores/{store_id}/sites", headers={**headers, "Idempotency-Key": str(uuid4())}, json={"code": "web", "name": "Website", "slug": "website", "site_type": "commerce", "primary_domain_placeholder": "example.com"})
    channel = await client.post(f"/api/v1/stores/{store_id}/channels", headers={**headers, "Idempotency-Key": str(uuid4())}, json={"code": "web", "name": "Web", "channel_type": "web"})
    environment = await client.post(f"/api/v1/stores/{store_id}/environments", headers={**headers, "Idempotency-Key": str(uuid4())}, json={"code": "production", "name": "Production", "environment_type": "production"})
    market = await client.post(f"/api/v1/stores/{store_id}/markets", headers={**headers, "Idempotency-Key": str(uuid4())}, json={"code": "ecuador", "name": "Ecuador", "country_code": "EC", "currency_code": "USD", "default_locale": "es-EC", "timezone": "America/Guayaquil"})
    assert [site.status_code, channel.status_code, environment.status_code, market.status_code] == [201, 201, 201, 201]
    duplicate_production = await client.post(f"/api/v1/stores/{store_id}/environments", headers={**headers, "Idempotency-Key": str(uuid4())}, json={"code": "prod-2", "name": "Second", "environment_type": "production"})
    assert duplicate_production.status_code == 409
    assert len((await client.get(f"/api/v1/stores/{store_id}/sites", headers=headers)).json()) == 1
    assert (await client.get(f"/api/v1/channels/{channel.json()['id']}", headers=headers)).status_code == 200
    assert (await client.patch(f"/api/v1/markets/{market.json()['id']}", headers=headers, json={"name": "Ecuador Retail"})).json()["name"] == "Ecuador Retail"
    async with SessionFactory() as db:
        dispatcher = OutboxDispatcher(db, InternalEventPublisher(DurableOperationConsumer(db)))
        assert await dispatcher.dispatch(uuid4() if False else __import__('uuid').UUID(tenant["id"])) >= 4
    operations = await client.get("/api/v1/operations", headers=headers)
    assert operations.status_code == 200 and len(operations.json()) >= 4
    assert (await client.get(f"/api/v1/operations/{operations.json()[0]['id']}", headers=headers)).status_code == 200


async def test_secondary_store_resources_are_independently_editable(client, registration):
    headers, _ = await platform_context(client, registration)
    primary = (await create_store(client, headers, code="primary", name="Primary", slug="primary")).json()
    secondary = (await create_store(client, headers, code="secondary", name="Secondary", slug="secondary")).json()

    async def create_children(store_id, suffix):
        common = {**headers, "Idempotency-Key": str(uuid4())}
        site = await client.post(
            f"/api/v1/stores/{store_id}/sites",
            headers=common,
            json={
                "code": "web",
                "name": f"Site {suffix}",
                "slug": f"site-{suffix}",
                "site_type": "commerce",
                "primary_domain_placeholder": f"{suffix}.example.com",
            },
        )
        channel = await client.post(
            f"/api/v1/stores/{store_id}/channels",
            headers={**headers, "Idempotency-Key": str(uuid4())},
            json={"code": "web", "name": f"Channel {suffix}", "channel_type": "web"},
        )
        environment = await client.post(
            f"/api/v1/stores/{store_id}/environments",
            headers={**headers, "Idempotency-Key": str(uuid4())},
            json={"code": "staging", "name": f"Environment {suffix}", "environment_type": "staging"},
        )
        market = await client.post(
            f"/api/v1/stores/{store_id}/markets",
            headers={**headers, "Idempotency-Key": str(uuid4())},
            json={"code": "ec", "name": f"Market {suffix}", "country_code": "EC", "currency_code": "USD", "default_locale": "es-EC", "timezone": "America/Guayaquil"},
        )
        assert [site.status_code, channel.status_code, environment.status_code, market.status_code] == [201, 201, 201, 201]
        return site.json(), channel.json(), environment.json(), market.json()

    primary_children = await create_children(primary["id"], "primary")
    secondary_children = await create_children(secondary["id"], "secondary")

    renamed_store = await client.patch(
        f"/api/v1/stores/{secondary['id']}",
        headers=headers,
        json={
            "name": "Secondary renamed",
            "slug": "secondary-renamed",
            "default_locale": "en-US",
            "default_currency": "EUR",
        },
    )
    assert renamed_store.status_code == 200
    assert renamed_store.json()["name"] == "Secondary renamed"
    assert renamed_store.json()["default_locale"] == "en-US"
    assert renamed_store.json()["default_currency"] == "EUR"

    async with SessionFactory() as db:
        await set_tenant_context(db, UUID(secondary["tenant_id"]))
        locale = await db.scalar(
            select(StoreLocaleModel).where(
                StoreLocaleModel.store_id == UUID(secondary["id"]), StoreLocaleModel.is_default.is_(True)
            )
        )
        currency = await db.scalar(
            select(StoreCurrencyModel).where(
                StoreCurrencyModel.store_id == UUID(secondary["id"]), StoreCurrencyModel.is_default.is_(True)
            )
        )
        assert locale is not None and locale.locale_code == "en-US"
        assert currency is not None and currency.currency_code == "EUR"

    paths = ("sites", "channels", "environments", "markets")
    for path, primary_child, secondary_child in zip(paths, primary_children, secondary_children, strict=True):
        payload = {"name": f"Updated {path}"}
        if path == "sites":
            payload["primary_domain_placeholder"] = None
        if path == "markets":
            payload["default_locale"] = "en-US"
        updated = await client.patch(
            f"/api/v1/{path}/{secondary_child['id']}", headers=headers, json=payload
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == f"Updated {path}"
        if path == "sites":
            assert updated.json()["primary_domain_placeholder"] is None
        primary_list = await client.get(f"/api/v1/stores/{primary['id']}/{path}", headers=headers)
        secondary_list = await client.get(f"/api/v1/stores/{secondary['id']}/{path}", headers=headers)
        assert {item["id"] for item in primary_list.json()} == {primary_child["id"]}
        assert {item["id"] for item in secondary_list.json()} == {secondary_child["id"]}
        assert primary_list.json()[0]["name"].endswith("primary")
        assert secondary_list.json()[0]["name"] == f"Updated {path}"

    async with SessionFactory() as db:
        await set_tenant_context(db, UUID(secondary["tenant_id"]))
        market_locale = await db.scalar(
            select(MarketLocaleModel).where(
                MarketLocaleModel.market_id == UUID(secondary_children[3]["id"]),
                MarketLocaleModel.is_default.is_(True),
            )
        )
        assert market_locale is not None and market_locale.locale_code == "en-US"

    unchanged_primary = await client.get(f"/api/v1/stores/{primary['id']}", headers=headers)
    assert unchanged_primary.json()["name"] == "Primary"


async def test_quota_usage_cross_tenant_and_readiness(client, registration):
    headers, tenant = await platform_context(client, registration)
    other_registration = {**registration, "email": "other-platform@example.com", "company": "Other Platform"}
    other_headers, _ = await platform_context(client, other_registration)
    foreign = (await create_store(client, other_headers, code="foreign", slug="foreign")).json()
    assert (await client.get(f"/api/v1/stores/{foreign['id']}", headers=headers)).status_code == 404
    async with SessionFactory() as db:
        denied = await db.scalar(
            select(AuditLogModel).where(
                AuditLogModel.tenant_id == tenant["id"],
                AuditLogModel.action == "platform.scope_denied",
                AuditLogModel.resource == foreign["id"],
            )
        )
        assert denied is not None and denied.result == "denied"
    override = await client.put("/api/v1/platform/entitlements/stores.max", headers=headers, json={"value": 1})
    assert override.status_code == 200 and override.json()["source"] == "override"
    assert (await create_store(client, headers)).status_code == 201
    quota_key = str(uuid4())
    limited = await client.post(
        "/api/v1/stores",
        headers={**headers, "Idempotency-Key": quota_key},
        json=store_payload(code="second", slug="second"),
    )
    assert limited.status_code == 409 and "stores.max" in limited.text
    replayed_limit = await client.post(
        "/api/v1/stores",
        headers={**headers, "Idempotency-Key": quota_key},
        json=store_payload(code="second", slug="second"),
    )
    assert replayed_limit.status_code == 409
    assert replayed_limit.json() == limited.json()
    assert replayed_limit.headers["Idempotency-Replayed"] == "true"
    entitlements = await client.get("/api/v1/platform/entitlements", headers=headers)
    usage = await client.get("/api/v1/platform/usage", headers=headers)
    assert next(item for item in entitlements.json() if item["key"] == "stores.max")["source"] == "override"
    assert usage.json()["stores"] == 1
    viewer = next(role for role in (await client.get("/api/v1/roles", headers=headers)).json() if role["name"] == "viewer")
    invitation = await client.post("/api/v1/members/invitations", headers=headers, json={"email": "quota-user@example.com", "role_ids": [viewer["id"]]})
    await client.put("/api/v1/platform/entitlements/users.max", headers=headers, json={"value": 1})
    rejected_user = await client.post("/api/v1/members/invitations/accept", json={"token": invitation.json()["invitation_token"], "password": "Quota-User-99", "full_name": "Quota User"})
    assert rejected_user.status_code == 409 and "users.max" in rejected_user.text
    assert (await client.get("/health")).status_code == 200
    assert (await client.get("/ready")).status_code == 200
    assert (await client.get("/health", headers={"X-Correlation-ID": "not-valid"})).status_code == 400

"""RBAC denial and quota enforcement for M3.2 Catalog Attributes -- real
PostgreSQL, no mocks."""

from uuid import uuid4

import pytest

from app.infrastructure.database import SessionFactory
from app.infrastructure.tenant_context import set_tenant_context
from app.modules.platform.infrastructure.runtime_models import EntitlementOverrideModel
from tests.integration.test_catalog_api import catalog_context
from tests.integration.test_catalog_attributes_api import create_attribute

pytestmark = pytest.mark.integration


async def _register_viewer(client, headers, tenant):
    viewer = next(
        role for role in (await client.get("/api/v1/roles", headers=headers)).json() if role["name"] == "viewer"
    )
    invitation = await client.post(
        "/api/v1/members/invitations",
        headers=headers,
        json={"email": "attributes-viewer@example.com", "role_ids": [viewer["id"]]},
    )
    assert invitation.status_code == 201, invitation.text
    accepted = await client.post(
        "/api/v1/members/invitations/accept",
        json={
            "token": invitation.json()["invitation_token"],
            "password": "Attributes-Viewer-99",
            "full_name": "Attributes Viewer",
        },
    )
    assert accepted.status_code == 200, accepted.text
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "attributes-viewer@example.com", "password": "Attributes-Viewer-99"},
    )
    selected = await client.post(
        "/api/v1/auth/select-tenant",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        json={"tenant_id": tenant["id"]},
    )
    assert selected.status_code == 200, selected.text
    return {"Authorization": f"Bearer {selected.json()['access_token']}"}


async def test_viewer_can_read_attributes_but_cannot_create_them(client, registration):
    headers, tenant = await catalog_context(client, registration)
    await create_attribute(client, headers, code="power", data_type="DECIMAL")
    viewer_headers = await _register_viewer(client, headers, tenant)

    allowed = await client.get("/api/v1/catalog/attributes", headers=viewer_headers)
    assert allowed.status_code == 200

    forbidden = await client.post(
        "/api/v1/catalog/attributes",
        headers={**viewer_headers, "Idempotency-Key": str(uuid4())},
        json={"code": "denied", "name": "Denied", "data_type": "TEXT"},
    )
    assert forbidden.status_code == 403, forbidden.text


async def test_attribute_options_quota_is_enforced(client, registration):
    headers, tenant = await catalog_context(client, registration)
    attribute = await create_attribute(client, headers, code="material", data_type="SELECT")

    async with SessionFactory() as db:
        await set_tenant_context(db, tenant["id"])
        db.add(
            EntitlementOverrideModel(
                tenant_id=tenant["id"], key="catalog.attribute_options.max_per_attribute", value=1
            )
        )
        await db.commit()

    first = await client.post(
        f"/api/v1/catalog/attributes/{attribute['id']}/options",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"code": "aluminium", "label": "Aluminium"},
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        f"/api/v1/catalog/attributes/{attribute['id']}/options",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"code": "steel", "label": "Steel"},
    )
    assert second.status_code == 409, second.text

from urllib.parse import parse_qs, urlparse

import pyotp
import pytest

from app.infrastructure.database import SessionFactory
from app.infrastructure.tenant_context import clear_tenant_context, set_tenant_context

pytestmark=pytest.mark.integration
async def test_two_factor_setup_login_recovery_and_session_management(client,registration):
    await client.post("/api/v1/auth/register",json=registration)
    login=await client.post("/api/v1/auth/login",json={"email":registration["email"],"password":registration["password"]})
    access=login.json()["access_token"]; headers={"Authorization":f"Bearer {access}"}
    sessions=await client.get("/api/v1/auth/sessions",headers=headers); assert sessions.status_code==200 and len(sessions.json())==1
    setup=await client.post("/api/v1/auth/2fa/setup",headers=headers); assert setup.status_code==200
    secret=parse_qs(urlparse(setup.json()["provisioning_uri"]).query)["secret"][0]; code=pyotp.TOTP(secret).now()
    enabled=await client.post("/api/v1/auth/2fa/enable",headers=headers,json={"code":code}); assert enabled.status_code==200
    recovery=enabled.json()["recovery_codes"][0]
    await client.post("/api/v1/auth/logout-all",headers={**headers,"Origin":"http://testserver","X-CSRF-Token":client.cookies["csrf_token"]})
    challenged=await client.post("/api/v1/auth/login",json={"email":registration["email"],"password":registration["password"]}); assert challenged.json()["requires_two_factor"]
    challenge=challenged.json()["challenge_token"]
    assert (await client.post("/api/v1/auth/2fa/verify",json={"challenge_token":challenge,"code":"000000"})).status_code==401
    recovered=await client.post("/api/v1/auth/2fa/verify",json={"challenge_token":challenge,"code":recovery}); assert recovered.status_code==200
    assert (await client.post("/api/v1/auth/2fa/verify",json={"challenge_token":challenge,"code":recovery})).status_code==401
    new_headers={"Authorization":f"Bearer {recovered.json()['access_token']}"}
    rows=(await client.get("/api/v1/auth/sessions",headers=new_headers)).json(); assert rows
    assert (await client.delete(f"/api/v1/auth/sessions/{rows[0]['id']}",headers=new_headers)).status_code==204
async def test_tenant_context_is_transaction_local(registration):
    from uuid import uuid4
    async with SessionFactory() as db:
        tenant_id=uuid4(); await set_tenant_context(db,tenant_id)
        value=await db.scalar(__import__('sqlalchemy').text("SELECT current_setting('app.current_tenant_id',true)")); assert value==str(tenant_id)
        await clear_tenant_context(db); assert not db.in_transaction()

async def test_recovery_regeneration_and_2fa_disable(client,registration):
    await client.post("/api/v1/auth/register",json=registration)
    login=await client.post("/api/v1/auth/login",json={"email":registration["email"],"password":registration["password"]}); headers={"Authorization":f"Bearer {login.json()['access_token']}"}
    setup=await client.post("/api/v1/auth/2fa/setup",headers=headers); secret=parse_qs(urlparse(setup.json()["provisioning_uri"]).query)["secret"][0]
    enabled=await client.post("/api/v1/auth/2fa/enable",headers=headers,json={"code":pyotp.TOTP(secret).now()}); old=set(enabled.json()["recovery_codes"])
    csrf={**headers,"Origin":"http://testserver","X-CSRF-Token":client.cookies["csrf_token"]}; payload={"password":registration["password"],"code":pyotp.TOTP(secret).now()}
    regenerated=await client.post("/api/v1/auth/2fa/recovery-codes/regenerate",headers=csrf,json=payload); assert regenerated.status_code==200 and old.isdisjoint(regenerated.json()["recovery_codes"])
    disabled=await client.post("/api/v1/auth/2fa/disable",headers=csrf,json=payload); assert disabled.status_code==204
    normal=await client.post("/api/v1/auth/login",json={"email":registration["email"],"password":registration["password"]}); assert not normal.json()["requires_two_factor"]

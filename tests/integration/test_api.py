import pytest
from sqlalchemy import select

from app.infrastructure.database import SessionFactory
from app.infrastructure.models import AuditLogModel, MembershipModel

pytestmark=pytest.mark.integration
async def register_and_login(client,data):
    assert (await client.post("/api/v1/auth/register",json=data)).status_code==201
    response=await client.post("/api/v1/auth/login",json={"email":data["email"],"password":data["password"]})
    assert response.status_code==200 and response.cookies.get("refresh_token")
    return response
async def test_registration_duplicate_normalization_and_login(client,registration):
    weak={**registration,"email":"weak@example.com","password":"aaaaaaaaaaaa"}; assert (await client.post("/api/v1/auth/register",json=weak)).status_code==422
    first=await client.post("/api/v1/auth/register",json=registration); assert first.status_code==201
    assert first.json()["user"]["email"]=="owner@example.com"
    assert (await client.post("/api/v1/auth/register",json=registration)).status_code==409
    assert (await client.post("/api/v1/auth/login",json={"email":"owner@example.com","password":"wrong-password"})).status_code==401
    ok=await client.post("/api/v1/auth/login",json={"email":"OWNER@example.com","password":registration["password"]}); assert ok.status_code==200
async def test_refresh_rotation_reuse_logout_and_audit(client,registration):
    login=await register_and_login(client,registration); token_a=login.cookies["refresh_token"]
    csrf={"Origin":"http://testserver","X-CSRF-Token":client.cookies["csrf_token"]}; rotated=await client.post("/api/v1/auth/refresh",headers=csrf); assert rotated.status_code==200
    token_b=rotated.cookies["refresh_token"]; assert token_a!=token_b; csrf["X-CSRF-Token"]=client.cookies["csrf_token"]
    client.cookies.set("refresh_token",token_a,path="/api/v1/auth")
    reused=await client.post("/api/v1/auth/refresh",headers=csrf); assert reused.status_code==401
    client.cookies.set("refresh_token",token_b,path="/api/v1/auth")
    assert (await client.post("/api/v1/auth/refresh",headers=csrf)).status_code==401
    async with SessionFactory() as db:
        rows=(await db.scalars(select(AuditLogModel).where(AuditLogModel.action=="auth.refresh_reuse"))).all(); assert len(rows)==1
async def test_tenant_selection_valid_foreign_and_inactive(client,registration):
    login=await register_and_login(client,registration); access=login.json()["access_token"]; headers={"Authorization":f"Bearer {access}"}
    tenants=await client.get("/api/v1/me/tenants",headers=headers); tenant_id=tenants.json()[0]["id"]
    selected=await client.post("/api/v1/auth/select-tenant",headers=headers,json={"tenant_id":tenant_id}); assert selected.status_code==200
    context=await client.get("/api/v1/me/context",headers={"Authorization":f"Bearer {selected.json()['access_token']}"}); assert context.status_code==200 and "owner" in context.json()["roles"]
    from uuid import uuid4
    assert (await client.post("/api/v1/auth/select-tenant",headers=headers,json={"tenant_id":str(uuid4())})).status_code==403
    async with SessionFactory() as db:
        m=await db.scalar(select(MembershipModel)); m.is_active=False; await db.commit()
    assert (await client.post("/api/v1/auth/select-tenant",headers=headers,json={"tenant_id":tenant_id})).status_code==403

async def test_logout_revokes_current_session_and_clears_cookie(client,registration):
    login=await register_and_login(client,registration); headers={"Authorization":f"Bearer {login.json()['access_token']}","Origin":"http://testserver","X-CSRF-Token":client.cookies["csrf_token"]}
    response=await client.post("/api/v1/auth/logout",headers=headers); assert response.status_code==204 and response.cookies.get("refresh_token") is None
    client.cookies.set("refresh_token",login.cookies["refresh_token"],path="/api/v1/auth")
    assert (await client.post("/api/v1/auth/refresh",headers={"Origin":"http://testserver","X-CSRF-Token":client.cookies.get("csrf_token","")})).status_code in (401,403)

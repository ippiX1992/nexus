import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.infrastructure.database import SessionFactory
from app.infrastructure.models import AuditLogModel, RefreshTokenModel
from app.main import app

pytestmark=pytest.mark.integration
async def test_simultaneous_refresh_allows_one_success_and_revokes_family(client,registration):
    await client.post("/api/v1/auth/register",json=registration)
    login=await client.post("/api/v1/auth/login",json={"email":registration["email"],"password":registration["password"]}); token=login.cookies["refresh_token"]; csrf=login.cookies["csrf_token"]
    async def rotate():
        async with AsyncClient(transport=ASGITransport(app=app),base_url="http://testserver") as c:
            c.cookies.set("refresh_token",token,path="/api/v1/auth"); c.cookies.set("csrf_token",csrf,path="/"); return await c.post("/api/v1/auth/refresh",headers={"Origin":"http://testserver","X-CSRF-Token":csrf})
    first,second=await asyncio.gather(rotate(),rotate()); assert sorted([first.status_code,second.status_code])==[200,401]
    async with SessionFactory() as db:
        active=(await db.scalars(select(RefreshTokenModel).where(RefreshTokenModel.revoked_at.is_(None)))).all(); assert active==[]
        events=(await db.scalars(select(AuditLogModel).where(AuditLogModel.action=="auth.refresh_reuse"))).all(); assert len(events)==1

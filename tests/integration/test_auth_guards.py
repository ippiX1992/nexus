import pytest
from sqlalchemy import select

from app.infrastructure.database import SessionFactory
from app.infrastructure.models import UserModel

pytestmark=pytest.mark.integration
async def test_authentication_and_context_guards(client,registration):
    assert (await client.get("/api/v1/me")).status_code==401
    assert (await client.get("/api/v1/me",headers={"Authorization":"Bearer invalid"})).status_code==401
    await client.post("/api/v1/auth/register",json=registration); login=await client.post("/api/v1/auth/login",json={"email":registration["email"],"password":registration["password"]}); access=login.json()["access_token"]; headers={"Authorization":f"Bearer {access}"}
    assert (await client.get("/api/v1/me/context",headers=headers)).status_code==409
    async with SessionFactory() as db:
        user=await db.scalar(select(UserModel).where(UserModel.email==registration["email"].casefold())); user.is_active=False; await db.commit()
    assert (await client.get("/api/v1/me",headers=headers)).status_code==401

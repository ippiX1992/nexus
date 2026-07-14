from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.application.auth import AuthError, revoke_session, rotate_refresh
from app.core.config import Settings
from app.core.security import create_token, token_hash
from app.infrastructure.database import SessionFactory
from app.infrastructure.models import RefreshTokenModel, UserModel

pytestmark=pytest.mark.integration
async def test_refresh_rejects_missing_revoked_and_expired_rows(registration,client):
    await client.post("/api/v1/auth/register",json=registration); settings=Settings(jwt_secret="integration-test-secret-at-least-32-characters")
    async with SessionFactory() as db:
        user=await db.scalar(select(UserModel)); uid=user.id; missing,_,_=create_token(uid,"refresh",settings)
        with pytest.raises(AuthError,match="Invalid"): await rotate_refresh(db,missing,settings)
        await db.rollback(); raw,expires,jti=create_token(uid,"refresh",settings); revoked=RefreshTokenModel(id=jti,user_id=uid,family_id=uuid4(),token_hash=token_hash(raw),expires_at=expires,revoked_at=datetime.now(UTC),revocation_reason="logout"); db.add(revoked); await db.commit()
        with pytest.raises(AuthError,match="revoked"): await rotate_refresh(db,raw,settings)
        await db.rollback(); raw2,_,jti2=create_token(uid,"refresh",settings); expired=RefreshTokenModel(id=jti2,user_id=uid,family_id=uuid4(),token_hash=token_hash(raw2),expires_at=datetime.now(UTC)-timedelta(seconds=1)); db.add(expired); await db.commit()
        with pytest.raises(AuthError,match="expired"): await rotate_refresh(db,raw2,settings)
        await db.rollback(); await revoke_session(db,uid,uuid4()); await db.rollback()

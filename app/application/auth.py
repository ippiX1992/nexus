from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import delete, select, update

from app.application.authorization import PERMISSIONS, ROLE_PERMISSIONS, SYSTEM_ROLES
from app.core.security import (
    create_token,
    decode_token,
    decrypt_secret,
    encrypt_secret,
    generate_recovery_codes,
    hash_recovery_code,
    new_totp_secret,
    token_hash,
    totp_uri,
    verify_recovery_code,
    verify_totp,
)
from app.infrastructure.models import (
    AuditLogModel,
    PermissionModel,
    RecoveryCodeModel,
    RefreshTokenModel,
    RoleModel,
    RolePermissionModel,
)


class AuthError(Exception): pass
class ReuseDetected(AuthError): pass
async def audit(db,action,result,actor_id=None,tenant_id=None,resource=None,ip=None,user_agent=None,metadata=None):
    db.add(AuditLogModel(actor_id=actor_id,tenant_id=tenant_id,action=action,result=result,resource=resource,ip_address=ip,user_agent=user_agent,metadata_json=metadata or {}))
async def seed_rbac(db,tenant_id):
    permissions={}
    for code in PERMISSIONS:
        p=await db.scalar(select(PermissionModel).where(PermissionModel.code==code))
        if not p: p=PermissionModel(code=code); db.add(p); await db.flush()
        permissions[code]=p
    roles={}
    for name in SYSTEM_ROLES:
        role=RoleModel(tenant_id=tenant_id,name=name,is_system=True); db.add(role); await db.flush(); roles[name]=role
        for code in ROLE_PERMISSIONS[name]: db.add(RolePermissionModel(role_id=role.id,permission_id=permissions[code].id))
    return roles
async def issue_session(db,user,settings,ip=None,user_agent=None):
    active=(await db.scalars(select(RefreshTokenModel).where(RefreshTokenModel.user_id==user.id,RefreshTokenModel.revoked_at.is_(None)).order_by(RefreshTokenModel.created_at.asc()).with_for_update())).all()
    overflow=max(0,len(active)-settings.max_active_sessions+1)
    for stale in active[:overflow]: stale.revoked_at=datetime.now(UTC); stale.revocation_reason="session_limit"

    family=uuid4(); raw,expires,jti=create_token(user.id,"refresh",settings,family_id=str(family))
    row=RefreshTokenModel(id=jti,user_id=user.id,family_id=family,token_hash=token_hash(raw),expires_at=expires,ip_address=ip,user_agent=user_agent)
    db.add(row); await db.flush(); access,access_exp,_=create_token(user.id,"access",settings,session_id=str(row.id))
    return access,access_exp,raw,row
async def rotate_refresh(db,raw,settings,ip=None,user_agent=None):
    payload=decode_token(raw,settings,"refresh"); jti=UUID(payload["jti"])
    row=await db.scalar(select(RefreshTokenModel).where(RefreshTokenModel.id==jti).with_for_update())
    if not row or row.token_hash!=token_hash(raw): raise AuthError("Invalid refresh token")
    now=datetime.now(UTC)
    if row.revoked_at:
        if row.replaced_by_id:
            await db.execute(update(RefreshTokenModel).where(RefreshTokenModel.family_id==row.family_id,RefreshTokenModel.revoked_at.is_(None)).values(revoked_at=now,revocation_reason="reuse_detected"))
            await audit(db,"auth.refresh_reuse","denied",actor_id=row.user_id,ip=ip,user_agent=user_agent); raise ReuseDetected("Refresh token reuse detected")
        raise AuthError("Refresh token revoked")
    if row.expires_at<=now: raise AuthError("Refresh token expired")
    new_raw,new_exp,new_id=create_token(row.user_id,"refresh",settings,family_id=str(row.family_id))
    new=RefreshTokenModel(id=new_id,user_id=row.user_id,family_id=row.family_id,token_hash=token_hash(new_raw),expires_at=new_exp,ip_address=ip,user_agent=user_agent)
    row.revoked_at=now; row.replaced_by_id=new_id; row.revocation_reason="rotated"; db.add(new)
    access,access_exp,_=create_token(row.user_id,"access",settings,session_id=str(new.id)); await audit(db,"auth.refresh","success",actor_id=row.user_id,ip=ip,user_agent=user_agent)
    return access,access_exp,new_raw
async def revoke_session(db,user_id,session_id,reason="logout"):
    row=await db.scalar(select(RefreshTokenModel).where(RefreshTokenModel.id==session_id,RefreshTokenModel.user_id==user_id).with_for_update())
    if row and not row.revoked_at: row.revoked_at=datetime.now(UTC); row.revocation_reason=reason
async def revoke_all(db,user_id,reason="logout_all"):
    await db.execute(update(RefreshTokenModel).where(RefreshTokenModel.user_id==user_id,RefreshTokenModel.revoked_at.is_(None)).values(revoked_at=datetime.now(UTC),revocation_reason=reason))
async def begin_two_factor(db,user,settings):
    secret=new_totp_secret(); user.totp_secret_encrypted=encrypt_secret(secret,settings); return totp_uri(secret,user.email),secret
async def enable_two_factor(db,user,code,settings):
    if not user.totp_secret_encrypted or not verify_totp(decrypt_secret(user.totp_secret_encrypted,settings),code): raise AuthError("Invalid TOTP code")
    user.two_factor_enabled=True; codes=generate_recovery_codes(); await db.execute(delete(RecoveryCodeModel).where(RecoveryCodeModel.user_id==user.id))
    db.add_all([RecoveryCodeModel(user_id=user.id,code_hash=hash_recovery_code(c)) for c in codes]); return codes
async def verify_second_factor(db,user,code,settings):
    if user.totp_secret_encrypted and verify_totp(decrypt_secret(user.totp_secret_encrypted,settings),code): return True
    rows=(await db.scalars(select(RecoveryCodeModel).where(RecoveryCodeModel.user_id==user.id,RecoveryCodeModel.used_at.is_(None)))).all()
    for row in rows:
        if verify_recovery_code(code,row.code_hash): row.used_at=datetime.now(UTC); return True
    return False

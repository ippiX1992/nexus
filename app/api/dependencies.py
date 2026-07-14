from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.authorization import TenantContext
from app.core.config import Settings, get_settings
from app.core.security import decode_token
from app.infrastructure.database import get_session
from app.infrastructure.models import (
    MembershipModel,
    MembershipRoleModel,
    PermissionModel,
    RoleModel,
    RolePermissionModel,
    UserModel,
)
from app.infrastructure.tenant_context import set_tenant_context

bearer=HTTPBearer(auto_error=False)
@dataclass
class Principal: user:UserModel; payload:dict
async def get_current_user(credentials:Annotated[HTTPAuthorizationCredentials|None,Depends(bearer)],db:Annotated[AsyncSession,Depends(get_session)],settings:Annotated[Settings,Depends(get_settings)]) -> Principal:
    if not credentials: raise HTTPException(401,"Authentication required")
    try: payload=decode_token(credentials.credentials,settings,"access"); user=await db.get(UserModel,UUID(payload["sub"]))
    except (jwt.InvalidTokenError,KeyError,ValueError): raise HTTPException(401,"Invalid access token") from None
    if not user or not user.is_active: raise HTTPException(401,"Inactive user")
    return Principal(user,payload)
async def get_current_context(principal:Annotated[Principal,Depends(get_current_user)],db:Annotated[AsyncSession,Depends(get_session)]) -> TenantContext:
    p=principal.payload
    if not p.get("tenant_id") or not p.get("membership_id"): raise HTTPException(409,"Select a tenant first")
    membership=await db.scalar(select(MembershipModel).where(MembershipModel.id==UUID(p["membership_id"]),MembershipModel.user_id==principal.user.id,MembershipModel.tenant_id==UUID(p["tenant_id"]),MembershipModel.is_active.is_(True)))
    if not membership: raise HTTPException(403,"Inactive or foreign membership")
    await set_tenant_context(db,membership.tenant_id)
    rows=(await db.execute(select(RoleModel.name,PermissionModel.code).join(MembershipRoleModel,MembershipRoleModel.role_id==RoleModel.id).outerjoin(RolePermissionModel,RolePermissionModel.role_id==RoleModel.id).outerjoin(PermissionModel,PermissionModel.id==RolePermissionModel.permission_id).where(MembershipRoleModel.membership_id==membership.id))).all()
    return TenantContext(principal.user.id,membership.tenant_id,membership.id,UUID(p["session_id"]) if p.get("session_id") else None,frozenset(r[0] for r in rows),frozenset(r[1] for r in rows if r[1]))
def require_permission(*codes:str):
    async def guard(context:Annotated[TenantContext,Depends(get_current_context)]):
        if not set(codes)<=context.permissions: raise HTTPException(403,"Insufficient permissions")
        return context
    return guard

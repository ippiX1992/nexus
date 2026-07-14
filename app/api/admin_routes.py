import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin_schemas import (
    DisableTwoFactorRequest,
    InvitationAccept,
    InvitationCreate,
    InvitationResponse,
    MemberResponse,
    MemberUpdate,
    PermissionAssignment,
    RoleAssignment,
    RoleCreate,
    RoleResponse,
    RoleUpdate,
    TransferOwnershipRequest,
)
from app.api.dependencies import Principal, get_current_user, require_permission
from app.api.schemas import RecoveryCodesResponse
from app.application.auth import audit, verify_second_factor
from app.application.authorization import TenantContext
from app.core.config import Settings, get_settings
from app.core.csrf import validate_csrf
from app.core.rate_limit import enforce_rate_limit
from app.core.security import (
    decrypt_secret,
    generate_recovery_codes,
    hash_password,
    hash_recovery_code,
    token_hash,
    verify_password,
    verify_totp,
)
from app.infrastructure.database import get_session
from app.infrastructure.models import (
    InvitationModel,
    InvitationRoleModel,
    MembershipModel,
    MembershipRoleModel,
    PermissionModel,
    RecoveryCodeModel,
    RefreshTokenModel,
    RoleModel,
    RolePermissionModel,
    UserModel,
)
from app.infrastructure.tenant_context import set_tenant_context
from app.modules.platform.domain.policies import QuotaExceeded, ensure_quota
from app.modules.platform.infrastructure.repositories import SqlAlchemyPlatformRepository

router=APIRouter(prefix="/api/v1")
async def role_view(db,role):
    codes=(await db.scalars(select(PermissionModel.code).join(RolePermissionModel).where(RolePermissionModel.role_id==role.id))).all(); return RoleResponse(id=role.id,name=role.name,is_system=role.is_system,permissions=list(codes))
@router.get("/members",response_model=list[MemberResponse])
async def members(ctx:Annotated[TenantContext,Depends(require_permission("member.read"))],db:Annotated[AsyncSession,Depends(get_session)]):
    rows=(await db.execute(select(MembershipModel,UserModel).join(UserModel).where(MembershipModel.tenant_id==ctx.tenant_id))).all(); result=[]
    for m,u in rows:
        names=(await db.scalars(select(RoleModel.name).join(MembershipRoleModel).where(MembershipRoleModel.membership_id==m.id))).all(); result.append(MemberResponse(membership_id=m.id,user_id=u.id,email=u.email,full_name=u.full_name,is_active=m.is_active,roles=list(names)))
    return result
@router.post("/members/invitations",response_model=InvitationResponse,status_code=201)
async def invite(payload:InvitationCreate,settings:Annotated[Settings,Depends(get_settings)],ctx:Annotated[TenantContext,Depends(require_permission("member.invite"))],db:Annotated[AsyncSession,Depends(get_session)]):
    email=payload.email.strip().casefold(); duplicate=await db.scalar(select(InvitationModel).where(InvitationModel.tenant_id==ctx.tenant_id,InvitationModel.email==email,InvitationModel.accepted_at.is_(None),InvitationModel.cancelled_at.is_(None),InvitationModel.expires_at>datetime.now(UTC)))
    if duplicate: raise HTTPException(409,"Active invitation already exists")
    roles=(await db.scalars(select(RoleModel).where(RoleModel.id.in_(payload.role_ids),RoleModel.tenant_id==ctx.tenant_id))).all()
    if len(roles)!=len(payload.role_ids): raise HTTPException(400,"Role does not belong to tenant")
    raw=secrets.token_urlsafe(32); row=InvitationModel(tenant_id=ctx.tenant_id,email=email,token_hash=token_hash(raw),invited_by_id=ctx.user_id,expires_at=datetime.now(UTC)+timedelta(days=7)); db.add(row); await db.flush(); db.add_all([InvitationRoleModel(invitation_id=row.id,role_id=r.id) for r in roles]); await audit(db,"member.invited","success",ctx.user_id,ctx.tenant_id,resource=str(row.id)); await db.commit(); return InvitationResponse(id=row.id,email=row.email,expires_at=row.expires_at,status="pending",invitation_token=raw if settings.environment!="production" else None)
@router.post("/members/invitations/accept",response_model=MemberResponse)
async def accept_invitation(payload:InvitationAccept,db:Annotated[AsyncSession,Depends(get_session)]):
    await enforce_rate_limit(db,f"invitation_accept:{token_hash(payload.token)}",8,300); await db.commit()
    row=await db.scalar(select(InvitationModel).where(InvitationModel.token_hash==token_hash(payload.token)).with_for_update()); now=datetime.now(UTC)
    if not row or row.accepted_at or row.cancelled_at or row.expires_at<=now: raise HTTPException(400,"Invalid or expired invitation")
    await set_tenant_context(db,row.tenant_id)
    user_limit=await SqlAlchemyPlatformRepository(db).entitlement_limit(row.tenant_id,"users.max")
    active_users=int(await db.scalar(select(func.count()).select_from(MembershipModel).where(MembershipModel.tenant_id==row.tenant_id,MembershipModel.is_active.is_(True))) or 0)
    try: ensure_quota("users.max",active_users,user_limit)
    except QuotaExceeded as exc:
        await audit(db,"platform.quota_exceeded","denied",tenant_id=row.tenant_id,resource=str(row.id),metadata={"entitlement":"users.max","limit":user_limit}); await db.commit(); raise HTTPException(409,str(exc)) from exc
    user=await db.scalar(select(UserModel).where(UserModel.email==row.email))
    if user and not verify_password(payload.password,user.password_hash): raise HTTPException(401,"Invalid credentials")
    if not user: user=UserModel(email=row.email,password_hash=hash_password(payload.password),full_name=payload.full_name); db.add(user); await db.flush()
    if await db.scalar(select(MembershipModel).where(MembershipModel.user_id==user.id,MembershipModel.tenant_id==row.tenant_id)): raise HTTPException(409,"Membership already exists")
    membership=MembershipModel(user_id=user.id,tenant_id=row.tenant_id); db.add(membership); await db.flush(); role_ids=(await db.scalars(select(InvitationRoleModel.role_id).where(InvitationRoleModel.invitation_id==row.id))).all(); db.add_all([MembershipRoleModel(membership_id=membership.id,role_id=r) for r in role_ids]); row.accepted_at=now; await audit(db,"member.invitation_accepted","success",user.id,row.tenant_id,resource=str(row.id)); await db.commit(); names=(await db.scalars(select(RoleModel.name).where(RoleModel.id.in_(role_ids)))).all(); return MemberResponse(membership_id=membership.id,user_id=user.id,email=user.email,full_name=user.full_name,is_active=True,roles=list(names))
@router.post("/members/invitations/{invitation_id}/resend",response_model=InvitationResponse)
async def resend(invitation_id:UUID,settings:Annotated[Settings,Depends(get_settings)],ctx:Annotated[TenantContext,Depends(require_permission("member.invite"))],db:Annotated[AsyncSession,Depends(get_session)]):
    row=await db.scalar(select(InvitationModel).where(InvitationModel.id==invitation_id,InvitationModel.tenant_id==ctx.tenant_id).with_for_update())
    if not row or row.accepted_at or row.cancelled_at: raise HTTPException(404,"Pending invitation not found")
    raw=secrets.token_urlsafe(32); row.token_hash=token_hash(raw); row.expires_at=datetime.now(UTC)+timedelta(days=7); await audit(db,"member.invitation_resent","success",ctx.user_id,ctx.tenant_id,resource=str(row.id)); await db.commit(); return InvitationResponse(id=row.id,email=row.email,expires_at=row.expires_at,status="pending",invitation_token=raw if settings.environment!="production" else None)
@router.delete("/members/invitations/{invitation_id}",status_code=204)
async def cancel_invitation(invitation_id:UUID,ctx:Annotated[TenantContext,Depends(require_permission("member.invite"))],db:Annotated[AsyncSession,Depends(get_session)]):
    row=await db.scalar(select(InvitationModel).where(InvitationModel.id==invitation_id,InvitationModel.tenant_id==ctx.tenant_id))
    if not row: raise HTTPException(404,"Invitation not found")
    row.cancelled_at=datetime.now(UTC); await audit(db,"member.invitation_cancelled","success",ctx.user_id,ctx.tenant_id,resource=str(row.id)); await db.commit()
@router.patch("/members/{membership_id}",response_model=MemberResponse)
async def update_member(membership_id:UUID,payload:MemberUpdate,ctx:Annotated[TenantContext,Depends(require_permission("member.update"))],db:Annotated[AsyncSession,Depends(get_session)]):
    m=await db.scalar(select(MembershipModel).where(MembershipModel.id==membership_id,MembershipModel.tenant_id==ctx.tenant_id))
    if not m: raise HTTPException(404,"Member not found")
    owner=await db.scalar(select(RoleModel).where(RoleModel.tenant_id==ctx.tenant_id,RoleModel.name=="owner")); assert owner is not None; is_owner=await db.scalar(select(MembershipRoleModel).where(MembershipRoleModel.membership_id==m.id,MembershipRoleModel.role_id==owner.id))
    if is_owner and not payload.is_active:
        count=await db.scalar(select(func.count()).select_from(MembershipRoleModel).join(MembershipModel).where(MembershipRoleModel.role_id==owner.id,MembershipModel.is_active.is_(True)))
        if (count or 0)<=1: raise HTTPException(409,"Last owner cannot be deactivated")
    m.is_active=payload.is_active; await audit(db,"member.updated","success",ctx.user_id,ctx.tenant_id,resource=str(m.id)); await db.commit(); u=await db.get(UserModel,m.user_id); assert u is not None; names=(await db.scalars(select(RoleModel.name).join(MembershipRoleModel).where(MembershipRoleModel.membership_id==m.id))).all(); return MemberResponse(membership_id=m.id,user_id=u.id,email=u.email,full_name=u.full_name,is_active=m.is_active,roles=list(names))
@router.put("/members/{membership_id}/roles",status_code=204)
async def assign_roles(membership_id:UUID,payload:RoleAssignment,ctx:Annotated[TenantContext,Depends(require_permission("member.update"))],db:Annotated[AsyncSession,Depends(get_session)]):
    m=await db.scalar(select(MembershipModel).where(MembershipModel.id==membership_id,MembershipModel.tenant_id==ctx.tenant_id)); roles=(await db.scalars(select(RoleModel).where(RoleModel.id.in_(payload.role_ids),RoleModel.tenant_id==ctx.tenant_id))).all()
    if not m or len(roles)!=len(payload.role_ids): raise HTTPException(400,"Invalid member or cross-tenant role")
    owner=await db.scalar(select(RoleModel).where(RoleModel.tenant_id==ctx.tenant_id,RoleModel.name=="owner")); assert owner is not None; had_owner=bool(await db.scalar(select(MembershipRoleModel).where(MembershipRoleModel.membership_id==m.id,MembershipRoleModel.role_id==owner.id)))
    if had_owner and owner.id not in payload.role_ids:
        count=await db.scalar(select(func.count()).select_from(MembershipRoleModel).join(MembershipModel).where(MembershipRoleModel.role_id==owner.id,MembershipModel.is_active.is_(True)))
        if (count or 0)<=1: raise HTTPException(409,"Last owner cannot be demoted")
    await db.execute(delete(MembershipRoleModel).where(MembershipRoleModel.membership_id==m.id)); db.add_all([MembershipRoleModel(membership_id=m.id,role_id=r.id) for r in roles]); await audit(db,"member.roles_changed","success",ctx.user_id,ctx.tenant_id,resource=str(m.id)); await db.commit()
@router.delete("/members/{membership_id}",status_code=204)
async def remove_member(membership_id:UUID,ctx:Annotated[TenantContext,Depends(require_permission("member.remove"))],db:Annotated[AsyncSession,Depends(get_session)]):
    m=await db.scalar(select(MembershipModel).where(MembershipModel.id==membership_id,MembershipModel.tenant_id==ctx.tenant_id))
    if not m: raise HTTPException(404,"Member not found")
    owner=await db.scalar(select(RoleModel).where(RoleModel.tenant_id==ctx.tenant_id,RoleModel.name=="owner")); assert owner is not None; is_owner=await db.scalar(select(MembershipRoleModel).where(MembershipRoleModel.membership_id==m.id,MembershipRoleModel.role_id==owner.id))
    if is_owner:
        count=await db.scalar(select(func.count()).select_from(MembershipRoleModel).join(MembershipModel).where(MembershipRoleModel.role_id==owner.id,MembershipModel.is_active.is_(True)))
        if (count or 0)<=1: raise HTTPException(409,"Last owner cannot be removed")
    await db.delete(m); await audit(db,"member.removed","success",ctx.user_id,ctx.tenant_id,resource=str(m.id)); await db.commit()
@router.get("/roles",response_model=list[RoleResponse])
async def list_roles(ctx:Annotated[TenantContext,Depends(require_permission("role.read"))],db:Annotated[AsyncSession,Depends(get_session)]): return [await role_view(db,r) for r in (await db.scalars(select(RoleModel).where(RoleModel.tenant_id==ctx.tenant_id))).all()]
@router.get("/permissions",response_model=list[str])
async def permissions(ctx:Annotated[TenantContext,Depends(require_permission("role.read"))],db:Annotated[AsyncSession,Depends(get_session)]): return list((await db.scalars(select(PermissionModel.code).order_by(PermissionModel.code))).all())
@router.post("/roles",response_model=RoleResponse,status_code=201)
async def create_role(payload:RoleCreate,ctx:Annotated[TenantContext,Depends(require_permission("role.create"))],db:Annotated[AsyncSession,Depends(get_session)]):
    if await db.scalar(select(RoleModel).where(RoleModel.tenant_id==ctx.tenant_id,RoleModel.name==payload.name)): raise HTTPException(409,"Role already exists")
    perms=(await db.scalars(select(PermissionModel).where(PermissionModel.code.in_(payload.permissions)))).all()
    if len(perms)!=len(payload.permissions): raise HTTPException(400,"Unknown permission")
    if not set(payload.permissions)<=ctx.permissions: raise HTTPException(403,"Cannot grant permissions you do not hold")
    role=RoleModel(tenant_id=ctx.tenant_id,name=payload.name,is_system=False); db.add(role); await db.flush(); db.add_all([RolePermissionModel(role_id=role.id,permission_id=p.id) for p in perms]); await audit(db,"role.created","success",ctx.user_id,ctx.tenant_id,resource=str(role.id)); await db.commit(); return await role_view(db,role)
@router.get("/roles/{role_id}",response_model=RoleResponse)
async def get_role(role_id:UUID,ctx:Annotated[TenantContext,Depends(require_permission("role.read"))],db:Annotated[AsyncSession,Depends(get_session)]):
    role=await db.scalar(select(RoleModel).where(RoleModel.id==role_id,RoleModel.tenant_id==ctx.tenant_id))
    if not role: raise HTTPException(404,"Role not found")
    return await role_view(db,role)
@router.patch("/roles/{role_id}",response_model=RoleResponse)
async def update_role(role_id:UUID,payload:RoleUpdate,ctx:Annotated[TenantContext,Depends(require_permission("role.update"))],db:Annotated[AsyncSession,Depends(get_session)]):
    role=await db.scalar(select(RoleModel).where(RoleModel.id==role_id,RoleModel.tenant_id==ctx.tenant_id))
    if not role or role.is_system: raise HTTPException(400,"System roles cannot be edited")
    if payload.name: role.name=payload.name
    await audit(db,"role.updated","success",ctx.user_id,ctx.tenant_id,resource=str(role.id)); await db.commit(); return await role_view(db,role)
@router.put("/roles/{role_id}/permissions",response_model=RoleResponse)
async def set_role_permissions(role_id:UUID,payload:PermissionAssignment,ctx:Annotated[TenantContext,Depends(require_permission("role.update"))],db:Annotated[AsyncSession,Depends(get_session)]):
    role=await db.scalar(select(RoleModel).where(RoleModel.id==role_id,RoleModel.tenant_id==ctx.tenant_id))
    if not role or role.is_system: raise HTTPException(400,"System roles cannot be edited")
    perms=(await db.scalars(select(PermissionModel).where(PermissionModel.code.in_(payload.permissions)))).all()
    if len(perms)!=len(payload.permissions) or not set(payload.permissions)<=ctx.permissions: raise HTTPException(403,"Invalid or excessive permissions")
    await db.execute(delete(RolePermissionModel).where(RolePermissionModel.role_id==role.id)); db.add_all([RolePermissionModel(role_id=role.id,permission_id=p.id) for p in perms]); await audit(db,"role.permissions_changed","success",ctx.user_id,ctx.tenant_id,resource=str(role.id)); await db.commit(); return await role_view(db,role)
@router.delete("/roles/{role_id}",status_code=204)
async def delete_role(role_id:UUID,ctx:Annotated[TenantContext,Depends(require_permission("role.delete"))],db:Annotated[AsyncSession,Depends(get_session)]):
    role=await db.scalar(select(RoleModel).where(RoleModel.id==role_id,RoleModel.tenant_id==ctx.tenant_id))
    if not role or role.is_system: raise HTTPException(400,"System roles cannot be deleted")
    await db.delete(role); await audit(db,"role.deleted","success",ctx.user_id,ctx.tenant_id,resource=str(role.id)); await db.commit()
@router.post("/tenant/transfer-ownership",status_code=204)
async def transfer(request:Request,payload:TransferOwnershipRequest,principal:Annotated[Principal,Depends(get_current_user)],ctx:Annotated[TenantContext,Depends(require_permission("security.manage"))],db:Annotated[AsyncSession,Depends(get_session)],settings:Annotated[Settings,Depends(get_settings)]):
    validate_csrf(request,settings)
    if "owner" not in ctx.roles or not verify_password(payload.password,principal.user.password_hash): raise HTTPException(403,"Owner and recent authentication required")
    if principal.user.two_factor_enabled and (not payload.totp_code or not await verify_second_factor(db,principal.user,payload.totp_code,settings)): raise HTTPException(401,"Valid second factor required")
    target=await db.scalar(select(MembershipModel).where(MembershipModel.id==payload.target_membership_id,MembershipModel.tenant_id==ctx.tenant_id,MembershipModel.is_active.is_(True)).with_for_update()); current=await db.scalar(select(MembershipModel).where(MembershipModel.id==ctx.membership_id).with_for_update())
    if not target or not current or target.id==current.id: raise HTTPException(400,"Invalid ownership target")
    owner=await db.scalar(select(RoleModel).where(RoleModel.tenant_id==ctx.tenant_id,RoleModel.name=="owner")); admin=await db.scalar(select(RoleModel).where(RoleModel.tenant_id==ctx.tenant_id,RoleModel.name=="admin")); assert owner is not None and admin is not None
    if not await db.scalar(select(MembershipRoleModel).where(MembershipRoleModel.membership_id==target.id,MembershipRoleModel.role_id==owner.id)): db.add(MembershipRoleModel(membership_id=target.id,role_id=owner.id))
    await db.execute(delete(MembershipRoleModel).where(MembershipRoleModel.membership_id==current.id,MembershipRoleModel.role_id==owner.id))
    if not await db.scalar(select(MembershipRoleModel).where(MembershipRoleModel.membership_id==current.id,MembershipRoleModel.role_id==admin.id)): db.add(MembershipRoleModel(membership_id=current.id,role_id=admin.id))
    await audit(db,"tenant.ownership_transferred","success",ctx.user_id,ctx.tenant_id,resource=str(target.id)); await db.commit()

@router.post("/auth/2fa/disable",status_code=204)
async def disable_2fa(request:Request,payload:DisableTwoFactorRequest,principal:Annotated[Principal,Depends(get_current_user)],db:Annotated[AsyncSession,Depends(get_session)],settings:Annotated[Settings,Depends(get_settings)]):
    validate_csrf(request,settings)
    user=principal.user
    if not verify_password(payload.password,user.password_hash) or not user.totp_secret_encrypted or not verify_totp(decrypt_secret(user.totp_secret_encrypted,settings),payload.code): raise HTTPException(401,"Invalid credentials or second factor")
    user.two_factor_enabled=False; user.totp_secret_encrypted=None; await db.execute(delete(RecoveryCodeModel).where(RecoveryCodeModel.user_id==user.id)); await db.execute(__import__('sqlalchemy').update(RefreshTokenModel).where(RefreshTokenModel.user_id==user.id,RefreshTokenModel.revoked_at.is_(None)).values(revoked_at=datetime.now(UTC),revocation_reason="2fa_disabled")); await audit(db,"auth.2fa_disabled","success",user.id); await db.commit()
@router.post("/auth/2fa/recovery-codes/regenerate",response_model=RecoveryCodesResponse)
async def regenerate_codes(request:Request,payload:DisableTwoFactorRequest,principal:Annotated[Principal,Depends(get_current_user)],db:Annotated[AsyncSession,Depends(get_session)],settings:Annotated[Settings,Depends(get_settings)]):
    validate_csrf(request,settings)
    user=principal.user
    if not user.two_factor_enabled or not verify_password(payload.password,user.password_hash) or not user.totp_secret_encrypted or not verify_totp(decrypt_secret(user.totp_secret_encrypted,settings),payload.code): raise HTTPException(401,"Invalid credentials or second factor")
    codes=generate_recovery_codes(); await db.execute(delete(RecoveryCodeModel).where(RecoveryCodeModel.user_id==user.id)); db.add_all([RecoveryCodeModel(user_id=user.id,code_hash=hash_recovery_code(c)) for c in codes]); await audit(db,"auth.recovery_codes_regenerated","success",user.id); await db.commit(); return RecoveryCodesResponse(recovery_codes=codes)

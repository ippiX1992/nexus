from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import Principal, get_current_context, get_current_user
from app.api.schemas import (
    ChallengeRequest,
    CodeRequest,
    ContextResponse,
    LoginRequest,
    RecoveryCodesResponse,
    RegisterRequest,
    RegistrationResponse,
    SelectTenantRequest,
    SessionResponse,
    TenantResponse,
    TokenResponse,
    TwoFactorSetupResponse,
    UserResponse,
)
from app.application.auth import (
    AuthError,
    ReuseDetected,
    audit,
    begin_two_factor,
    enable_two_factor,
    issue_session,
    revoke_all,
    revoke_session,
    rotate_refresh,
    seed_rbac,
    verify_second_factor,
)
from app.application.authorization import TenantContext
from app.application.identity import slugify
from app.core.config import Settings, get_settings
from app.core.csrf import new_csrf_token, validate_csrf
from app.core.rate_limit import enforce_rate_limit
from app.core.security import create_token, decode_token, hash_password, token_hash, verify_password
from app.infrastructure.database import get_session
from app.infrastructure.models import (
    MembershipModel,
    MembershipRoleModel,
    RefreshTokenModel,
    RoleModel,
    TenantModel,
    UserModel,
)

router=APIRouter(prefix="/api/v1")
def client(request): return request.client.host if request.client else None,request.headers.get("user-agent")
def set_refresh_cookie(response,token,settings):
    response.set_cookie("refresh_token",token,httponly=True,secure=settings.cookie_secure,samesite="lax",path="/api/v1/auth",max_age=settings.refresh_token_days*86400)
    response.set_cookie("csrf_token",new_csrf_token(),httponly=False,secure=settings.cookie_secure,samesite="lax",path="/")
@router.post("/auth/register",response_model=RegistrationResponse,status_code=201)
async def register(payload:RegisterRequest,request:Request,db:Annotated[AsyncSession,Depends(get_session)]):
    email=payload.email.strip().casefold()
    await enforce_rate_limit(db,f"register:{client(request)[0]}:{email}",5,60); await db.commit()
    if await db.scalar(select(UserModel).where(UserModel.email==email)): raise HTTPException(409,"Email already registered")
    if True:
        user=UserModel(email=email,password_hash=hash_password(payload.password),full_name=payload.full_name.strip()); tenant=TenantModel(name=payload.company.strip(),slug=f"{slugify(payload.company)}-{str(uuid4())[:8]}")
        db.add_all([user,tenant]); await db.flush(); membership=MembershipModel(user_id=user.id,tenant_id=tenant.id); db.add(membership); await db.flush(); roles=await seed_rbac(db,tenant.id); db.add(MembershipRoleModel(membership_id=membership.id,role_id=roles["owner"].id)); ip,ua=client(request); await audit(db,"auth.register","success",user.id,tenant.id,ip=ip,user_agent=ua)
    await db.commit()
    return RegistrationResponse(user=UserResponse(id=user.id,email=user.email,full_name=user.full_name),tenant=TenantResponse(id=tenant.id,name=tenant.name,slug=tenant.slug,membership_id=membership.id,roles=["owner"]))
@router.post("/auth/login",response_model=TokenResponse)
async def login(payload:LoginRequest,request:Request,response:Response,db:Annotated[AsyncSession,Depends(get_session)],settings:Annotated[Settings,Depends(get_settings)]):
    normalized=payload.email.strip().casefold(); ip,ua=client(request); await enforce_rate_limit(db,f"login:{ip}:{normalized}",10,60); await db.commit()
    user=await db.scalar(select(UserModel).where(UserModel.email==normalized))
    if not user or not verify_password(payload.password,user.password_hash):
        if user: user.failed_login_attempts+=1; await audit(db,"auth.login","denied",user.id,ip=ip,user_agent=ua); await db.commit()
        raise HTTPException(401,"Invalid credentials")
    if user.two_factor_enabled:
        challenge,exp,_=create_token(user.id,"2fa",settings); return TokenResponse(access_token="",access_expires_at=exp,requires_two_factor=True,challenge_token=challenge)
    if True: access,exp,refresh,_=await issue_session(db,user,settings,ip,ua); await audit(db,"auth.login","success",user.id,ip=ip,user_agent=ua)
    await db.commit()
    set_refresh_cookie(response,refresh,settings); return TokenResponse(access_token=access,refresh_token=None,access_expires_at=exp)
@router.post("/auth/2fa/verify",response_model=TokenResponse)
async def verify_2fa(payload:ChallengeRequest,request:Request,response:Response,db:Annotated[AsyncSession,Depends(get_session)],settings:Annotated[Settings,Depends(get_settings)]):
    await enforce_rate_limit(db,f"2fa:{client(request)[0]}:{token_hash(payload.challenge_token)}",8,60); await db.commit()
    try: claims=decode_token(payload.challenge_token,settings,"2fa"); user=await db.get(UserModel,UUID(claims["sub"]))
    except Exception: raise HTTPException(401,"Invalid challenge") from None
    if not user or not await verify_second_factor(db,user,payload.code,settings): raise HTTPException(401,"Invalid second factor")
    ip,ua=client(request); access,exp,refresh,_=await issue_session(db,user,settings,ip,ua); await audit(db,"auth.2fa_login","success",user.id,ip=ip,user_agent=ua); await db.commit(); set_refresh_cookie(response,refresh,settings); return TokenResponse(access_token=access,access_expires_at=exp)
@router.post("/auth/refresh",response_model=TokenResponse)
async def refresh(request:Request,response:Response,db:Annotated[AsyncSession,Depends(get_session)],settings:Annotated[Settings,Depends(get_settings)],refresh_token:Annotated[str|None,Cookie()]=None):
    validate_csrf(request,settings)
    await enforce_rate_limit(db,f"refresh:{client(request)[0]}",30,60); await db.commit()
    if not refresh_token: raise HTTPException(401,"Refresh cookie required")
    try:
        access,exp,new=await rotate_refresh(db,refresh_token,settings,*client(request))
        await db.commit()
    except ReuseDetected as exc: await db.commit(); response.delete_cookie("refresh_token",path="/api/v1/auth"); raise HTTPException(401,str(exc)) from exc
    except AuthError as exc: raise HTTPException(401,str(exc)) from exc
    set_refresh_cookie(response,new,settings); return TokenResponse(access_token=access,access_expires_at=exp)
@router.post("/auth/logout",status_code=204)
async def logout(request:Request,response:Response,settings:Annotated[Settings,Depends(get_settings)],principal:Annotated[Principal,Depends(get_current_user)],db:Annotated[AsyncSession,Depends(get_session)]):
    validate_csrf(request,settings)
    if principal.payload.get("session_id"): await revoke_session(db,principal.user.id,UUID(principal.payload["session_id"])); await db.commit()
    response.delete_cookie("refresh_token",path="/api/v1/auth")
@router.post("/auth/logout-all",status_code=204)
async def logout_all(request:Request,response:Response,settings:Annotated[Settings,Depends(get_settings)],principal:Annotated[Principal,Depends(get_current_user)],db:Annotated[AsyncSession,Depends(get_session)]):
    validate_csrf(request,settings)
    await revoke_all(db,principal.user.id); await db.commit(); response.delete_cookie("refresh_token",path="/api/v1/auth")
@router.get("/auth/sessions",response_model=list[SessionResponse])
async def sessions(principal:Annotated[Principal,Depends(get_current_user)],db:Annotated[AsyncSession,Depends(get_session)]):
    rows=(await db.scalars(select(RefreshTokenModel).where(RefreshTokenModel.user_id==principal.user.id,RefreshTokenModel.revoked_at.is_(None)))).all(); current=principal.payload.get("session_id")
    return [SessionResponse(id=r.id,created_at=r.created_at,expires_at=r.expires_at,ip_address=r.ip_address,user_agent=r.user_agent,current=str(r.id)==current) for r in rows]
@router.delete("/auth/sessions/{session_id}",status_code=204)
async def delete_session(session_id:UUID,principal:Annotated[Principal,Depends(get_current_user)],db:Annotated[AsyncSession,Depends(get_session)]): await revoke_session(db,principal.user.id,session_id,"remote_logout"); await db.commit()
@router.get("/me",response_model=UserResponse)
async def me(principal:Annotated[Principal,Depends(get_current_user)]): return UserResponse(id=principal.user.id,email=principal.user.email,full_name=principal.user.full_name,two_factor_enabled=principal.user.two_factor_enabled)
@router.get("/me/tenants",response_model=list[TenantResponse])
async def tenants(principal:Annotated[Principal,Depends(get_current_user)],db:Annotated[AsyncSession,Depends(get_session)]):
    rows=(await db.execute(select(TenantModel,MembershipModel).join(MembershipModel).where(MembershipModel.user_id==principal.user.id,MembershipModel.is_active.is_(True),TenantModel.is_active.is_(True)))).all(); return [TenantResponse(id=t.id,name=t.name,slug=t.slug,membership_id=m.id) for t,m in rows]
@router.post("/auth/select-tenant",response_model=TokenResponse)
async def select_tenant(payload:SelectTenantRequest,principal:Annotated[Principal,Depends(get_current_user)],db:Annotated[AsyncSession,Depends(get_session)],settings:Annotated[Settings,Depends(get_settings)]):
    m=await db.scalar(select(MembershipModel).where(MembershipModel.user_id==principal.user.id,MembershipModel.tenant_id==payload.tenant_id,MembershipModel.is_active.is_(True)))
    if not m: raise HTTPException(403,"No active membership for tenant")
    roles=(await db.scalars(select(RoleModel.name).join(MembershipRoleModel).where(MembershipRoleModel.membership_id==m.id))).all(); token,exp,_=create_token(principal.user.id,"access",settings,tenant_id=str(m.tenant_id),membership_id=str(m.id),session_id=principal.payload.get("session_id"),roles=list(roles)); await audit(db,"tenant.select","success",principal.user.id,m.tenant_id); await db.commit(); return TokenResponse(access_token=token,access_expires_at=exp)
@router.get("/me/context",response_model=ContextResponse)
async def context(ctx:Annotated[TenantContext,Depends(get_current_context)]): return ContextResponse(user_id=ctx.user_id,tenant_id=ctx.tenant_id,membership_id=ctx.membership_id,roles=sorted(ctx.roles),permissions=sorted(ctx.permissions))
@router.post("/auth/2fa/setup",response_model=TwoFactorSetupResponse)
async def setup_2fa(principal:Annotated[Principal,Depends(get_current_user)],db:Annotated[AsyncSession,Depends(get_session)],settings:Annotated[Settings,Depends(get_settings)]):
    await enforce_rate_limit(db,f"2fa_setup:{principal.user.id}",5,300); await db.commit()
    uri,_=await begin_two_factor(db,principal.user,settings); await db.commit(); return TwoFactorSetupResponse(provisioning_uri=uri)
@router.post("/auth/2fa/enable",response_model=RecoveryCodesResponse)
async def enable_2fa(payload:CodeRequest,principal:Annotated[Principal,Depends(get_current_user)],db:Annotated[AsyncSession,Depends(get_session)],settings:Annotated[Settings,Depends(get_settings)]):
    await enforce_rate_limit(db,f"2fa_enable:{principal.user.id}",8,300); await db.commit()
    try: codes=await enable_two_factor(db,principal.user,payload.code,settings)
    except AuthError as exc: raise HTTPException(400,str(exc)) from exc
    await audit(db,"auth.2fa_enabled","success",principal.user.id); await db.commit(); return RecoveryCodesResponse(recovery_codes=codes)

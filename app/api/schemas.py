from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    full_name: str = Field(min_length=2, max_length=160)
    company: str = Field(min_length=2, max_length=160)
    @field_validator("password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        if not any(c.islower() for c in value) or not any(c.isupper() for c in value) or not any(c.isdigit() for c in value):
            raise ValueError("Password must include upper, lower and numeric characters")
        return value
class LoginRequest(BaseModel): email:EmailStr; password:str
class CodeRequest(BaseModel): code:str=Field(min_length=6,max_length=32)
class ChallengeRequest(CodeRequest): challenge_token:str
class RefreshRequest(BaseModel): refresh_token:str|None=None
class SelectTenantRequest(BaseModel): tenant_id:UUID
class UserResponse(BaseModel): id:UUID; email:EmailStr; full_name:str; two_factor_enabled:bool=False
class TenantResponse(BaseModel): id:UUID; name:str; slug:str; membership_id:UUID|None=None; roles:list[str]=[]
class RegistrationResponse(BaseModel): user:UserResponse; tenant:TenantResponse
class TokenResponse(BaseModel): access_token:str; refresh_token:str|None=None; access_expires_at:datetime; token_type:str="bearer"; requires_two_factor:bool=False; challenge_token:str|None=None
class ContextResponse(BaseModel): user_id:UUID; tenant_id:UUID; membership_id:UUID; roles:list[str]; permissions:list[str]
class SessionResponse(BaseModel): id:UUID; created_at:datetime; expires_at:datetime; ip_address:str|None; user_agent:str|None; current:bool=False
class TwoFactorSetupResponse(BaseModel): provisioning_uri:str
class RecoveryCodesResponse(BaseModel): recovery_codes:list[str]

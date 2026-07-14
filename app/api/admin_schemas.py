from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class InvitationCreate(BaseModel): email:EmailStr; role_ids:list[UUID]=[]
class InvitationAccept(BaseModel): token:str; password:str=Field(min_length=12); full_name:str=Field(min_length=2,max_length=160)
class InvitationResponse(BaseModel): id:UUID; email:EmailStr; expires_at:datetime; status:str; invitation_token:str|None=None
class MemberUpdate(BaseModel): is_active:bool
class RoleAssignment(BaseModel): role_ids:list[UUID]
class MemberResponse(BaseModel): membership_id:UUID; user_id:UUID; email:EmailStr; full_name:str; is_active:bool; roles:list[str]
class RoleCreate(BaseModel): name:str=Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$"); permissions:list[str]=[]
class RoleUpdate(BaseModel): name:str|None=None
class PermissionAssignment(BaseModel): permissions:list[str]
class RoleResponse(BaseModel): id:UUID; name:str; is_system:bool; permissions:list[str]
class TransferOwnershipRequest(BaseModel): target_membership_id:UUID; password:str; totp_code:str|None=None
class DisableTwoFactorRequest(BaseModel): password:str; code:str

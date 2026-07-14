from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase): pass
class UserModel(Base):
    __tablename__="users"
    id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    email: Mapped[str]=mapped_column(String(320),unique=True,index=True)
    password_hash: Mapped[str]=mapped_column(String(255)); full_name: Mapped[str]=mapped_column(String(160))
    is_active: Mapped[bool]=mapped_column(Boolean,default=True); failed_login_attempts: Mapped[int]=mapped_column(Integer,default=0)
    locked_until: Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); two_factor_enabled: Mapped[bool]=mapped_column(Boolean,default=False)
    totp_secret_encrypted: Mapped[str|None]=mapped_column(Text); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
class TenantModel(Base):
    __tablename__="tenants"
    id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    name: Mapped[str]=mapped_column(String(160)); slug: Mapped[str]=mapped_column(String(100),unique=True,index=True)
    is_active: Mapped[bool]=mapped_column(Boolean,default=True); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
class MembershipModel(Base):
    __tablename__="memberships"; __table_args__=(UniqueConstraint("user_id","tenant_id"),)
    id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    user_id: Mapped[UUID]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True)
    tenant_id: Mapped[UUID]=mapped_column(ForeignKey("tenants.id",ondelete="CASCADE"),index=True)
    is_active: Mapped[bool]=mapped_column(Boolean,default=True); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
class RoleModel(Base):
    __tablename__="roles"; __table_args__=(UniqueConstraint("tenant_id","name"),)
    id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    tenant_id: Mapped[UUID|None]=mapped_column(ForeignKey("tenants.id",ondelete="CASCADE"),index=True)
    name: Mapped[str]=mapped_column(String(64)); is_system: Mapped[bool]=mapped_column(Boolean,default=False)
class PermissionModel(Base):
    __tablename__="permissions"
    id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4); code: Mapped[str]=mapped_column(String(100),unique=True)
class RolePermissionModel(Base):
    __tablename__="role_permissions"; __table_args__=(UniqueConstraint("role_id","permission_id"),)
    role_id: Mapped[UUID]=mapped_column(ForeignKey("roles.id",ondelete="CASCADE"),primary_key=True)
    permission_id: Mapped[UUID]=mapped_column(ForeignKey("permissions.id",ondelete="CASCADE"),primary_key=True)
class MembershipRoleModel(Base):
    __tablename__="membership_roles"; __table_args__=(UniqueConstraint("membership_id","role_id"),)
    membership_id: Mapped[UUID]=mapped_column(ForeignKey("memberships.id",ondelete="CASCADE"),primary_key=True)
    role_id: Mapped[UUID]=mapped_column(ForeignKey("roles.id",ondelete="CASCADE"),primary_key=True)
class RefreshTokenModel(Base):
    __tablename__="refresh_tokens"; __table_args__=(Index("ix_refresh_family","family_id"),)
    id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True)
    user_id: Mapped[UUID]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True)
    family_id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True)); token_hash: Mapped[str]=mapped_column(String(64),unique=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now()); expires_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); replaced_by_id: Mapped[UUID|None]=mapped_column(PGUUID(as_uuid=True))
    ip_address: Mapped[str|None]=mapped_column(String(64)); user_agent: Mapped[str|None]=mapped_column(String(500)); revocation_reason: Mapped[str|None]=mapped_column(String(100))
class RecoveryCodeModel(Base):
    __tablename__="recovery_codes"
    id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4); user_id: Mapped[UUID]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True)
    code_hash: Mapped[str]=mapped_column(String(255)); used_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
class AuditLogModel(Base):
    __tablename__="audit_logs"
    id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4); actor_id: Mapped[UUID|None]=mapped_column(PGUUID(as_uuid=True),index=True)
    tenant_id: Mapped[UUID|None]=mapped_column(PGUUID(as_uuid=True),index=True); action: Mapped[str]=mapped_column(String(100),index=True)
    resource: Mapped[str|None]=mapped_column(String(200)); result: Mapped[str]=mapped_column(String(32)); ip_address: Mapped[str|None]=mapped_column(String(64)); user_agent: Mapped[str|None]=mapped_column(String(500))
    metadata_json: Mapped[dict]=mapped_column(JSONB,default=dict); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),index=True)
class TenantResourceModel(Base):
    __tablename__="tenant_resources"; __table_args__=(CheckConstraint("tenant_id IS NOT NULL"),)
    id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4); tenant_id: Mapped[UUID]=mapped_column(ForeignKey("tenants.id",ondelete="CASCADE"),index=True)
    name: Mapped[str]=mapped_column(String(160))

class InvitationModel(Base):
    __tablename__ = "invitations"
    __table_args__ = (Index("ix_invitation_tenant_email", "tenant_id", "email"),)
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    invited_by_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class InvitationRoleModel(Base):
    __tablename__ = "invitation_roles"
    invitation_id: Mapped[UUID] = mapped_column(ForeignKey("invitations.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[UUID] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)

class RateLimitModel(Base):
    __tablename__ = "rate_limit_buckets"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

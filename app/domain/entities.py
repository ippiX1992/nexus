from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4


class MembershipRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
@dataclass(frozen=True, slots=True)
class User:
    email: str
    password_hash: str
    full_name: str
    id: UUID = field(default_factory=uuid4)
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
@dataclass(frozen=True, slots=True)
class Tenant:
    name: str
    slug: str
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
@dataclass(frozen=True, slots=True)
class Membership:
    user_id: UUID
    tenant_id: UUID
    role: MembershipRole
    id: UUID = field(default_factory=uuid4)

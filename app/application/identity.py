import re
from dataclasses import dataclass

from app.core.security import hash_password, verify_password
from app.domain.entities import Membership, MembershipRole, Tenant, User
from app.domain.repositories import IdentityRepository


class ConflictError(Exception): pass
class AuthenticationError(Exception): pass
@dataclass(frozen=True)
class RegistrationResult:
    user: User
    tenant: Tenant
def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    if not slug: raise ValueError("Company name must contain letters or numbers")
    return slug
class IdentityService:
    def __init__(self, repository: IdentityRepository): self.repository = repository
    async def register(self, *, email: str, password: str, full_name: str, company: str) -> RegistrationResult:
        email = email.strip().casefold()
        if await self.repository.get_user_by_email(email): raise ConflictError("Email is already registered")
        user = User(email=email, password_hash=hash_password(password), full_name=full_name.strip())
        tenant = Tenant(name=company.strip(), slug=slugify(company))
        await self.repository.add_user(user)
        await self.repository.add_tenant(tenant)
        await self.repository.add_membership(Membership(user_id=user.id, tenant_id=tenant.id, role=MembershipRole.OWNER))
        await self.repository.commit()
        return RegistrationResult(user, tenant)
    async def authenticate(self, *, email: str, password: str) -> User:
        user = await self.repository.get_user_by_email(email.strip().casefold())
        if user is None or not user.is_active or not verify_password(password, user.password_hash): raise AuthenticationError("Invalid credentials")
        return user

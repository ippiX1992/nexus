import pytest

from app.application.identity import ConflictError, IdentityService, slugify


class MemoryRepo:
    def __init__(self): self.users={}; self.tenants=[]; self.memberships=[]; self.committed=False
    async def get_user_by_email(self,email): return self.users.get(email)
    async def add_user(self,user): self.users[user.email]=user
    async def add_tenant(self,tenant): self.tenants.append(tenant)
    async def add_membership(self,membership): self.memberships.append(membership)
    async def list_tenants_for_user(self,user_id):
        ids={m.tenant_id for m in self.memberships if m.user_id==user_id}
        return [t for t in self.tenants if t.id in ids]
    async def commit(self): self.committed=True
@pytest.mark.asyncio
async def test_registration_creates_owner_membership():
    repo=MemoryRepo(); result=await IdentityService(repo).register(email=" OWNER@EXAMPLE.COM ",password="a secure password",full_name="Ada",company="Acme Corp")
    assert result.user.email=="owner@example.com" and result.tenant.slug=="acme-corp"
    assert repo.memberships[0].tenant_id==result.tenant.id and repo.committed
@pytest.mark.asyncio
async def test_duplicate_email_is_rejected():
    repo=MemoryRepo(); service=IdentityService(repo)
    data=dict(email="a@example.com",password="a secure password",full_name="Ada",company="Acme")
    await service.register(**data)
    with pytest.raises(ConflictError): await service.register(**data)
def test_slugify(): assert slugify("My New Store!")=="my-new-store"

import os

os.environ["DATABASE_URL"]=os.getenv("TEST_DATABASE_URL","postgresql+asyncpg://nexus_app:nexus_app@127.0.0.1:55432/nexus_test")
os.environ["DATABASE_MIGRATION_URL"]=os.getenv("TEST_DATABASE_MIGRATION_URL","postgresql+psycopg://nexus_migrator:nexus_migrator@127.0.0.1:55432/nexus_test")
os.environ["ALLOWED_ORIGINS"]="http://testserver"
os.environ["JWT_SECRET"]="integration-test-secret-at-least-32-characters"
import psycopg
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

MIGRATION=os.environ["DATABASE_MIGRATION_URL"].replace("postgresql+psycopg://","postgresql://")
@pytest.fixture(autouse=True)
def clean_database():
    with psycopg.connect(MIGRATION) as conn:
        conn.execute("TRUNCATE platform_entitlement_overrides, platform_jobs, platform_operations, platform_idempotency_records, platform_inbox_events, platform_outbox_events, platform_resource_scopes, platform_channel_environments, platform_channel_markets, platform_channel_sites, platform_market_currencies, platform_market_locales, platform_store_currencies, platform_store_locales, platform_markets, platform_environments, platform_channels, platform_sites, platform_stores, rate_limit_buckets, audit_logs, recovery_codes, refresh_tokens, membership_roles, role_permissions, memberships, roles, permissions, tenant_resources, tenants, users RESTART IDENTITY CASCADE")
    yield
@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app),base_url="http://testserver") as value: yield value
@pytest.fixture
def registration(): return {"email":"Owner@Example.com","password":"Correct-Horse-99","full_name":"Ada Owner","company":"Tenant Alpha"}

import os
from uuid import uuid4

import asyncpg
import pytest

pytestmark = pytest.mark.integration


def asyncpg_dsn(value: str) -> str:
    return value.replace("postgresql+asyncpg://", "postgresql://").replace("postgresql+psycopg://", "postgresql://")


APP_DSN = asyncpg_dsn(os.environ["DATABASE_URL"])
MIGRATOR_DSN = asyncpg_dsn(os.environ["DATABASE_MIGRATION_URL"])


async def test_platform_rls_blocks_cross_tenant_crud_and_pool_leaks():
    tenant_a, tenant_b, user_id, store_a, store_b = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    admin = await asyncpg.connect(MIGRATOR_DSN)
    await admin.execute("INSERT INTO users(id,email,password_hash,full_name,is_active,failed_login_attempts,two_factor_enabled) VALUES($1,$2,'hash','RLS',true,0,false)", user_id, f"rls-{user_id}@example.com")
    await admin.execute("INSERT INTO tenants(id,name,slug,is_active) VALUES($1,'A',$2,true),($3,'B',$4,true)", tenant_a, f"a-{tenant_a}", tenant_b, f"b-{tenant_b}")
    async with admin.transaction():
        await admin.execute("SELECT set_config('app.current_tenant_id',$1,true)", str(tenant_a))
        await admin.execute("INSERT INTO platform_stores(id,tenant_id,code,name,slug,status,default_locale,default_currency,timezone,created_by,updated_by) VALUES($1,$2,'a','A','a','active','es-EC','USD','America/Guayaquil',$3,$3)", store_a, tenant_a, user_id)
    async with admin.transaction():
        await admin.execute("SELECT set_config('app.current_tenant_id',$1,true)", str(tenant_b))
        await admin.execute("INSERT INTO platform_stores(id,tenant_id,code,name,slug,status,default_locale,default_currency,timezone,created_by,updated_by) VALUES($1,$2,'b','B','b','active','es-EC','USD','America/Guayaquil',$3,$3)", store_b, tenant_b, user_id)
    await admin.close()
    pool = await asyncpg.create_pool(APP_DSN, min_size=1, max_size=1)
    async with pool.acquire() as connection:
        assert await connection.fetch("SELECT * FROM platform_stores") == []
        async with connection.transaction():
            await connection.execute("SELECT set_config('app.current_tenant_id',$1,true)", str(tenant_a))
            assert await connection.fetchval("SELECT count(*) FROM platform_stores") == 1
            assert await connection.fetchrow("SELECT * FROM platform_stores WHERE id=$1", store_b) is None
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                async with connection.transaction():
                    await connection.execute("INSERT INTO platform_sites(id,tenant_id,store_id,code,name,slug,site_type,status) VALUES($1,$2,$3,'x','X','x','content','active')", uuid4(), tenant_b, store_b)
            assert await connection.execute("UPDATE platform_stores SET name='bad' WHERE id=$1", store_b) == "UPDATE 0"
            assert await connection.execute("DELETE FROM platform_stores WHERE id=$1", store_b) == "DELETE 0"
    async with pool.acquire() as reused:
        assert await reused.fetch("SELECT * FROM platform_stores") == []
    await pool.close()

import os
from uuid import uuid4

import asyncpg
import pytest

pytestmark=pytest.mark.integration
def asyncpg_dsn(value: str) -> str: return value.replace("postgresql+asyncpg://", "postgresql://").replace("postgresql+psycopg://", "postgresql://")
APP_DSN=asyncpg_dsn(os.environ["DATABASE_URL"])
MIGRATOR_DSN=asyncpg_dsn(os.environ["DATABASE_MIGRATION_URL"])
async def seed():
    a,b,ra,rb=uuid4(),uuid4(),uuid4(),uuid4()
    conn=await asyncpg.connect(MIGRATOR_DSN)
    await conn.execute("INSERT INTO tenants(id,name,slug,is_active) VALUES($1,'A',$2,true),($3,'B',$4,true)",a,f"a-{a}",b,f"b-{b}")
    async with conn.transaction():
        await conn.execute("SELECT set_config('app.current_tenant_id',$1,true)",str(a)); await conn.execute("INSERT INTO tenant_resources(id,tenant_id,name) VALUES($1,$2,'A resource')",ra,a)
    async with conn.transaction():
        await conn.execute("SELECT set_config('app.current_tenant_id',$1,true)",str(b)); await conn.execute("INSERT INTO tenant_resources(id,tenant_id,name) VALUES($1,$2,'B resource')",rb,b)
    await conn.close(); return a,b,ra,rb
async def test_rls_blocks_cross_tenant_and_missing_context():
    a,b,ra,rb=await seed(); conn=await asyncpg.connect(APP_DSN)
    assert await conn.fetch("SELECT * FROM tenant_resources")==[]
    async with conn.transaction():
        await conn.execute("SELECT set_config('app.current_tenant_id',$1,true)",str(a)); rows=await conn.fetch("SELECT * FROM tenant_resources"); assert [r['id'] for r in rows]==[ra]
        assert await conn.fetchrow("SELECT * FROM tenant_resources WHERE id=$1",rb) is None
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            async with conn.transaction(): await conn.execute("INSERT INTO tenant_resources(id,tenant_id,name) VALUES($1,$2,'cross')",uuid4(),b)
        assert await conn.execute("UPDATE tenant_resources SET name='hacked' WHERE id=$1",rb)=="UPDATE 0"
        assert await conn.execute("DELETE FROM tenant_resources WHERE id=$1",rb)=="DELETE 0"
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            async with conn.transaction(): await conn.execute("ALTER TABLE tenant_resources DISABLE ROW LEVEL SECURITY")
    assert await conn.fetch("SELECT * FROM tenant_resources")==[]; await conn.close()
    check=await asyncpg.connect(MIGRATOR_DSN)
    async with check.transaction():
        await check.execute("SELECT set_config('app.current_tenant_id',$1,true)",str(b)); assert await check.fetchval("SELECT count(*) FROM tenant_resources WHERE id=$1 AND name='B resource'",rb)==1
    await check.close()
async def test_pool_connection_does_not_leak_tenant():
    a,_,ra,_=await seed(); pool=await asyncpg.create_pool(APP_DSN,min_size=1,max_size=1)
    async with pool.acquire() as conn:
        async with conn.transaction(): await conn.execute("SELECT set_config('app.current_tenant_id',$1,true)",str(a)); assert (await conn.fetchval("SELECT count(*) FROM tenant_resources"))==1
    async with pool.acquire() as reused: assert await reused.fetch("SELECT * FROM tenant_resources")==[]
    await pool.close()

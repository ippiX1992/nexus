from sqlalchemy import text


async def set_tenant_context(session,tenant_id):
    if not session.in_transaction(): await session.begin()
    await session.execute(text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),{"tenant_id":str(tenant_id)})
async def set_store_context(session,store_id):
    if not session.in_transaction(): await session.begin()
    await session.execute(text("SELECT set_config('app.current_store_id', :store_id, true)"),{"store_id":str(store_id)})
async def clear_tenant_context(session):
    if session.in_transaction(): await session.rollback()
def rls_tenant_clause()->str:
    return "tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid"

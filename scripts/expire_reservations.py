"""Release inventory reservations whose hold has expired.

Cron-friendly automatic expiration. Run periodically, e.g. every 5 minutes:

    python -m scripts.expire_reservations

It iterates every tenant, sets the RLS context, and asks InventoryService to
release the due 'held' reservations (reserved -= qty, reservation -> expired,
ledger + event). Safe to run concurrently: due rows are locked FOR UPDATE SKIP
LOCKED, so parallel runs never process the same reservation twice.
"""
import asyncio
from uuid import UUID, uuid4

from sqlalchemy import text

from app.infrastructure.database import SessionFactory
from app.infrastructure.tenant_context import set_tenant_context
from app.modules.inventory.application.services import InventoryActor, InventoryService
from app.modules.inventory.infrastructure.repositories import SqlAlchemyInventoryRepository


async def expire_tenant(tenant_id: UUID) -> int:
    async with SessionFactory() as session:
        await set_tenant_context(session, tenant_id)
        service = InventoryService(
            SqlAlchemyInventoryRepository(session),
            InventoryActor(user_id=None, session_id=None, tenant_id=tenant_id, correlation_id=uuid4()),
            session,
        )
        released = await service.expire_due_reservations()
        await session.commit()
        return released


async def run() -> int:
    async with SessionFactory() as session:
        tenant_ids = [row[0] for row in (await session.execute(text("SELECT id FROM tenants"))).all()]
    total = 0
    for tenant_id in tenant_ids:
        total += await expire_tenant(tenant_id)
    return total


if __name__ == "__main__":
    count = asyncio.run(run())
    print(f"expired {count} reservation(s)")

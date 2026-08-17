"""Checkout <-> Inventory Engine integration.

The storefront order lifecycle now drives InventoryService only -- reserve on
purchase, commit on dispatch, release on cancel/payment-failure, restock on
cancel-after-dispatch, and an expiry sweeper for stale holds. Every scenario is
asserted against a real PostgreSQL through the same service the storefront
routes call. No direct stock SQL anywhere.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.infrastructure.database import SessionFactory
from app.infrastructure.tenant_context import set_tenant_context
from app.modules.inventory.application.services import InventoryActor, InventoryService
from app.modules.inventory.domain.policies import InsufficientStock
from app.modules.inventory.infrastructure.repositories import SqlAlchemyInventoryRepository
from tests.integration.test_catalog_api import catalog_context
from tests.integration.test_inventory_api import create_location, create_warehouse, receive, seed_variant

pytestmark = pytest.mark.integration

_ORDER_REF = "storefront_order"


def _service(session, tenant_id) -> InventoryService:
    actor = InventoryActor(user_id=None, session_id=None, tenant_id=UUID(str(tenant_id)), correlation_id=uuid4())
    return InventoryService(SqlAlchemyInventoryRepository(session), actor, session)


async def _setup(client, registration, *, on_hand):
    """Tenant + one variant + one location holding `on_hand` units, all via the
    real authenticated API (the same way an operator would set it up)."""
    headers, tenant = await catalog_context(client, registration)
    variant = await seed_variant(client, headers)
    warehouse = await create_warehouse(client, headers)
    location = await create_location(client, headers, warehouse["id"])
    await receive(client, headers, location["id"], variant["id"], on_hand)
    return tenant["id"], UUID(variant["id"])


async def _stock(tenant_id, variant_id):
    async with SessionFactory() as session:
        await set_tenant_context(session, tenant_id)
        repo = SqlAlchemyInventoryRepository(session)
        levels, _ = await repo.list_stock_levels(UUID(str(tenant_id)), limit=100, cursor=None, variant_id=variant_id)
        return levels[0]


async def _reservations(tenant_id, variant_id, order_id):
    async with SessionFactory() as session:
        await set_tenant_context(session, tenant_id)
        repo = SqlAlchemyInventoryRepository(session)
        return await repo.list_reservations_by_reference(UUID(str(tenant_id)), _ORDER_REF, order_id)


async def _ledger_types(tenant_id, variant_id):
    async with SessionFactory() as session:
        await set_tenant_context(session, tenant_id)
        repo = SqlAlchemyInventoryRepository(session)
        rows, _ = await repo.list_ledger(UUID(str(tenant_id)), limit=100, cursor=None, variant_id=variant_id)
        return [r.entry_type for r in rows]


# 1 ── Normal purchase: reserve on checkout, commit on dispatch.
async def test_normal_purchase_reserves_then_commits(client, registration):
    tenant_id, variant_id = await _setup(client, registration, on_hand=10)
    order_id = uuid4()

    async with SessionFactory() as session:
        await set_tenant_context(session, tenant_id)
        reservations = await _service(session, tenant_id).reserve_available(
            variant_id, 3, reference_type=_ORDER_REF, reference_id=order_id
        )
        await session.commit()
    assert len(reservations) == 1

    level = await _stock(tenant_id, variant_id)
    assert (level.on_hand, level.reserved, level.available) == (10, 3, 7)

    async with SessionFactory() as session:
        await set_tenant_context(session, tenant_id)
        committed = await _service(session, tenant_id).commit_reservations_for(_ORDER_REF, order_id)
        await session.commit()
    assert committed == 1

    level = await _stock(tenant_id, variant_id)
    assert (level.on_hand, level.reserved, level.available) == (7, 0, 7)

    types = await _ledger_types(tenant_id, variant_id)
    assert "reservation_hold" in types and "reservation_commit" in types
    statuses = [r.status for r in await _reservations(tenant_id, variant_id, order_id)]
    assert statuses == ["committed"]


# 2 ── Cancellation before dispatch: release returns the held units.
async def test_cancel_before_dispatch_releases_stock(client, registration):
    tenant_id, variant_id = await _setup(client, registration, on_hand=5)
    order_id = uuid4()
    async with SessionFactory() as session:
        await set_tenant_context(session, tenant_id)
        await _service(session, tenant_id).reserve_available(variant_id, 2, reference_type=_ORDER_REF, reference_id=order_id)
        await session.commit()

    async with SessionFactory() as session:
        await set_tenant_context(session, tenant_id)
        released = await _service(session, tenant_id).release_reservations_for(_ORDER_REF, order_id, reason="order cancelled")
        await session.commit()
    assert released == 1

    level = await _stock(tenant_id, variant_id)
    assert (level.on_hand, level.reserved, level.available) == (5, 0, 5)
    assert [r.status for r in await _reservations(tenant_id, variant_id, order_id)] == ["released"]


# 3 ── Payment failed: same release path, stock never leaves on_hand.
async def test_payment_failure_releases_reservation(client, registration):
    tenant_id, variant_id = await _setup(client, registration, on_hand=4)
    order_id = uuid4()
    async with SessionFactory() as session:
        await set_tenant_context(session, tenant_id)
        await _service(session, tenant_id).reserve_available(variant_id, 4, reference_type=_ORDER_REF, reference_id=order_id)
        await session.commit()

    async with SessionFactory() as session:
        await set_tenant_context(session, tenant_id)
        released = await _service(session, tenant_id).release_reservations_for(_ORDER_REF, order_id, reason="payment failed")
        await session.commit()
    assert released == 1
    level = await _stock(tenant_id, variant_id)
    assert (level.on_hand, level.reserved, level.available) == (4, 0, 4)


# 4 ── Expired hold: the sweeper releases it and marks it 'expired'.
async def test_expired_reservation_is_swept(client, registration):
    tenant_id, variant_id = await _setup(client, registration, on_hand=6)
    order_id = uuid4()
    async with SessionFactory() as session:
        await set_tenant_context(session, tenant_id)
        await _service(session, tenant_id).reserve_available(
            variant_id, 2, reference_type=_ORDER_REF, reference_id=order_id,
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
        await session.commit()

    level = await _stock(tenant_id, variant_id)
    assert level.reserved == 2

    async with SessionFactory() as session:
        await set_tenant_context(session, tenant_id)
        expired = await _service(session, tenant_id).expire_due_reservations()
        await session.commit()
    assert expired == 1

    level = await _stock(tenant_id, variant_id)
    assert (level.on_hand, level.reserved, level.available) == (6, 0, 6)
    assert [r.status for r in await _reservations(tenant_id, variant_id, order_id)] == ["expired"]


# 5 ── Two shoppers, last unit: the second reserve is refused (no overselling).
async def test_last_unit_cannot_be_oversold(client, registration):
    tenant_id, variant_id = await _setup(client, registration, on_hand=1)

    async with SessionFactory() as session:
        await set_tenant_context(session, tenant_id)
        await _service(session, tenant_id).reserve_available(variant_id, 1, reference_type=_ORDER_REF, reference_id=uuid4())
        await session.commit()

    async with SessionFactory() as session:
        await set_tenant_context(session, tenant_id)
        with pytest.raises(InsufficientStock):
            await _service(session, tenant_id).reserve_available(variant_id, 1, reference_type=_ORDER_REF, reference_id=uuid4())
        await session.rollback()

    level = await _stock(tenant_id, variant_id)
    assert level.reserved == 1 and level.available == 0  # exactly one shopper won


# 6 ── Idempotent lifecycle: committing/releasing an order twice is a no-op the
# second time (retries / duplicate webhooks never double-consume stock).
async def test_commit_and_release_are_idempotent(client, registration):
    tenant_id, variant_id = await _setup(client, registration, on_hand=10)
    order_id = uuid4()
    async with SessionFactory() as session:
        await set_tenant_context(session, tenant_id)
        await _service(session, tenant_id).reserve_available(variant_id, 3, reference_type=_ORDER_REF, reference_id=order_id)
        await session.commit()

    async with SessionFactory() as session:
        await set_tenant_context(session, tenant_id)
        service = _service(session, tenant_id)
        first = await service.commit_reservations_for(_ORDER_REF, order_id)
        second = await service.commit_reservations_for(_ORDER_REF, order_id)  # retry
        await session.commit()
    assert first == 1 and second == 0

    async with SessionFactory() as session:
        await set_tenant_context(session, tenant_id)
        released = await _service(session, tenant_id).release_reservations_for(_ORDER_REF, order_id)  # nothing held left
        await session.commit()
    assert released == 0

    level = await _stock(tenant_id, variant_id)
    assert (level.on_hand, level.reserved, level.available) == (7, 0, 7)  # consumed once, not twice


# 7 ── Cancel after dispatch: units already left on_hand, so they are restocked.
async def test_cancel_after_dispatch_restocks(client, registration):
    tenant_id, variant_id = await _setup(client, registration, on_hand=10)
    order_id = uuid4()
    async with SessionFactory() as session:
        await set_tenant_context(session, tenant_id)
        service = _service(session, tenant_id)
        await service.reserve_available(variant_id, 4, reference_type=_ORDER_REF, reference_id=order_id)
        await service.commit_reservations_for(_ORDER_REF, order_id)
        await session.commit()

    level = await _stock(tenant_id, variant_id)
    assert level.on_hand == 6  # dispatched

    async with SessionFactory() as session:
        await set_tenant_context(session, tenant_id)
        restocked = await _service(session, tenant_id).restock_committed_for(_ORDER_REF, order_id, reason="cancelled")
        await session.commit()
    assert restocked == 1

    level = await _stock(tenant_id, variant_id)
    assert level.on_hand == 10  # units returned
    assert "adjustment" in await _ledger_types(tenant_id, variant_id)


# 8 ── Architectural guard: the storefront never writes stock with raw SQL.
def test_storefront_has_no_direct_stock_writes():
    source = Path("app/modules/storefront/api/routes.py").read_text(encoding="utf-8")
    lowered = source.lower()
    assert "update inventory_stock_levels" not in lowered
    assert "insert into inventory_stock_levels" not in lowered
    assert "delete from inventory_stock_levels" not in lowered

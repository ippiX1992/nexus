"""Pure unit tests for the allocation engine and stock policies -- no database,
no I/O. Covers the rules the reservation/transfer flows depend on: greedy
priority-ordered allocation, shortfall reporting, and the stock invariants."""

from uuid import uuid4

import pytest

from app.modules.inventory.domain.policies import (
    InsufficientStock,
    InventoryPolicyError,
    InventoryVersionConflict,
    ensure_adjustment_keeps_on_hand_nonnegative,
    ensure_can_reserve,
    ensure_expected_version,
    ensure_positive_quantity,
    ensure_scope_reference,
)
from app.modules.inventory.domain.values import LocationCandidate, allocate

WH_A, WH_B = uuid4(), uuid4()


def _candidate(priority: int, available: int, warehouse=WH_A):
    return LocationCandidate(location_id=uuid4(), warehouse_id=warehouse, priority=priority, available=available)


def test_allocate_single_location_exact():
    plan = allocate(5, [_candidate(0, 5)])
    assert plan.fully_allocated
    assert plan.allocated == 5
    assert plan.shortfall == 0
    assert plan.allocations[0].quantity == 5


def test_allocate_reports_shortfall_when_insufficient():
    plan = allocate(10, [_candidate(0, 3), _candidate(0, 4)])
    assert not plan.fully_allocated
    assert plan.allocated == 7
    assert plan.shortfall == 3
    assert sum(a.quantity for a in plan.allocations) == 7


def test_allocate_prefers_higher_priority_warehouse():
    low = _candidate(1, 100, warehouse=WH_A)
    high = _candidate(9, 4, warehouse=WH_B)
    plan = allocate(4, [low, high])
    assert plan.fully_allocated
    # The single high-priority location fully covers the demand, so it is used alone.
    assert len(plan.allocations) == 1
    assert plan.allocations[0].warehouse_id == WH_B


def test_allocate_spills_to_next_priority_when_first_is_short():
    high = _candidate(9, 3, warehouse=WH_B)
    low = _candidate(1, 10, warehouse=WH_A)
    plan = allocate(8, [high, low])
    assert plan.fully_allocated
    assert plan.allocations[0].warehouse_id == WH_B
    assert plan.allocations[0].quantity == 3
    assert plan.allocations[1].warehouse_id == WH_A
    assert plan.allocations[1].quantity == 5


def test_allocate_skips_zero_available():
    plan = allocate(2, [_candidate(5, 0), _candidate(1, 2)])
    assert plan.fully_allocated
    assert len(plan.allocations) == 1
    assert plan.allocations[0].quantity == 2


def test_allocate_zero_request_is_empty_plan():
    plan = allocate(0, [_candidate(0, 5)])
    assert plan.allocations == []
    assert plan.allocated == 0


def test_allocate_is_deterministic_on_priority_ties():
    # Same priority + same available -> ordered by location_id string, stable.
    candidates = [_candidate(5, 3) for _ in range(3)]
    first = allocate(9, candidates)
    second = allocate(9, candidates)
    assert [a.location_id for a in first.allocations] == [a.location_id for a in second.allocations]


def test_ensure_positive_quantity_rejects_zero_and_negatives():
    ensure_positive_quantity(1)
    for bad in (0, -1):
        with pytest.raises(InventoryPolicyError):
            ensure_positive_quantity(bad)
    with pytest.raises(InventoryPolicyError):
        ensure_positive_quantity(True)  # bool is not a valid quantity


def test_ensure_adjustment_nonnegative():
    ensure_adjustment_keeps_on_hand_nonnegative(5, -5)
    with pytest.raises(InsufficientStock):
        ensure_adjustment_keeps_on_hand_nonnegative(5, -6)


def test_ensure_can_reserve():
    ensure_can_reserve(available=5, quantity=5)
    with pytest.raises(InsufficientStock):
        ensure_can_reserve(available=4, quantity=5)


def test_ensure_expected_version():
    ensure_expected_version(3, 3)
    with pytest.raises(InventoryVersionConflict):
        ensure_expected_version(3, 2)


def test_ensure_scope_reference_rules():
    store = uuid4()
    ensure_scope_reference("store", store, None, None)
    with pytest.raises(InventoryPolicyError):
        ensure_scope_reference("store", None, None, None)  # missing id
    with pytest.raises(InventoryPolicyError):
        ensure_scope_reference("store", store, uuid4(), None)  # extra channel id
    with pytest.raises(InventoryPolicyError):
        ensure_scope_reference("warehouse", store, None, None)  # invalid scope

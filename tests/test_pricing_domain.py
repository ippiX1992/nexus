"""Pure unit tests for the price resolution engine -- no database, no I/O.
Covers the priority rules the whole module exists to enforce: override beats
assignment, higher-priority assignment wins, a matching assignment with no
entry falls through instead of stopping resolution, the tenant default is
the last resort, and effective-date windows are honored."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from app.modules.pricing.domain.values import (
    AssignmentCandidate,
    EntryCandidate,
    OverrideCandidate,
    resolve_effective_price,
)

NOW = datetime(2026, 6, 1, tzinfo=UTC)
VARIANT_ID = uuid4()


def _entry(price_list_id, unit_amount="10.00", **overrides):
    fields = {
        "id": uuid4(),
        "price_list_id": price_list_id,
        "unit_amount": Decimal(unit_amount),
        "compare_at_amount": None,
        "msrp_amount": None,
        "cost_amount": None,
        "currency_code": "USD",
    }
    fields.update(overrides)
    return EntryCandidate(**fields)


def test_no_candidates_resolves_to_none():
    result = resolve_effective_price(
        variant_id=VARIANT_ID, at=NOW, overrides=[], assignments=[], entries_by_price_list={}, default_entry=None
    )
    assert result is None


def test_default_entry_used_when_nothing_else_applies():
    default_entry = _entry(uuid4(), "19.99")
    result = resolve_effective_price(
        variant_id=VARIANT_ID, at=NOW, overrides=[], assignments=[], entries_by_price_list={}, default_entry=default_entry
    )
    assert result is not None
    assert result.source == "default"
    assert result.unit_amount == Decimal("19.99")


def test_assignment_beats_default():
    price_list_id = uuid4()
    assignment = AssignmentCandidate(
        id=uuid4(), price_list_id=price_list_id, priority=0, effective_from=None, effective_until=None
    )
    entry = _entry(price_list_id, "15.00")
    result = resolve_effective_price(
        variant_id=VARIANT_ID,
        at=NOW,
        overrides=[],
        assignments=[assignment],
        entries_by_price_list={price_list_id: entry},
        default_entry=_entry(uuid4(), "19.99"),
    )
    assert result is not None
    assert result.source == "assignment"
    assert result.unit_amount == Decimal("15.00")


def test_higher_priority_assignment_wins():
    low_list, high_list = uuid4(), uuid4()
    low = AssignmentCandidate(id=uuid4(), price_list_id=low_list, priority=1, effective_from=None, effective_until=None)
    high = AssignmentCandidate(id=uuid4(), price_list_id=high_list, priority=10, effective_from=None, effective_until=None)
    result = resolve_effective_price(
        variant_id=VARIANT_ID,
        at=NOW,
        overrides=[],
        assignments=[low, high],
        entries_by_price_list={low_list: _entry(low_list, "5.00"), high_list: _entry(high_list, "50.00")},
        default_entry=None,
    )
    assert result is not None
    assert result.unit_amount == Decimal("50.00")


def test_assignment_without_entry_falls_through_to_next_priority():
    empty_list, backup_list = uuid4(), uuid4()
    high = AssignmentCandidate(id=uuid4(), price_list_id=empty_list, priority=10, effective_from=None, effective_until=None)
    low = AssignmentCandidate(id=uuid4(), price_list_id=backup_list, priority=1, effective_from=None, effective_until=None)
    result = resolve_effective_price(
        variant_id=VARIANT_ID,
        at=NOW,
        overrides=[],
        assignments=[high, low],
        entries_by_price_list={backup_list: _entry(backup_list, "7.00")},  # only the lower-priority list has an entry
        default_entry=None,
    )
    assert result is not None
    assert result.source == "assignment"
    assert result.unit_amount == Decimal("7.00")


def test_override_beats_assignment_regardless_of_priority():
    price_list_id = uuid4()
    assignment = AssignmentCandidate(
        id=uuid4(), price_list_id=price_list_id, priority=999, effective_from=None, effective_until=None
    )
    override = OverrideCandidate(
        id=uuid4(), unit_amount=Decimal("1.00"), compare_at_amount=None, currency_code="USD",
        priority=0, effective_from=None, effective_until=None,
    )
    result = resolve_effective_price(
        variant_id=VARIANT_ID,
        at=NOW,
        overrides=[override],
        assignments=[assignment],
        entries_by_price_list={price_list_id: _entry(price_list_id, "999.00")},
        default_entry=None,
    )
    assert result is not None
    assert result.source == "override"
    assert result.unit_amount == Decimal("1.00")


def test_override_outside_effective_window_is_ignored():
    expired = OverrideCandidate(
        id=uuid4(), unit_amount=Decimal("1.00"), compare_at_amount=None, currency_code="USD",
        priority=0, effective_from=NOW - timedelta(days=10), effective_until=NOW - timedelta(days=1),
    )
    default_entry = _entry(uuid4(), "19.99")
    result = resolve_effective_price(
        variant_id=VARIANT_ID, at=NOW, overrides=[expired], assignments=[], entries_by_price_list={}, default_entry=default_entry
    )
    assert result is not None
    assert result.source == "default"


def test_override_before_effective_from_is_ignored():
    future = OverrideCandidate(
        id=uuid4(), unit_amount=Decimal("1.00"), compare_at_amount=None, currency_code="USD",
        priority=0, effective_from=NOW + timedelta(days=1), effective_until=None,
    )
    result = resolve_effective_price(
        variant_id=VARIANT_ID, at=NOW, overrides=[future], assignments=[], entries_by_price_list={}, default_entry=None
    )
    assert result is None


def test_assignment_outside_window_is_ignored():
    price_list_id = uuid4()
    expired = AssignmentCandidate(
        id=uuid4(), price_list_id=price_list_id, priority=100,
        effective_from=None, effective_until=NOW - timedelta(days=1),
    )
    result = resolve_effective_price(
        variant_id=VARIANT_ID,
        at=NOW,
        overrides=[],
        assignments=[expired],
        entries_by_price_list={price_list_id: _entry(price_list_id, "5.00")},
        default_entry=None,
    )
    assert result is None


def test_two_active_overrides_highest_priority_wins():
    low = OverrideCandidate(
        id=uuid4(), unit_amount=Decimal("2.00"), compare_at_amount=None, currency_code="USD",
        priority=1, effective_from=None, effective_until=None,
    )
    high = OverrideCandidate(
        id=uuid4(), unit_amount=Decimal("3.00"), compare_at_amount=None, currency_code="USD",
        priority=5, effective_from=None, effective_until=None,
    )
    result = resolve_effective_price(
        variant_id=VARIANT_ID, at=NOW, overrides=[low, high], assignments=[], entries_by_price_list={}, default_entry=None
    )
    assert result is not None
    assert result.unit_amount == Decimal("3.00")


def test_resolved_price_carries_msrp_and_cost_from_entry():
    price_list_id = uuid4()
    assignment = AssignmentCandidate(
        id=uuid4(), price_list_id=price_list_id, priority=0, effective_from=None, effective_until=None
    )
    entry = _entry(price_list_id, "10.00", compare_at_amount=Decimal("15.00"), msrp_amount=Decimal("20.00"), cost_amount=Decimal("4.00"))
    result = resolve_effective_price(
        variant_id=VARIANT_ID,
        at=NOW,
        overrides=[],
        assignments=[assignment],
        entries_by_price_list={price_list_id: entry},
        default_entry=None,
    )
    assert result is not None
    assert result.compare_at_amount == Decimal("15.00")
    assert result.msrp_amount == Decimal("20.00")
    assert result.cost_amount == Decimal("4.00")

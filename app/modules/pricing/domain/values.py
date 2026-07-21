"""Pure price-resolution engine. No I/O, no SQLAlchemy -- everything here is a
plain function over plain dataclasses so the resolution algorithm (the actual
"motor de precios") can be unit-tested without a database and reused
unchanged by Checkout/Storefront once those modules exist."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from app.modules.platform.domain.values import normalize_code, validate_currency

SCOPE_TYPES = frozenset({"store", "channel", "market"})
_MIN_DATETIME = datetime.min.replace(tzinfo=UTC)


def normalized_code(value: str) -> str:
    return normalize_code(value)


def normalize_currency(value: str) -> str:
    code, _precision = validate_currency(value)
    return code


@dataclass(frozen=True, slots=True)
class OverrideCandidate:
    id: UUID
    unit_amount: Decimal
    compare_at_amount: Decimal | None
    currency_code: str
    priority: int
    effective_from: datetime | None
    effective_until: datetime | None


@dataclass(frozen=True, slots=True)
class AssignmentCandidate:
    id: UUID
    price_list_id: UUID
    priority: int
    effective_from: datetime | None
    effective_until: datetime | None


@dataclass(frozen=True, slots=True)
class EntryCandidate:
    id: UUID
    price_list_id: UUID
    unit_amount: Decimal
    compare_at_amount: Decimal | None
    msrp_amount: Decimal | None
    cost_amount: Decimal | None
    currency_code: str


@dataclass(frozen=True, slots=True)
class ResolvedPrice:
    source: str
    source_id: UUID
    variant_id: UUID
    unit_amount: Decimal
    compare_at_amount: Decimal | None
    msrp_amount: Decimal | None
    cost_amount: Decimal | None
    currency_code: str
    price_list_id: UUID | None


def _is_effective(effective_from: datetime | None, effective_until: datetime | None, at: datetime) -> bool:
    if effective_from is not None and at < effective_from:
        return False
    if effective_until is not None and at > effective_until:
        return False
    return True


def resolve_effective_price(
    *,
    variant_id: UUID,
    at: datetime,
    overrides: list[OverrideCandidate],
    assignments: list[AssignmentCandidate],
    entries_by_price_list: dict[UUID, EntryCandidate],
    default_entry: EntryCandidate | None,
) -> ResolvedPrice | None:
    """Priority order: an active, effective-now Override always wins over any
    PriceList (that is the point of an override); otherwise the
    highest-priority, effective-now Assignment whose PriceList actually has
    an entry for this Variant wins (a matching Assignment with no entry falls
    through to the next one, it does not stop resolution); otherwise the
    tenant's default PriceList entry, if any; otherwise None -- callers decide
    whether "no price configured" is an error or a valid state."""
    active_overrides = [
        candidate for candidate in overrides if _is_effective(candidate.effective_from, candidate.effective_until, at)
    ]
    if active_overrides:
        winner = max(active_overrides, key=lambda candidate: (candidate.priority, candidate.effective_from or _MIN_DATETIME))
        return ResolvedPrice(
            source="override",
            source_id=winner.id,
            variant_id=variant_id,
            unit_amount=winner.unit_amount,
            compare_at_amount=winner.compare_at_amount,
            msrp_amount=None,
            cost_amount=None,
            currency_code=winner.currency_code,
            price_list_id=None,
        )

    active_assignments = sorted(
        (
            candidate
            for candidate in assignments
            if _is_effective(candidate.effective_from, candidate.effective_until, at)
        ),
        key=lambda candidate: candidate.priority,
        reverse=True,
    )
    for assignment in active_assignments:
        entry = entries_by_price_list.get(assignment.price_list_id)
        if entry is not None:
            return ResolvedPrice(
                source="assignment",
                source_id=assignment.id,
                variant_id=variant_id,
                unit_amount=entry.unit_amount,
                compare_at_amount=entry.compare_at_amount,
                msrp_amount=entry.msrp_amount,
                cost_amount=entry.cost_amount,
                currency_code=entry.currency_code,
                price_list_id=entry.price_list_id,
            )

    if default_entry is not None:
        return ResolvedPrice(
            source="default",
            source_id=default_entry.id,
            variant_id=variant_id,
            unit_amount=default_entry.unit_amount,
            compare_at_amount=default_entry.compare_at_amount,
            msrp_amount=default_entry.msrp_amount,
            cost_amount=default_entry.cost_amount,
            currency_code=default_entry.currency_code,
            price_list_id=default_entry.price_list_id,
        )

    return None

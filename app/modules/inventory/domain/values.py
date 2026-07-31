"""Pure allocation engine. No I/O, no SQLAlchemy -- given a demand and the
candidate stock the caller has already fetched, it decides how to split the
demand across locations. Kept pure so the allocation policy is unit-testable
without a database and reusable unchanged by Checkout/Orders once they exist."""

from dataclasses import dataclass
from uuid import UUID

from app.modules.platform.domain.values import normalize_code

SCOPE_TYPES = frozenset({"store", "channel", "market"})


def normalized_code(value: str) -> str:
    return normalize_code(value)


@dataclass(frozen=True, slots=True)
class LocationCandidate:
    """A location that can serve part of a demand, with its warehouse's
    fulfillment priority and how much is currently available there."""

    location_id: UUID
    warehouse_id: UUID
    priority: int
    available: int


@dataclass(frozen=True, slots=True)
class Allocation:
    location_id: UUID
    warehouse_id: UUID
    quantity: int


@dataclass(frozen=True, slots=True)
class AllocationPlan:
    allocations: list[Allocation]
    allocated: int
    requested: int

    @property
    def shortfall(self) -> int:
        return self.requested - self.allocated

    @property
    def fully_allocated(self) -> bool:
        return self.allocated >= self.requested


def allocate(requested: int, candidates: list[LocationCandidate]) -> AllocationPlan:
    """Greedy fill by descending warehouse priority, then by descending
    available (fewest locations touched first), then by location_id for a
    deterministic tie-break. Never allocates more than a location's available
    or more than requested; reports any shortfall rather than raising, so the
    caller decides whether a partial allocation is acceptable."""
    if requested <= 0:
        return AllocationPlan(allocations=[], allocated=0, requested=requested)

    ordered = sorted(
        (candidate for candidate in candidates if candidate.available > 0),
        key=lambda candidate: (-candidate.priority, -candidate.available, str(candidate.location_id)),
    )
    allocations: list[Allocation] = []
    remaining = requested
    for candidate in ordered:
        if remaining <= 0:
            break
        take = min(candidate.available, remaining)
        allocations.append(
            Allocation(location_id=candidate.location_id, warehouse_id=candidate.warehouse_id, quantity=take)
        )
        remaining -= take

    return AllocationPlan(allocations=allocations, allocated=requested - remaining, requested=requested)

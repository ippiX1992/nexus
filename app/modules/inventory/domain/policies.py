from datetime import datetime
from uuid import UUID


class InventoryPolicyError(ValueError):
    pass


class InventoryNotFound(InventoryPolicyError):
    pass


class InventoryConflict(InventoryPolicyError):
    pass


class InventoryVersionConflict(InventoryConflict):
    pass


class InsufficientStock(InventoryConflict):
    """Raised when a reservation/transfer/adjustment would drive on_hand below
    zero or reserve more than is available. A 409, not a 422 -- it is a
    transient state conflict (someone else took the stock), not a malformed
    request."""


def ensure_expected_version(current: int, expected: int) -> None:
    if expected < 1 or current != expected:
        raise InventoryVersionConflict(f"Version conflict: expected {expected}, current {current}")


def ensure_reference_active(status: str, resource: str) -> None:
    if status == "archived":
        raise InventoryPolicyError(f"Archived {resource} cannot be used")


def ensure_positive_quantity(quantity: int, label: str = "quantity") -> None:
    if not isinstance(quantity, int) or isinstance(quantity, bool):
        raise InventoryPolicyError(f"{label} must be a whole number")
    if quantity <= 0:
        raise InventoryPolicyError(f"{label} must be greater than zero")


def ensure_adjustment_keeps_on_hand_nonnegative(current_on_hand: int, delta: int) -> None:
    if current_on_hand + delta < 0:
        raise InsufficientStock(
            f"Adjustment of {delta} would drive on_hand below zero (current {current_on_hand})"
        )


def ensure_recount_nonnegative(counted: int) -> None:
    if not isinstance(counted, int) or isinstance(counted, bool) or counted < 0:
        raise InventoryPolicyError("Recounted quantity must be zero or a positive whole number")


def ensure_can_reserve(available: int, quantity: int) -> None:
    if quantity > available:
        raise InsufficientStock(f"Cannot reserve {quantity}; only {available} available")


def ensure_reservation_releasable(status: str) -> None:
    if status != "held":
        raise InventoryConflict(f"Only a held reservation can be released or committed (current status: {status})")


def ensure_can_ship_transfer(available: int, quantity: int) -> None:
    if quantity > available:
        raise InsufficientStock(
            f"Cannot transfer {quantity}; only {available} available at the source location"
        )


def ensure_transfer_completable(status: str) -> None:
    if status != "in_transit":
        raise InventoryConflict(f"Only an in-transit transfer can be completed or cancelled (current status: {status})")


def ensure_scope_reference(
    scope_type: str, store_id: UUID | None, channel_id: UUID | None, market_id: UUID | None
) -> None:
    if scope_type not in ("store", "channel", "market"):
        raise InventoryPolicyError("scope_type must be one of: store, channel, market")
    present = {"store": store_id, "channel": channel_id, "market": market_id}
    for name, value in present.items():
        if name == scope_type and value is None:
            raise InventoryPolicyError(f"scope_type '{scope_type}' requires {name}_id")
        if name != scope_type and value is not None:
            raise InventoryPolicyError(f"{name}_id must be omitted when scope_type is '{scope_type}'")


def ensure_reservation_not_expired(expires_at: datetime | None, now: datetime) -> None:
    if expires_at is not None and expires_at <= now:
        raise InventoryConflict("Reservation has expired")

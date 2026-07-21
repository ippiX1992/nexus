from datetime import datetime
from uuid import UUID


class PricingPolicyError(ValueError):
    pass


class PricingNotFound(PricingPolicyError):
    pass


class PricingConflict(PricingPolicyError):
    pass


class PricingVersionConflict(PricingConflict):
    pass


def ensure_expected_version(current: int, expected: int) -> None:
    if expected < 1 or current != expected:
        raise PricingVersionConflict(f"Version conflict: expected {expected}, current {current}")


def ensure_price_list_mutable(status: str) -> None:
    if status == "archived":
        raise PricingPolicyError("Archived Price Lists cannot be modified")


def ensure_reference_active(status: str, resource: str) -> None:
    if status == "archived":
        raise PricingPolicyError(f"Archived {resource} cannot be assigned")


def ensure_effective_window(effective_from: datetime | None, effective_until: datetime | None) -> None:
    if effective_from is not None and effective_until is not None and effective_until <= effective_from:
        raise PricingPolicyError("effective_until must be after effective_from")


def ensure_scope_reference(
    scope_type: str, store_id: UUID | None, channel_id: UUID | None, market_id: UUID | None
) -> None:
    if scope_type not in ("store", "channel", "market"):
        raise PricingPolicyError("scope_type must be one of: store, channel, market")
    present = {"store": store_id, "channel": channel_id, "market": market_id}
    for name, value in present.items():
        if name == scope_type and value is None:
            raise PricingPolicyError(f"scope_type '{scope_type}' requires {name}_id")
        if name != scope_type and value is not None:
            raise PricingPolicyError(f"{name}_id must be omitted when scope_type is '{scope_type}'")

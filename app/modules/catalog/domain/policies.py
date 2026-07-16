from uuid import UUID


class CatalogPolicyError(ValueError):
    pass


class CatalogNotFound(CatalogPolicyError):
    pass


class CatalogConflict(CatalogPolicyError):
    pass


class CatalogVersionConflict(CatalogConflict):
    pass


class CatalogQuotaExceeded(CatalogPolicyError):
    def __init__(self, entitlement: str, limit: int) -> None:
        self.entitlement = entitlement
        self.limit = limit
        super().__init__(f"Quota exceeded for {entitlement} (limit {limit})")


class CatalogOptionsQuotaExceeded(CatalogQuotaExceeded):
    """Quota errors for the M3.1 entitlements map to 409, not the 429 that M3.0's
    pre-existing catalog.products.max/catalog.variants.max_per_product already use
    and are tested against -- see the M3.1 error convention in
    docs/modules/03-1-catalog-options-plan.md section 5. Kept as a distinct
    subclass instead of changing CatalogQuotaExceeded itself so M3.0's behavior
    is untouched."""


class CategoryCycle(CatalogPolicyError):
    pass


def ensure_expected_version(current: int, expected: int) -> None:
    if expected < 1 or current != expected:
        raise CatalogVersionConflict(f"Version conflict: expected {expected}, current {current}")


def ensure_reference_active(status: str, resource: str) -> None:
    if status == "archived":
        raise CatalogPolicyError(f"Archived {resource} cannot be assigned")


def ensure_product_mutable(status: str) -> None:
    if status == "archived":
        raise CatalogPolicyError("Archived products cannot be modified")


def ensure_product_activation(active_variants: int) -> None:
    if active_variants < 1:
        raise CatalogPolicyError("Product requires at least one active variant")


def ensure_variant_archive(product_status: str, active_variants: int) -> None:
    if product_status == "active" and active_variants <= 1:
        raise CatalogPolicyError("The only active variant of an active product cannot be archived")


def ensure_quota(entitlement: str, current: int, limit: int) -> None:
    if current >= limit:
        raise CatalogQuotaExceeded(entitlement, limit)


def ensure_options_quota(entitlement: str, current: int, limit: int) -> None:
    if current >= limit:
        raise CatalogOptionsQuotaExceeded(entitlement, limit)


def ensure_store_assignment(product_status: str, store_status: str, assignment_status: str) -> None:
    ensure_product_mutable(product_status)
    if assignment_status == "active" and store_status != "active":
        raise CatalogPolicyError("Only active stores accept active product assignments")
    if store_status == "archived":
        raise CatalogPolicyError("Archived stores cannot accept product assignments")


class CombinationDuplicate(CatalogConflict):
    pass


def ensure_product_option_retirable(active_variant_count: int) -> None:
    if active_variant_count > 0:
        raise CatalogPolicyError(
            "Product Option cannot be retired while active Variants use it; archive those Variants first"
        )


def ensure_combination_complete(required_option_ids: frozenset[UUID], provided_option_ids: frozenset[UUID]) -> None:
    missing = required_option_ids - provided_option_ids
    if missing:
        raise CatalogPolicyError("Combination is missing a value for a required Product Option")
    extra = provided_option_ids - required_option_ids
    if extra:
        raise CatalogPolicyError("Combination includes an Option that is not assigned to this Product")


def ensure_generation_within_limits(estimated_work: int, per_operation_limit: int, remaining_capacity: int) -> None:
    if estimated_work > per_operation_limit:
        raise CatalogOptionsQuotaExceeded("catalog.combination_generation.max_per_operation", per_operation_limit)
    if estimated_work > remaining_capacity:
        raise CatalogOptionsQuotaExceeded("catalog.variant_combinations.max_per_product", remaining_capacity)

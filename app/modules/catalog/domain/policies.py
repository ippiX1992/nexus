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


def ensure_store_assignment(product_status: str, store_status: str, assignment_status: str) -> None:
    ensure_product_mutable(product_status)
    if assignment_status == "active" and store_status != "active":
        raise CatalogPolicyError("Only active stores accept active product assignments")
    if store_status == "archived":
        raise CatalogPolicyError("Archived stores cannot accept product assignments")

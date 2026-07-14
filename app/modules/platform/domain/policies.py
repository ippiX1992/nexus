from dataclasses import dataclass
from uuid import UUID

from app.modules.platform.domain.values import EnvironmentType, StoreStatus


class PlatformPolicyError(ValueError):
    pass


class QuotaExceeded(PlatformPolicyError):
    def __init__(self, entitlement: str, limit: int) -> None:
        self.entitlement = entitlement
        self.limit = limit
        super().__init__(f"Quota exceeded for {entitlement} (limit {limit})")


def ensure_store_accepts_configuration(status: str) -> None:
    if status == StoreStatus.ARCHIVED:
        raise PlatformPolicyError("Archived stores cannot receive configurations")


def ensure_store_transition(current: str, target: str) -> None:
    allowed = {
        StoreStatus.DRAFT: {StoreStatus.ACTIVE, StoreStatus.ARCHIVED},
        StoreStatus.ACTIVE: {StoreStatus.SUSPENDED, StoreStatus.ARCHIVED},
        StoreStatus.SUSPENDED: {StoreStatus.ACTIVE, StoreStatus.ARCHIVED},
        StoreStatus.ARCHIVED: set(),
    }
    if StoreStatus(target) not in allowed[StoreStatus(current)]:
        raise PlatformPolicyError(f"Store cannot transition from {current} to {target}")


def ensure_environment_flags(environment_type: str, is_production: bool) -> None:
    if (environment_type == EnvironmentType.PRODUCTION) != is_production:
        raise PlatformPolicyError("Production type and flag must match")


def ensure_quota(entitlement: str, current: int, limit: int) -> None:
    if current >= limit:
        raise QuotaExceeded(entitlement, limit)


@dataclass(frozen=True, slots=True)
class ResourceScope:
    tenant_id: UUID
    scope_type: str
    resource_id: UUID
    parent_scope_id: UUID | None

    def contains(self, tenant_id: UUID, resource_id: UUID) -> bool:
        return self.tenant_id == tenant_id and self.resource_id == resource_id

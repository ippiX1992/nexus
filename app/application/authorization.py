from dataclasses import dataclass
from uuid import UUID

OWNER = "owner"
SYSTEM_ROLES = ("owner", "admin", "manager", "editor", "analyst", "viewer")
PLATFORM_PERMISSIONS = (
    "store.read", "store.create", "store.update", "store.archive",
    "site.read", "site.create", "site.update", "site.archive",
    "channel.read", "channel.create", "channel.update", "channel.archive",
    "environment.read", "environment.create", "environment.update", "environment.archive",
    "market.read", "market.create", "market.update", "market.archive",
    "operation.read", "entitlement.read", "entitlement.manage",
)
CATALOG_PERMISSIONS = (
    "catalog.product.read", "catalog.product.create", "catalog.product.update", "catalog.product.archive",
    "catalog.variant.read", "catalog.variant.create", "catalog.variant.update", "catalog.variant.archive",
    "catalog.product_type.read", "catalog.product_type.manage",
    "catalog.brand.read", "catalog.brand.manage",
    "catalog.taxonomy.read", "catalog.taxonomy.manage",
    "catalog.category.read", "catalog.category.manage",
    "catalog.assignment.read", "catalog.assignment.manage",
)
PERMISSIONS = (
    "tenant.read", "tenant.update", "member.read", "member.invite", "member.update", "member.remove",
    "role.read", "role.create", "role.update", "role.delete", "audit.read", "security.manage",
    *PLATFORM_PERMISSIONS, *CATALOG_PERMISSIONS,
)

CATALOG_READ_PERMISSIONS = {permission for permission in CATALOG_PERMISSIONS if permission.endswith(".read")}
CATALOG_EDITOR_PERMISSIONS = {
    "catalog.product.read", "catalog.product.create", "catalog.product.update",
    "catalog.variant.read", "catalog.variant.create", "catalog.variant.update",
    "catalog.product_type.read", "catalog.brand.read", "catalog.brand.manage",
    "catalog.taxonomy.read", "catalog.category.read", "catalog.category.manage", "catalog.assignment.read",
}

ROLE_PERMISSIONS = {
    "owner": set(PERMISSIONS),
    "admin": set(PERMISSIONS) - {"role.delete"},
    "manager": {
        "tenant.read", "member.read", "member.invite", "role.read", "audit.read",
        *(permission for permission in PLATFORM_PERMISSIONS if not permission.endswith(".archive") and permission != "entitlement.manage"),
        *(permission for permission in CATALOG_PERMISSIONS if permission != "catalog.product_type.manage"),
    },
    "editor": {
        "tenant.read", "member.read", "role.read", "store.read", "site.read", "channel.read",
        "environment.read", "market.read", "operation.read", "entitlement.read", *CATALOG_EDITOR_PERMISSIONS,
    },
    "analyst": {
        "tenant.read", "audit.read", "store.read", "site.read", "channel.read", "environment.read",
        "market.read", "operation.read", "entitlement.read", *CATALOG_READ_PERMISSIONS,
    },
    "viewer": {
        "tenant.read", "store.read", "site.read", "channel.read", "environment.read", "market.read",
        "operation.read", "entitlement.read", *CATALOG_READ_PERMISSIONS,
    },
}


@dataclass(frozen=True)
class TenantContext:
    user_id: UUID
    tenant_id: UUID
    membership_id: UUID
    session_id: UUID | None
    roles: frozenset[str]
    permissions: frozenset[str]


def ensure_last_owner(owner_count: int, removing_owner: bool) -> None:
    if removing_owner and owner_count <= 1:
        raise ValueError("The last active owner cannot be removed or demoted")


def require_permissions(context: TenantContext, *required: str) -> None:
    missing = set(required) - context.permissions
    if missing:
        raise PermissionError(f"Missing permissions: {', '.join(sorted(missing))}")

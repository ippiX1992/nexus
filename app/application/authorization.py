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
CATALOG_OPTIONS_PERMISSIONS = (
    "catalog.option.read", "catalog.option.create", "catalog.option.update", "catalog.option.archive",
    "catalog.option_value.read", "catalog.option_value.create", "catalog.option_value.update", "catalog.option_value.archive",
    "catalog.product_option.read", "catalog.product_option.manage",
    "catalog.variant_combination.read", "catalog.variant_combination.create",
    "catalog.variant_combination.generate", "catalog.variant_combination.archive",
)
CATALOG_ATTRIBUTES_PERMISSIONS = (
    "catalog.attribute.read", "catalog.attribute.create", "catalog.attribute.update", "catalog.attribute.archive",
    "catalog.attribute_option.read", "catalog.attribute_option.create", "catalog.attribute_option.update", "catalog.attribute_option.archive",
    "catalog.attribute_group.read", "catalog.attribute_group.create", "catalog.attribute_group.update", "catalog.attribute_group.archive",
    "catalog.product_type_attribute.read", "catalog.product_type_attribute.manage",
    "catalog.product_attribute_value.read", "catalog.product_attribute_value.manage",
)
PRICING_PERMISSIONS = (
    "pricing.price_list.read", "pricing.price_list.create", "pricing.price_list.update", "pricing.price_list.archive",
    "pricing.price_list_entry.read", "pricing.price_list_entry.manage",
    "pricing.assignment.read", "pricing.assignment.manage",
    "pricing.variant_override.read", "pricing.variant_override.manage",
    "pricing.price.resolve",
)
INVENTORY_PERMISSIONS = (
    "inventory.warehouse.read", "inventory.warehouse.create", "inventory.warehouse.update", "inventory.warehouse.archive",
    "inventory.location.read", "inventory.location.create", "inventory.location.update", "inventory.location.archive",
    "inventory.stock.read", "inventory.stock.adjust", "inventory.stock.recount",
    "inventory.transfer.read", "inventory.transfer.manage",
    "inventory.reservation.read", "inventory.reservation.manage",
    "inventory.fulfillment_scope.read", "inventory.fulfillment_scope.manage",
    "inventory.allocation.read",
)
PERMISSIONS = (
    "tenant.read", "tenant.update", "member.read", "member.invite", "member.update", "member.remove",
    "role.read", "role.create", "role.update", "role.delete", "audit.read", "security.manage",
    *PLATFORM_PERMISSIONS, *CATALOG_PERMISSIONS, *CATALOG_OPTIONS_PERMISSIONS, *CATALOG_ATTRIBUTES_PERMISSIONS,
    *PRICING_PERMISSIONS, *INVENTORY_PERMISSIONS,
)

CATALOG_READ_PERMISSIONS = {
    permission
    for permission in (*CATALOG_PERMISSIONS, *CATALOG_OPTIONS_PERMISSIONS, *CATALOG_ATTRIBUTES_PERMISSIONS)
    if permission.endswith(".read")
}
PRICING_READ_PERMISSIONS = {
    permission for permission in PRICING_PERMISSIONS if permission.endswith(".read")
} | {"pricing.price.resolve"}
PRICING_EDITOR_PERMISSIONS = {
    "pricing.price_list.read", "pricing.price_list.create", "pricing.price_list.update",
    "pricing.price_list_entry.read", "pricing.price_list_entry.manage",
    "pricing.assignment.read", "pricing.assignment.manage",
    "pricing.variant_override.read", "pricing.variant_override.manage",
    "pricing.price.resolve",
}
INVENTORY_READ_PERMISSIONS = {
    permission for permission in INVENTORY_PERMISSIONS if permission.endswith(".read")
} | {"inventory.allocation.read"}
INVENTORY_EDITOR_PERMISSIONS = set(INVENTORY_PERMISSIONS) - {"inventory.warehouse.archive", "inventory.location.archive"}
CATALOG_EDITOR_PERMISSIONS = {
    "catalog.product.read", "catalog.product.create", "catalog.product.update",
    "catalog.variant.read", "catalog.variant.create", "catalog.variant.update",
    "catalog.product_type.read", "catalog.brand.read", "catalog.brand.manage",
    "catalog.taxonomy.read", "catalog.category.read", "catalog.category.manage", "catalog.assignment.read",
    "catalog.option.read", "catalog.option.create", "catalog.option.update",
    "catalog.option_value.read", "catalog.option_value.create", "catalog.option_value.update",
    "catalog.product_option.read", "catalog.product_option.manage",
    "catalog.variant_combination.read", "catalog.variant_combination.create", "catalog.variant_combination.generate",
    "catalog.attribute.read", "catalog.attribute.create", "catalog.attribute.update",
    "catalog.attribute_option.read", "catalog.attribute_option.create", "catalog.attribute_option.update",
    "catalog.attribute_group.read", "catalog.attribute_group.create", "catalog.attribute_group.update",
    "catalog.product_type_attribute.read", "catalog.product_type_attribute.manage",
    "catalog.product_attribute_value.read", "catalog.product_attribute_value.manage",
}

ROLE_PERMISSIONS = {
    "owner": set(PERMISSIONS),
    "admin": set(PERMISSIONS) - {"role.delete"},
    "manager": {
        "tenant.read", "member.read", "member.invite", "role.read", "audit.read",
        *(permission for permission in PLATFORM_PERMISSIONS if not permission.endswith(".archive") and permission != "entitlement.manage"),
        *(permission for permission in CATALOG_PERMISSIONS if permission != "catalog.product_type.manage"),
        *CATALOG_OPTIONS_PERMISSIONS,
        *CATALOG_ATTRIBUTES_PERMISSIONS,
        *PRICING_PERMISSIONS,
        *INVENTORY_PERMISSIONS,
    },
    "editor": {
        "tenant.read", "member.read", "role.read", "store.read", "site.read", "channel.read",
        "environment.read", "market.read", "operation.read", "entitlement.read", *CATALOG_EDITOR_PERMISSIONS,
        *PRICING_EDITOR_PERMISSIONS, *INVENTORY_EDITOR_PERMISSIONS,
    },
    "analyst": {
        "tenant.read", "audit.read", "store.read", "site.read", "channel.read", "environment.read",
        "market.read", "operation.read", "entitlement.read", *CATALOG_READ_PERMISSIONS, *PRICING_READ_PERMISSIONS,
        *INVENTORY_READ_PERMISSIONS,
    },
    "viewer": {
        "tenant.read", "store.read", "site.read", "channel.read", "environment.read", "market.read",
        "operation.read", "entitlement.read", *CATALOG_READ_PERMISSIONS, *PRICING_READ_PERMISSIONS,
        *INVENTORY_READ_PERMISSIONS,
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

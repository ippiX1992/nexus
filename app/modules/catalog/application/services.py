from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, NoReturn
from uuid import UUID

from app.application.auth import audit
from app.modules.catalog.contracts.repositories import CatalogRepository
from app.modules.catalog.domain.policies import (
    CatalogAttributesQuotaExceeded,
    CatalogConflict,
    CatalogNotFound,
    CatalogOptionsQuotaExceeded,
    CatalogPolicyError,
    CatalogQuotaExceeded,
    CatalogVersionConflict,
    CategoryCycle,
    ensure_attribute_options_supported,
    ensure_attribute_type_immutable,
    ensure_attributes_quota,
    ensure_combination_complete,
    ensure_expected_version,
    ensure_options_quota,
    ensure_product_activation,
    ensure_product_attribute_value_assignable,
    ensure_product_mutable,
    ensure_product_option_retirable,
    ensure_product_type_attribute_assignable,
    ensure_quota,
    ensure_reference_active,
    ensure_required_attributes_present,
    ensure_store_assignment,
    ensure_variant_archive,
)
from app.modules.catalog.domain.values import (
    ATTRIBUTE_DATA_TYPES,
    combination_fingerprint,
    normalize_attribute_value,
    normalize_identifier,
    normalize_locale,
    normalize_multi_select_values,
    normalize_sku,
    normalize_slug,
    normalize_swatch_hex,
    normalized_code,
)
from app.modules.platform.contracts.events import EventActor, EventEnvelope


@dataclass(frozen=True, slots=True)
class CatalogActor:
    user_id: UUID
    session_id: UUID | None
    tenant_id: UUID
    correlation_id: UUID


class CatalogService:
    def __init__(self, repository: CatalogRepository, actor: CatalogActor, audit_session: Any) -> None:
        self.repository = repository
        self.actor = actor
        self.audit_session = audit_session

    def _event(
        self,
        event_type: str,
        aggregate_type: str,
        aggregate_id: UUID,
        version: int,
        data: dict[str, Any],
        store_id: UUID | None = None,
    ) -> EventEnvelope:
        return EventEnvelope.create(
            event_type=event_type,
            tenant_id=self.actor.tenant_id,
            store_id=store_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            correlation_id=self.actor.correlation_id,
            actor=EventActor(self.actor.user_id, self.actor.session_id),
            data={"aggregate_version": version, **data},
        )

    async def _audit(
        self,
        action: str,
        result: str,
        resource: UUID | str | None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await audit(
            self.audit_session,
            action,
            result,
            self.actor.user_id,
            self.actor.tenant_id,
            resource=str(resource) if resource else None,
            metadata={
                **(metadata or {}),
                "correlation_id": str(self.actor.correlation_id),
            },
        )

    async def _missing(self, kind: str, resource_id: UUID) -> NoReturn:
        await self._audit("catalog.scope_denied", "denied", resource_id, {"kind": kind})
        raise CatalogNotFound(f"{kind.replace('_', ' ').title()} not found")

    async def _version(self, kind: str, resource: Any, expected: int) -> None:
        try:
            ensure_expected_version(resource.version, expected)
        except CatalogVersionConflict:
            await self._audit(
                "catalog.version_conflict",
                "denied",
                resource.id,
                {"kind": kind, "expected": expected, "current": resource.version},
            )
            raise

    async def _quota(self, key: str, current: int, limit: int, resource: UUID | None = None) -> None:
        try:
            ensure_quota(key, current, limit)
        except CatalogQuotaExceeded:
            await self._audit(
                "catalog.quota_exceeded",
                "denied",
                resource,
                {"entitlement": key, "current": current, "limit": limit},
            )
            raise

    async def _options_quota(self, key: str, current: int, limit: int, resource: UUID | None = None) -> None:
        """Same as _quota but for the M3.1 entitlements, which map to 409 -- see
        CatalogOptionsQuotaExceeded."""
        try:
            ensure_options_quota(key, current, limit)
        except CatalogOptionsQuotaExceeded:
            await self._audit(
                "catalog.quota_exceeded",
                "denied",
                resource,
                {"entitlement": key, "current": current, "limit": limit},
            )
            raise

    async def _attributes_quota(self, key: str, current: int, limit: int, resource: UUID | None = None) -> None:
        """Same as _quota but for the M3.2 entitlements, which map to 409 -- see
        CatalogAttributesQuotaExceeded."""
        try:
            ensure_attributes_quota(key, current, limit)
        except CatalogAttributesQuotaExceeded:
            await self._audit(
                "catalog.quota_exceeded",
                "denied",
                resource,
                {"entitlement": key, "current": current, "limit": limit},
            )
            raise

    async def create_product_type(self, data: dict[str, Any]) -> Any:
        row = await self.repository.create_product_type(
            self.actor.tenant_id,
            self.actor.user_id,
            {
                "code": normalized_code(data["code"]),
                "name": data["name"].strip(),
                "description": data.get("description"),
                "status": "active",
            },
        )
        await self.repository.flush()
        await self.repository.add_event(
            self._event(
                "catalog.product_type.created.v1",
                "catalog.product_type",
                row.id,
                row.version,
                {"code": row.code, "name": row.name, "status": row.status},
            )
        )
        await self._audit("catalog.product_type_created", "success", row.id)
        return row

    async def update_product_type(self, resource_id: UUID, expected: int, data: dict[str, Any]) -> Any:
        row = await self.repository.get_product_type(self.actor.tenant_id, resource_id, lock=True)
        if row is None:
            await self._missing("product_type", resource_id)
        await self._version("product_type", row, expected)
        ensure_reference_active(row.status, "Product Type")
        changed: list[str] = []
        for field in ("name", "description"):
            if field in data and data[field] is not None:
                value = data[field].strip() if isinstance(data[field], str) else data[field]
                if getattr(row, field) != value:
                    setattr(row, field, value)
                    changed.append(field)
        row.updated_by = self.actor.user_id
        row.version += 1
        await self.repository.add_event(
            self._event(
                "catalog.product_type.updated.v1",
                "catalog.product_type",
                row.id,
                row.version,
                {"changed_fields": changed},
            )
        )
        await self._audit("catalog.product_type_updated", "success", row.id, {"changed_fields": changed})
        return row

    async def archive_product_type(self, resource_id: UUID, expected: int) -> Any:
        row = await self.repository.get_product_type(self.actor.tenant_id, resource_id, lock=True)
        if row is None:
            await self._missing("product_type", resource_id)
        await self._version("product_type", row, expected)
        if row.status != "archived":
            row.status = "archived"
            row.archived_at = datetime.now(UTC)
            row.updated_by = self.actor.user_id
            row.version += 1
            await self.repository.add_event(
                self._event(
                    "catalog.product_type.archived.v1",
                    "catalog.product_type",
                    row.id,
                    row.version,
                    {"status": row.status},
                )
            )
            await self._audit("catalog.product_type_archived", "success", row.id)
        return row

    async def create_brand(self, data: dict[str, Any]) -> Any:
        row = await self.repository.create_brand(
            self.actor.tenant_id,
            self.actor.user_id,
            {
                "code": normalized_code(data["code"]),
                "name": data["name"].strip(),
                "slug": normalize_slug(data["slug"]),
                "status": "active",
            },
        )
        await self.repository.flush()
        await self.repository.add_event(
            self._event(
                "catalog.brand.created.v1",
                "catalog.brand",
                row.id,
                row.version,
                {"code": row.code, "name": row.name, "slug": row.slug},
            )
        )
        await self._audit("catalog.brand_created", "success", row.id)
        return row

    async def update_brand(self, resource_id: UUID, expected: int, data: dict[str, Any]) -> Any:
        row = await self.repository.get_brand(self.actor.tenant_id, resource_id, lock=True)
        if row is None:
            await self._missing("brand", resource_id)
        await self._version("brand", row, expected)
        ensure_reference_active(row.status, "Brand")
        changed: list[str] = []
        for field in ("name", "slug"):
            if field in data and data[field] is not None:
                value = normalize_slug(data[field]) if field == "slug" else data[field].strip()
                if getattr(row, field) != value:
                    setattr(row, field, value)
                    changed.append(field)
        row.updated_by = self.actor.user_id
        row.version += 1
        await self.repository.add_event(
            self._event("catalog.brand.updated.v1", "catalog.brand", row.id, row.version, {"changed_fields": changed})
        )
        await self._audit("catalog.brand_updated", "success", row.id, {"changed_fields": changed})
        return row

    async def archive_brand(self, resource_id: UUID, expected: int) -> Any:
        row = await self.repository.get_brand(self.actor.tenant_id, resource_id, lock=True)
        if row is None:
            await self._missing("brand", resource_id)
        await self._version("brand", row, expected)
        if row.status != "archived":
            row.status = "archived"
            row.archived_at = datetime.now(UTC)
            row.updated_by = self.actor.user_id
            row.version += 1
            await self.repository.add_event(
                self._event("catalog.brand.archived.v1", "catalog.brand", row.id, row.version, {"status": row.status})
            )
            await self._audit("catalog.brand_archived", "success", row.id)
        return row

    async def create_product(self, data: dict[str, Any]) -> tuple[Any, Any]:
        await self.repository.lock_tenant(self.actor.tenant_id)
        product_type = await self.repository.get_product_type(self.actor.tenant_id, data["product_type_id"])
        if product_type is None:
            await self._missing("product_type", data["product_type_id"])
        ensure_reference_active(product_type.status, "Product Type")
        brand_id = data.get("brand_id")
        if brand_id:
            brand = await self.repository.get_brand(self.actor.tenant_id, brand_id)
            if brand is None:
                await self._missing("brand", brand_id)
            ensure_reference_active(brand.status, "Brand")
        sku, sku_normalized = normalize_sku(data["sku"])
        translation = data.get("translation")
        locale: str | None = None
        if translation:
            locale = normalize_locale(translation["locale"])
            if not await self.repository.locale_enabled(self.actor.tenant_id, locale):
                raise CatalogPolicyError("Locale is not enabled for this tenant")
            translation = {
                "name": translation["name"].strip(),
                "short_description": translation.get("short_description"),
                "long_description": translation.get("long_description"),
                "slug": normalize_slug(translation["slug"]),
            }
        limit = await self.repository.entitlement_limit(
            self.actor.tenant_id, "catalog.products.max"
        )
        await self._quota("catalog.products.max", await self.repository.count_products(self.actor.tenant_id), limit)
        product = await self.repository.create_product(
            self.actor.tenant_id,
            self.actor.user_id,
            {
                "product_type_id": product_type.id,
                "brand_id": brand_id,
                "code": normalized_code(data["code"]) if data.get("code") else None,
                "status": "draft",
            },
        )
        await self.repository.flush()
        variant = await self.repository.create_variant(
            self.actor.tenant_id,
            self.actor.user_id,
            {
                "product_id": product.id,
                "sku": sku,
                "sku_normalized": sku_normalized,
                "is_default": True,
                "status": "active",
            },
        )
        await self.repository.flush()
        if translation and locale:
            await self.repository.upsert_translation(
                self.actor.tenant_id,
                product.id,
                locale,
                translation,
            )
        await self.repository.add_event(
            self._event(
                "catalog.product.created.v1",
                "catalog.product",
                product.id,
                product.version,
                {
                    "product_type_id": str(product.product_type_id),
                    "brand_id": str(product.brand_id) if product.brand_id else None,
                    "default_variant_id": str(variant.id),
                    "status": product.status,
                },
            )
        )
        await self.repository.add_event(
            self._event(
                "catalog.variant.created.v1",
                "catalog.product",
                product.id,
                product.version,
                {"variant_id": str(variant.id), "sku": variant.sku, "is_default": True, "status": variant.status},
            )
        )
        await self._audit(
            "catalog.product_created",
            "success",
            product.id,
            {"default_variant_id": str(variant.id), "product_type_id": str(product.product_type_id)},
        )
        return product, variant

    async def update_product(self, resource_id: UUID, expected: int, data: dict[str, Any]) -> Any:
        row = await self.repository.get_product(self.actor.tenant_id, resource_id, lock=True)
        if row is None:
            await self._missing("product", resource_id)
        await self._version("product", row, expected)
        ensure_product_mutable(row.status)
        changed: list[str] = []
        if "code" in data:
            value = normalized_code(data["code"]) if data["code"] else None
            if row.code != value:
                row.code = value
                changed.append("code")
        if "brand_id" in data:
            brand_id = data["brand_id"]
            if brand_id:
                brand = await self.repository.get_brand(self.actor.tenant_id, brand_id)
                if brand is None:
                    await self._missing("brand", brand_id)
                ensure_reference_active(brand.status, "Brand")
            if row.brand_id != brand_id:
                row.brand_id = brand_id
                changed.append("brand_id")
        row.updated_by = self.actor.user_id
        row.version += 1
        await self.repository.add_event(
            self._event("catalog.product.updated.v1", "catalog.product", row.id, row.version, {"changed_fields": changed})
        )
        await self._audit("catalog.product_updated", "success", row.id, {"changed_fields": changed})
        return row

    async def activate_product(self, resource_id: UUID, expected: int) -> Any:
        row = await self.repository.get_product(self.actor.tenant_id, resource_id, lock=True)
        if row is None:
            await self._missing("product", resource_id)
        await self._version("product", row, expected)
        ensure_product_mutable(row.status)
        ensure_product_activation(await self.repository.count_active_variants(self.actor.tenant_id, row.id))
        if row.status != "active":
            row.status = "active"
            row.updated_by = self.actor.user_id
            row.version += 1
            await self.repository.add_event(
                self._event("catalog.product.activated.v1", "catalog.product", row.id, row.version, {"status": row.status})
            )
            await self._audit("catalog.product_activated", "success", row.id)
        return row

    async def archive_product(self, resource_id: UUID, expected: int) -> Any:
        row = await self.repository.get_product(self.actor.tenant_id, resource_id, lock=True)
        if row is None:
            await self._missing("product", resource_id)
        await self._version("product", row, expected)
        if row.status != "archived":
            row.status = "archived"
            row.archived_at = datetime.now(UTC)
            row.updated_by = self.actor.user_id
            row.version += 1
            for assignment in await self.repository.list_product_stores(self.actor.tenant_id, row.id):
                assignment.eligible = False
                if assignment.status == "active":
                    assignment.status = "suspended"
                assignment.updated_by = self.actor.user_id
                assignment.version += 1
            await self.repository.add_event(
                self._event("catalog.product.archived.v1", "catalog.product", row.id, row.version, {"status": row.status})
            )
            await self._audit("catalog.product_archived", "success", row.id)
        return row

    async def create_variant(self, product_id: UUID, data: dict[str, Any]) -> Any:
        product = await self.repository.get_product(self.actor.tenant_id, product_id, lock=True)
        if product is None:
            await self._missing("product", product_id)
        ensure_product_mutable(product.status)
        limit = await self.repository.entitlement_limit(self.actor.tenant_id, "catalog.variants.max_per_product")
        current = await self.repository.count_variants(self.actor.tenant_id, product.id)
        await self._quota("catalog.variants.max_per_product", current, limit, product.id)
        sku, sku_normalized = normalize_sku(data["sku"])
        row = await self.repository.create_variant(
            self.actor.tenant_id,
            self.actor.user_id,
            {
                "product_id": product.id,
                "sku": sku,
                "sku_normalized": sku_normalized,
                "is_default": False,
                "status": "active",
            },
        )
        product.updated_by = self.actor.user_id
        product.version += 1
        await self.repository.flush()
        await self.repository.add_event(
            self._event(
                "catalog.variant.created.v1",
                "catalog.product",
                product.id,
                product.version,
                {"variant_id": str(row.id), "sku": row.sku, "is_default": False, "status": row.status},
            )
        )
        option_value_ids = data.get("option_value_ids")
        if option_value_ids:
            await self._apply_combination(row, product, option_value_ids)
        await self._audit("catalog.variant_created", "success", row.id, {"product_id": str(product.id)})
        return row

    async def update_variant(self, resource_id: UUID, expected: int, data: dict[str, Any]) -> Any:
        existing = await self.repository.get_variant(self.actor.tenant_id, resource_id)
        if existing is None:
            await self._missing("variant", resource_id)
        product = await self.repository.get_product(self.actor.tenant_id, existing.product_id, lock=True)
        if product is None:
            await self._missing("product", existing.product_id)
        row = await self.repository.get_variant(self.actor.tenant_id, resource_id, lock=True)
        if row is None:
            await self._missing("variant", resource_id)
        await self._version("variant", row, expected)
        ensure_product_mutable(product.status)
        if row.status == "archived":
            raise CatalogPolicyError("Archived variants cannot be updated")
        changed: list[str] = []
        if "sku" in data and data["sku"] is not None:
            sku, normalized = normalize_sku(data["sku"])
            if row.sku_normalized != normalized:
                row.sku = sku
                row.sku_normalized = normalized
                changed.append("sku")
                await self._audit("catalog.variant_sku_changed", "success", row.id)
        row.updated_by = self.actor.user_id
        row.version += 1
        product.updated_by = self.actor.user_id
        product.version += 1
        await self.repository.add_event(
            self._event(
                "catalog.variant.updated.v1",
                "catalog.product",
                product.id,
                product.version,
                {"variant_id": str(row.id), "variant_version": row.version, "changed_fields": changed},
            )
        )
        await self._audit("catalog.variant_updated", "success", row.id, {"changed_fields": changed})
        return row

    async def archive_variant(self, resource_id: UUID, expected: int) -> Any:
        existing = await self.repository.get_variant(self.actor.tenant_id, resource_id)
        if existing is None:
            await self._missing("variant", resource_id)
        product = await self.repository.get_product(self.actor.tenant_id, existing.product_id, lock=True)
        if product is None:
            await self._missing("product", existing.product_id)
        row = await self.repository.get_variant(self.actor.tenant_id, resource_id, lock=True)
        if row is None:
            await self._missing("variant", resource_id)
        await self._version("variant", row, expected)
        if row.status != "archived":
            active = await self.repository.count_active_variants(self.actor.tenant_id, product.id)
            ensure_variant_archive(product.status, active)
            row.status = "archived"
            row.archived_at = datetime.now(UTC)
            row.updated_by = self.actor.user_id
            row.version += 1
            product.updated_by = self.actor.user_id
            product.version += 1
            await self.repository.add_event(
                self._event(
                    "catalog.variant.archived.v1",
                    "catalog.product",
                    product.id,
                    product.version,
                    {"variant_id": str(row.id), "variant_version": row.version, "status": row.status},
                )
            )
            await self._audit("catalog.variant_archived", "success", row.id)
        return row

    async def create_identifier(self, variant_id: UUID, data: dict[str, Any]) -> Any:
        variant = await self.repository.get_variant(self.actor.tenant_id, variant_id)
        if variant is None:
            await self._missing("variant", variant_id)
        product = await self.repository.get_product(self.actor.tenant_id, variant.product_id, lock=True)
        if product is None:
            await self._missing("product", variant.product_id)
        ensure_product_mutable(product.status)
        normalized, source = normalize_identifier(data["identifier_type"], data["value"], data.get("source_system"))
        row = await self.repository.create_identifier(
            self.actor.tenant_id,
            {
                "variant_id": variant.id,
                "identifier_type": data["identifier_type"].strip().casefold(),
                "value": data["value"].strip(),
                "normalized_value": normalized,
                "source_system": source,
                "is_primary": data.get("is_primary", False),
            },
        )
        product.updated_by = self.actor.user_id
        product.version += 1
        await self.repository.flush()
        await self.repository.add_event(
            self._event(
                "catalog.variant.updated.v1",
                "catalog.product",
                product.id,
                product.version,
                {"variant_id": str(variant.id), "changed_fields": ["identifiers"]},
            )
        )
        await self._audit("catalog.identifier_created", "success", row.id, {"variant_id": str(variant.id)})
        return row

    async def archive_identifier(self, resource_id: UUID) -> Any:
        row = await self.repository.get_identifier(self.actor.tenant_id, resource_id, lock=True)
        if row is None:
            await self._missing("identifier", resource_id)
        variant = await self.repository.get_variant(self.actor.tenant_id, row.variant_id)
        if variant is None:
            await self._missing("variant", row.variant_id)
        product = await self.repository.get_product(self.actor.tenant_id, variant.product_id, lock=True)
        if product is None:
            await self._missing("product", variant.product_id)
        if row.archived_at is None:
            row.archived_at = datetime.now(UTC)
            row.is_primary = False
            product.updated_by = self.actor.user_id
            product.version += 1
            await self.repository.add_event(
                self._event(
                    "catalog.variant.updated.v1",
                    "catalog.product",
                    product.id,
                    product.version,
                    {"variant_id": str(variant.id), "changed_fields": ["identifiers"]},
                )
            )
            await self._audit("catalog.identifier_archived", "success", row.id, {"variant_id": str(variant.id)})
        return row

    async def upsert_translation(self, product_id: UUID, locale_value: str, expected: int, data: dict[str, Any]) -> Any:
        product = await self.repository.get_product(self.actor.tenant_id, product_id, lock=True)
        if product is None:
            await self._missing("product", product_id)
        await self._version("product", product, expected)
        ensure_product_mutable(product.status)
        locale = normalize_locale(locale_value)
        if not await self.repository.locale_enabled(self.actor.tenant_id, locale):
            raise CatalogPolicyError("Locale is not enabled for this tenant")
        row = await self.repository.upsert_translation(
            self.actor.tenant_id,
            product.id,
            locale,
            {
                "name": data["name"].strip(),
                "short_description": data.get("short_description"),
                "long_description": data.get("long_description"),
                "slug": normalize_slug(data["slug"]),
            },
        )
        product.updated_by = self.actor.user_id
        product.version += 1
        await self.repository.flush()
        await self.repository.add_event(
            self._event(
                "catalog.product.updated.v1",
                "catalog.product",
                product.id,
                product.version,
                {"changed_fields": ["translations"], "locales": [locale]},
            )
        )
        await self._audit("catalog.product_translation_updated", "success", product.id, {"locale": locale})
        return row

    async def upsert_seo(self, product_id: UUID, locale_value: str, expected: int, data: dict[str, Any]) -> Any:
        product = await self.repository.get_product(self.actor.tenant_id, product_id, lock=True)
        if product is None:
            await self._missing("product", product_id)
        await self._version("product", product, expected)
        ensure_product_mutable(product.status)
        locale = normalize_locale(locale_value)
        if not await self.repository.locale_enabled(self.actor.tenant_id, locale):
            raise CatalogPolicyError("Locale is not enabled for this tenant")
        canonical_path = data.get("canonical_path")
        if canonical_path and (not canonical_path.startswith("/") or "://" in canonical_path):
            raise CatalogPolicyError("canonical_path must be an absolute path without a host")
        row = await self.repository.upsert_seo(self.actor.tenant_id, product.id, locale, data)
        product.updated_by = self.actor.user_id
        product.version += 1
        await self.repository.flush()
        await self.repository.add_event(
            self._event(
                "catalog.product.updated.v1",
                "catalog.product",
                product.id,
                product.version,
                {"changed_fields": ["seo"], "locales": [locale]},
            )
        )
        await self._audit("catalog.product_seo_updated", "success", product.id, {"locale": locale})
        return row

    async def create_taxonomy(self, data: dict[str, Any]) -> Any:
        row = await self.repository.create_taxonomy(
            self.actor.tenant_id,
            self.actor.user_id,
            {"code": normalized_code(data["code"]), "name": data["name"].strip(), "status": "active"},
        )
        await self.repository.flush()
        await self.repository.add_event(
            self._event(
                "catalog.taxonomy.created.v1",
                "catalog.taxonomy",
                row.id,
                row.version,
                {"code": row.code, "name": row.name, "status": row.status},
            )
        )
        await self._audit("catalog.taxonomy_created", "success", row.id)
        return row

    async def create_category(self, taxonomy_id: UUID, data: dict[str, Any]) -> Any:
        taxonomy = await self.repository.get_taxonomy(self.actor.tenant_id, taxonomy_id, lock=True)
        if taxonomy is None:
            await self._missing("taxonomy", taxonomy_id)
        ensure_reference_active(taxonomy.status, "Taxonomy")
        parent_id = data.get("parent_id")
        if parent_id:
            parent = await self.repository.get_category(self.actor.tenant_id, parent_id)
            if parent is None or parent.taxonomy_id != taxonomy.id:
                await self._missing("category", parent_id)
            ensure_reference_active(parent.status, "Category")
        row = await self.repository.create_category(
            self.actor.tenant_id,
            self.actor.user_id,
            {
                "taxonomy_id": taxonomy.id,
                "parent_id": parent_id,
                "code": normalized_code(data["code"]),
                "name": data["name"].strip(),
                "slug": normalize_slug(data["slug"]),
                "position": data.get("position", 0),
                "status": "active",
            },
        )
        await self.repository.flush()
        await self.repository.add_category_closure(self.actor.tenant_id, taxonomy.id, row.id, parent_id)
        taxonomy.updated_by = self.actor.user_id
        taxonomy.version += 1
        await self.repository.add_event(
            self._event(
                "catalog.category.created.v1",
                "catalog.taxonomy",
                taxonomy.id,
                taxonomy.version,
                {"category_id": str(row.id), "parent_id": str(parent_id) if parent_id else None},
            )
        )
        await self._audit("catalog.category_created", "success", row.id, {"taxonomy_id": str(taxonomy.id)})
        return row

    async def update_category(self, resource_id: UUID, expected: int, data: dict[str, Any]) -> Any:
        initial = await self.repository.get_category(self.actor.tenant_id, resource_id)
        if initial is None:
            await self._missing("category", resource_id)
        taxonomy = await self.repository.get_taxonomy(
            self.actor.tenant_id, initial.taxonomy_id, lock=True
        )
        if taxonomy is None:
            await self._missing("taxonomy", initial.taxonomy_id)
        row = await self.repository.get_category(self.actor.tenant_id, resource_id, lock=True)
        if row is None:
            await self._missing("category", resource_id)
        await self._version("category", row, expected)
        ensure_reference_active(row.status, "Category")
        changed: list[str] = []
        for field in ("name", "slug", "position"):
            if field in data and data[field] is not None:
                value = normalize_slug(data[field]) if field == "slug" else data[field]
                value = value.strip() if isinstance(value, str) else value
                if getattr(row, field) != value:
                    setattr(row, field, value)
                    changed.append(field)
        taxonomy.updated_by = self.actor.user_id
        taxonomy.version += 1
        row.updated_by = self.actor.user_id
        row.version += 1
        await self.repository.add_event(
            self._event(
                "catalog.category.updated.v1",
                "catalog.taxonomy",
                row.taxonomy_id,
                taxonomy.version,
                {"category_id": str(row.id), "changed_fields": changed},
            )
        )
        await self._audit("catalog.category_updated", "success", row.id, {"changed_fields": changed})
        return row

    async def move_category(self, resource_id: UUID, expected: int, parent_id: UUID | None, position: int) -> Any:
        initial = await self.repository.get_category(self.actor.tenant_id, resource_id)
        if initial is None:
            await self._missing("category", resource_id)
        taxonomy = await self.repository.get_taxonomy(
            self.actor.tenant_id, initial.taxonomy_id, lock=True
        )
        if taxonomy is None:
            await self._missing("taxonomy", initial.taxonomy_id)
        row = await self.repository.get_category(self.actor.tenant_id, resource_id, lock=True)
        if row is None:
            await self._missing("category", resource_id)
        await self._version("category", row, expected)
        ensure_reference_active(row.status, "Category")
        old_parent_id = row.parent_id
        if parent_id:
            parent = await self.repository.get_category(self.actor.tenant_id, parent_id, lock=True)
            if parent is None or parent.taxonomy_id != row.taxonomy_id:
                await self._missing("category", parent_id)
            ensure_reference_active(parent.status, "Category")
            if parent.id == row.id or await self.repository.category_would_cycle(
                self.actor.tenant_id, row.taxonomy_id, row.id, parent.id
            ):
                await self._audit("catalog.category_cycle", "denied", row.id, {"parent_id": str(parent.id)})
                raise CategoryCycle("Category cannot be moved below itself or one of its descendants")
        await self.repository.move_category_closure(
            self.actor.tenant_id, row.taxonomy_id, row.id, parent_id
        )
        row.parent_id = parent_id
        taxonomy.updated_by = self.actor.user_id
        taxonomy.version += 1
        row.position = position
        row.updated_by = self.actor.user_id
        row.version += 1
        await self.repository.add_event(
            self._event(
                "catalog.category.moved.v1",
                "catalog.taxonomy",
                row.taxonomy_id,
                taxonomy.version,
                {
                    "category_id": str(row.id),
                    "old_parent_id": str(old_parent_id) if old_parent_id else None,
                    "new_parent_id": str(parent_id) if parent_id else None,
                    "position": position,
                },
            )
        )
        await self._audit(
            "catalog.category_moved",
            "success",
            row.id,
            {"old_parent_id": str(old_parent_id) if old_parent_id else None, "parent_id": str(parent_id) if parent_id else None},
        )
        return row

    async def archive_category(self, resource_id: UUID, expected: int) -> Any:
        initial = await self.repository.get_category(self.actor.tenant_id, resource_id)
        if initial is None:
            await self._missing("category", resource_id)
        taxonomy = await self.repository.get_taxonomy(
            self.actor.tenant_id, initial.taxonomy_id, lock=True
        )
        if taxonomy is None:
            await self._missing("taxonomy", initial.taxonomy_id)
        row = await self.repository.get_category(self.actor.tenant_id, resource_id, lock=True)
        if row is None:
            await self._missing("category", resource_id)
        await self._version("category", row, expected)
        children = await self.repository.list_categories(self.actor.tenant_id, row.taxonomy_id)
        if any(child.parent_id == row.id and child.status != "archived" for child in children):
            raise CatalogConflict("Category with active children cannot be archived")
        if row.status != "archived":
            taxonomy.updated_by = self.actor.user_id
            taxonomy.version += 1
            row.status = "archived"
            row.archived_at = datetime.now(UTC)
            row.updated_by = self.actor.user_id
            row.version += 1
            await self.repository.add_event(
                self._event(
                    "catalog.category.archived.v1",
                    "catalog.taxonomy",
                    row.taxonomy_id,
                    taxonomy.version,
                    {"category_id": str(row.id), "status": row.status},
                )
            )
            await self._audit("catalog.category_archived", "success", row.id)
        return row

    async def assign_categories(self, product_id: UUID, expected: int, assignments: list[dict[str, Any]]) -> list[Any]:
        product = await self.repository.get_product(self.actor.tenant_id, product_id, lock=True)
        if product is None:
            await self._missing("product", product_id)
        await self._version("product", product, expected)
        ensure_product_mutable(product.status)
        normalized: list[dict[str, Any]] = []
        primary_taxonomies: set[UUID] = set()
        seen: set[UUID] = set()
        for assignment in assignments:
            category_id = assignment["category_id"]
            if category_id in seen:
                raise CatalogConflict("Duplicate category assignment")
            seen.add(category_id)
            category = await self.repository.get_category(self.actor.tenant_id, category_id)
            if category is None:
                await self._missing("category", category_id)
            ensure_reference_active(category.status, "Category")
            if assignment.get("is_primary", False):
                if category.taxonomy_id in primary_taxonomies:
                    raise CatalogConflict("Only one primary category is allowed per taxonomy")
                primary_taxonomies.add(category.taxonomy_id)
            normalized.append(
                {
                    "category_id": category.id,
                    "taxonomy_id": category.taxonomy_id,
                    "is_primary": assignment.get("is_primary", False),
                    "position": assignment.get("position", 0),
                }
            )
        await self.repository.replace_product_categories(self.actor.tenant_id, product.id, normalized)
        product.updated_by = self.actor.user_id
        product.version += 1
        await self.repository.add_event(
            self._event(
                "catalog.product.assigned_to_category.v1",
                "catalog.product",
                product.id,
                product.version,
                {"category_ids": [str(item["category_id"]) for item in normalized]},
            )
        )
        await self._audit(
            "catalog.product_categories_changed",
            "success",
            product.id,
            {"category_count": len(normalized)},
        )
        return await self.repository.list_product_categories(self.actor.tenant_id, product.id)

    async def assign_store(self, product_id: UUID, store_id: UUID, data: dict[str, Any]) -> Any:
        product = await self.repository.get_product(self.actor.tenant_id, product_id, lock=True)
        if product is None:
            await self._missing("product", product_id)
        store = await self.repository.get_store(self.actor.tenant_id, store_id, lock=True)
        if store is None:
            await self._missing("store", store_id)
        status = data.get("status", "draft")
        ensure_store_assignment(product.status, store.status, status)
        row = await self.repository.get_store_assignment(
            self.actor.tenant_id, product.id, store.id, lock=True
        )
        active_variants = await self.repository.count_active_variants(self.actor.tenant_id, product.id)
        eligible = product.status == "active" and store.status == "active" and status == "active" and active_variants > 0
        if row is None:
            row = await self.repository.create_store_assignment(
                self.actor.tenant_id,
                self.actor.user_id,
                {
                    "product_id": product.id,
                    "store_id": store.id,
                    "status": status,
                    "eligible": eligible,
                },
            )
        else:
            expected = data.get("version")
            if expected is not None:
                await self._version("product_store", row, expected)
            row.status = status
            row.eligible = eligible
            row.archived_at = None if status != "archived" else datetime.now(UTC)
            row.updated_by = self.actor.user_id
            row.version += 1
        product.updated_by = self.actor.user_id
        product.version += 1
        await self.repository.flush()
        await self.repository.add_event(
            self._event(
                "catalog.product.assigned_to_store.v1",
                "catalog.product",
                product.id,
                product.version,
                {"store_id": str(store.id), "status": row.status, "eligible": row.eligible},
                store.id,
            )
        )
        await self._audit(
            "catalog.product_assigned_to_store",
            "success",
            product.id,
            {"store_id": str(store.id), "status": row.status, "eligible": row.eligible},
        )
        return row

    async def unassign_store(self, product_id: UUID, store_id: UUID, expected: int) -> Any:
        product = await self.repository.get_product(self.actor.tenant_id, product_id, lock=True)
        if product is None:
            await self._missing("product", product_id)
        row = await self.repository.get_store_assignment(
            self.actor.tenant_id, product.id, store_id, lock=True
        )
        if row is None:
            await self._missing("product_store", store_id)
        await self._version("product_store", row, expected)
        if row.status != "archived":
            row.status = "archived"
            row.eligible = False
            row.archived_at = datetime.now(UTC)
            row.updated_by = self.actor.user_id
            row.version += 1
            product.updated_by = self.actor.user_id
            product.version += 1
            await self.repository.add_event(
                self._event(
                    "catalog.product.unassigned_from_store.v1",
                    "catalog.product",
                    product.id,
                    product.version,
                    {"store_id": str(store_id), "status": row.status},
                    store_id,
                )
            )
            await self._audit(
                "catalog.product_unassigned_from_store",
                "success",
                product.id,
                {"store_id": str(store_id)},
            )
        return row

    # --- M3.1 Options ---

    async def create_option(self, data: dict[str, Any]) -> Any:
        row = await self.repository.create_option(
            self.actor.tenant_id,
            self.actor.user_id,
            {
                "code": normalized_code(data["code"]),
                "name": data["name"].strip(),
                "input_type": data.get("input_type", "select"),
                "position": data.get("position", 0),
                "status": "active",
            },
        )
        await self.repository.flush()
        await self.repository.add_event(
            self._event(
                "catalog.option.created.v1",
                "catalog.option",
                row.id,
                row.version,
                {"code": row.code, "name": row.name, "input_type": row.input_type},
            )
        )
        await self._audit("catalog.option_created", "success", row.id)
        return row

    async def update_option(self, resource_id: UUID, expected: int, data: dict[str, Any]) -> Any:
        row = await self.repository.get_option(self.actor.tenant_id, resource_id, lock=True)
        if row is None:
            await self._missing("option", resource_id)
        await self._version("option", row, expected)
        ensure_reference_active(row.status, "Option")
        changed: list[str] = []
        for field in ("name", "input_type", "position"):
            if field in data and data[field] is not None:
                value = data[field].strip() if isinstance(data[field], str) else data[field]
                if getattr(row, field) != value:
                    setattr(row, field, value)
                    changed.append(field)
        row.updated_by = self.actor.user_id
        row.version += 1
        await self.repository.add_event(
            self._event("catalog.option.updated.v1", "catalog.option", row.id, row.version, {"changed_fields": changed})
        )
        await self._audit("catalog.option_updated", "success", row.id, {"changed_fields": changed})
        return row

    async def archive_option(self, resource_id: UUID, expected: int) -> Any:
        row = await self.repository.get_option(self.actor.tenant_id, resource_id, lock=True)
        if row is None:
            await self._missing("option", resource_id)
        await self._version("option", row, expected)
        if row.status != "archived":
            row.status = "archived"
            row.archived_at = datetime.now(UTC)
            row.updated_by = self.actor.user_id
            row.version += 1
            await self.repository.add_event(
                self._event("catalog.option.archived.v1", "catalog.option", row.id, row.version, {"status": row.status})
            )
            await self._audit("catalog.option_archived", "success", row.id)
        return row

    async def upsert_option_translation(self, option_id: UUID, locale_value: str, data: dict[str, Any]) -> Any:
        option = await self.repository.get_option(self.actor.tenant_id, option_id, lock=True)
        if option is None:
            await self._missing("option", option_id)
        ensure_reference_active(option.status, "Option")
        locale = normalize_locale(locale_value)
        row = await self.repository.upsert_option_translation(
            self.actor.tenant_id, option.id, locale, {"name": data["name"].strip()}
        )
        option.updated_by = self.actor.user_id
        option.version += 1
        await self.repository.flush()
        await self.repository.add_event(
            self._event(
                "catalog.option.updated.v1", "catalog.option", option.id, option.version,
                {"changed_fields": ["translations"], "locales": [locale]},
            )
        )
        await self._audit("catalog.option_translation_updated", "success", option.id, {"locale": locale})
        return row

    async def create_option_value(self, option_id: UUID, data: dict[str, Any]) -> Any:
        option = await self.repository.get_option(self.actor.tenant_id, option_id, lock=True)
        if option is None:
            await self._missing("option", option_id)
        ensure_reference_active(option.status, "Option")
        limit = await self.repository.entitlement_limit(self.actor.tenant_id, "catalog.option_values.max_per_option")
        current = await self.repository.count_option_values(self.actor.tenant_id, option.id)
        await self._options_quota("catalog.option_values.max_per_option", current, limit, option.id)
        row = await self.repository.create_option_value(
            self.actor.tenant_id,
            self.actor.user_id,
            {
                "option_id": option.id,
                "code": normalized_code(data["code"]),
                "value": data["value"].strip(),
                "swatch_hex": normalize_swatch_hex(data.get("swatch_hex")),
                "position": data.get("position", 0),
                "status": "active",
            },
        )
        await self.repository.flush()
        await self.repository.add_event(
            self._event(
                "catalog.option_value.created.v1", "catalog.option", option.id, option.version,
                {"option_value_id": str(row.id), "code": row.code, "value": row.value},
            )
        )
        await self._audit("catalog.option_value_created", "success", row.id, {"option_id": str(option.id)})
        return row

    async def update_option_value(self, resource_id: UUID, expected: int, data: dict[str, Any]) -> Any:
        row = await self.repository.get_option_value(self.actor.tenant_id, resource_id, lock=True)
        if row is None:
            await self._missing("option_value", resource_id)
        await self._version("option_value", row, expected)
        ensure_reference_active(row.status, "Option Value")
        changed: list[str] = []
        for field in ("value", "position"):
            if field in data and data[field] is not None:
                value = data[field].strip() if isinstance(data[field], str) else data[field]
                if getattr(row, field) != value:
                    setattr(row, field, value)
                    changed.append(field)
        if "swatch_hex" in data:
            value = normalize_swatch_hex(data["swatch_hex"])
            if row.swatch_hex != value:
                row.swatch_hex = value
                changed.append("swatch_hex")
        row.updated_by = self.actor.user_id
        row.version += 1
        await self.repository.add_event(
            self._event(
                "catalog.option_value.updated.v1", "catalog.option", row.option_id, row.version,
                {"option_value_id": str(row.id), "changed_fields": changed},
            )
        )
        await self._audit("catalog.option_value_updated", "success", row.id, {"changed_fields": changed})
        return row

    async def archive_option_value(self, resource_id: UUID, expected: int) -> Any:
        row = await self.repository.get_option_value(self.actor.tenant_id, resource_id, lock=True)
        if row is None:
            await self._missing("option_value", resource_id)
        await self._version("option_value", row, expected)
        if row.status != "archived":
            row.status = "archived"
            row.archived_at = datetime.now(UTC)
            row.updated_by = self.actor.user_id
            row.version += 1
            await self.repository.add_event(
                self._event(
                    "catalog.option_value.archived.v1", "catalog.option", row.option_id, row.version,
                    {"option_value_id": str(row.id), "status": row.status},
                )
            )
            await self._audit("catalog.option_value_archived", "success", row.id)
        return row

    async def upsert_option_value_translation(self, option_value_id: UUID, locale_value: str, data: dict[str, Any]) -> Any:
        value = await self.repository.get_option_value(self.actor.tenant_id, option_value_id, lock=True)
        if value is None:
            await self._missing("option_value", option_value_id)
        ensure_reference_active(value.status, "Option Value")
        locale = normalize_locale(locale_value)
        row = await self.repository.upsert_option_value_translation(
            self.actor.tenant_id, value.id, locale, {"value": data["value"].strip()}
        )
        value.updated_by = self.actor.user_id
        value.version += 1
        await self.repository.flush()
        await self.repository.add_event(
            self._event(
                "catalog.option_value.updated.v1", "catalog.option", value.option_id, value.version,
                {"option_value_id": str(value.id), "changed_fields": ["translations"], "locales": [locale]},
            )
        )
        await self._audit("catalog.option_value_translation_updated", "success", value.id, {"locale": locale})
        return row

    # --- M3.1 Product Options ---

    async def set_product_options(self, product_id: UUID, expected: int, options: list[dict[str, Any]]) -> list[Any]:
        product = await self.repository.get_product(self.actor.tenant_id, product_id, lock=True)
        if product is None:
            await self._missing("product", product_id)
        await self._version("product", product, expected)
        ensure_product_mutable(product.status)
        seen: set[UUID] = set()
        normalized: list[dict[str, Any]] = []
        for item in options:
            option_id = item["option_id"]
            if option_id in seen:
                raise CatalogConflict("Duplicate Option in product options assignment")
            seen.add(option_id)
            option = await self.repository.get_option(self.actor.tenant_id, option_id)
            if option is None:
                await self._missing("option", option_id)
            ensure_reference_active(option.status, "Option")
            normalized.append({"option_id": option.id, "required": True, "position": item.get("position", 0)})
        limit = await self.repository.entitlement_limit(self.actor.tenant_id, "catalog.product_options.max_per_product")
        # This PUT replaces the whole set in one shot, so the check is on the final
        # size directly rather than the "current count before adding one more" shape
        # that ensure_quota/_quota assume for incremental creates.
        await self._options_quota("catalog.product_options.max_per_product", len(normalized) - 1, limit, product.id)
        existing = await self.repository.list_product_options(self.actor.tenant_id, product.id)
        existing_ids = {row.option_id for row in existing}
        removed_ids = existing_ids - seen
        for option_id in removed_ids:
            active = await self.repository.count_active_variants_using_option(self.actor.tenant_id, product.id, option_id)
            ensure_product_option_retirable(active)
        await self.repository.replace_product_options(self.actor.tenant_id, product.id, normalized)
        product.updated_by = self.actor.user_id
        product.version += 1
        added_ids = seen - existing_ids
        for option_id in added_ids:
            await self.repository.add_event(
                self._event(
                    "catalog.product.option_attached.v1", "catalog.product", product.id, product.version,
                    {"option_id": str(option_id)},
                )
            )
        for option_id in removed_ids:
            await self.repository.add_event(
                self._event(
                    "catalog.product.option_detached.v1", "catalog.product", product.id, product.version,
                    {"option_id": str(option_id)},
                )
            )
        await self._audit(
            "catalog.product_options_changed", "success", product.id,
            {"attached": [str(i) for i in added_ids], "detached": [str(i) for i in removed_ids]},
        )
        return await self.repository.list_product_options(self.actor.tenant_id, product.id)

    # --- M3.1 Variant Combinations ---

    async def _apply_combination(self, row: Any, product: Any, option_value_ids: list[UUID]) -> str | None:
        """Validate and persist a Variant's combination. Caller holds locks on both rows.

        Returns the new fingerprint (or None for an empty/no-Options combination).
        Bumps row.version and product.version and emits the created/updated event --
        the caller only needs to commit/audit around it.
        """
        product_options = [
            item for item in await self.repository.list_product_options(self.actor.tenant_id, product.id)
            if item.archived_at is None
        ]
        required_option_ids = frozenset(item.option_id for item in product_options)
        pairs: list[dict[str, Any]] = []
        fingerprint_pairs: list[tuple[UUID, UUID]] = []
        provided_option_ids: set[UUID] = set()
        for value_id in option_value_ids:
            value = await self.repository.get_option_value(self.actor.tenant_id, value_id)
            if value is None:
                await self._missing("option_value", value_id)
            ensure_reference_active(value.status, "Option Value")
            if value.option_id in provided_option_ids:
                raise CatalogConflict("Combination cannot include two values for the same Option")
            provided_option_ids.add(value.option_id)
            pairs.append({"option_id": value.option_id, "option_value_id": value.id})
            fingerprint_pairs.append((value.option_id, value.id))
        ensure_combination_complete(required_option_ids, frozenset(provided_option_ids))
        new_fingerprint = combination_fingerprint(fingerprint_pairs)
        is_new_combination = row.combination_fingerprint is None
        if new_fingerprint is not None:
            if is_new_combination:
                limit = await self.repository.entitlement_limit(
                    self.actor.tenant_id, "catalog.variant_combinations.max_per_product"
                )
                current = await self.repository.count_variant_combinations(self.actor.tenant_id, product.id)
                await self._options_quota("catalog.variant_combinations.max_per_product", current, limit, product.id)
            existing_owner = await self.repository.get_variant_by_fingerprint(
                self.actor.tenant_id, product.id, new_fingerprint
            )
            if existing_owner is not None and existing_owner.id != row.id:
                await self._audit(
                    "catalog.combination_duplicate", "denied", row.id,
                    {"product_id": str(product.id), "fingerprint": new_fingerprint},
                )
                raise CatalogConflict("This combination already exists for another Variant of this Product")
        await self.repository.replace_variant_option_values(self.actor.tenant_id, row.id, product.id, pairs)
        await self.repository.set_variant_fingerprint(self.actor.tenant_id, row.id, new_fingerprint)
        row.updated_by = self.actor.user_id
        row.version += 1
        product.updated_by = self.actor.user_id
        product.version += 1
        event_type = "catalog.variant.combination_created.v1" if is_new_combination else "catalog.variant.combination_updated.v1"
        await self.repository.add_event(
            self._event(
                event_type, "catalog.product", product.id, product.version,
                {"variant_id": str(row.id), "fingerprint": new_fingerprint},
            )
        )
        return new_fingerprint

    async def set_variant_combination(self, variant_id: UUID, expected: int, option_value_ids: list[UUID]) -> Any:
        variant = await self.repository.get_variant(self.actor.tenant_id, variant_id)
        if variant is None:
            await self._missing("variant", variant_id)
        product = await self.repository.get_product(self.actor.tenant_id, variant.product_id, lock=True)
        if product is None:
            await self._missing("product", variant.product_id)
        row = await self.repository.get_variant(self.actor.tenant_id, variant_id, lock=True)
        if row is None:
            await self._missing("variant", variant_id)
        await self._version("variant", row, expected)
        ensure_product_mutable(product.status)
        if row.status == "archived":
            raise CatalogPolicyError("Archived variants cannot be updated")
        fingerprint = await self._apply_combination(row, product, option_value_ids)
        await self._audit(
            "catalog.variant_combination_set", "success", row.id,
            {"product_id": str(product.id), "fingerprint": fingerprint},
        )
        return row

    async def preview_variant_generation(self, product_id: UUID) -> dict[str, Any]:
        """Read-only: never writes, never runs inside the durable generation Job.

        Returns the ten fields required by the M3.1 design
        (docs/architecture/catalog-option-combinations.md section 2): options
        considered, per-Option Value counts, theoretical total, existing/new/
        duplicate combinations, tenant limit, remaining capacity, warnings and
        estimated work. `duplicate_combinations` is always 0 in this
        increment -- generation always targets "everything missing from the
        full cartesian", there is no per-combination candidate selection UI
        yet that could produce duplicates within a single request.
        """
        product = await self.repository.get_product(self.actor.tenant_id, product_id)
        if product is None:
            await self._missing("product", product_id)
        product_options = [
            item for item in await self.repository.list_product_options(self.actor.tenant_id, product.id)
            if item.archived_at is None
        ]
        if not product_options:
            raise CatalogPolicyError("Product has no active Options to generate combinations from")
        options_considered: list[dict[str, Any]] = []
        theoretical_total = 1
        warnings: list[str] = []
        for po in product_options:
            option = await self.repository.get_option(self.actor.tenant_id, po.option_id)
            count = await self.repository.count_option_values(self.actor.tenant_id, po.option_id)
            options_considered.append(
                {"option_id": str(po.option_id), "code": option.code if option else None, "value_count": count}
            )
            if count == 0:
                warnings.append(f"Option {option.code if option else po.option_id} has no active Values")
            theoretical_total *= count
        existing_combinations = await self.repository.count_variant_combinations(self.actor.tenant_id, product.id)
        new_combinations = max(theoretical_total - existing_combinations, 0)
        tenant_limit = await self.repository.entitlement_limit(
            self.actor.tenant_id, "catalog.variant_combinations.max_per_product"
        )
        remaining_capacity = max(tenant_limit - existing_combinations, 0)
        operation_limit = await self.repository.entitlement_limit(
            self.actor.tenant_id, "catalog.combination_generation.max_per_operation"
        )
        estimated_work = new_combinations
        if estimated_work > operation_limit:
            warnings.append(
                f"Estimated work ({estimated_work}) exceeds catalog.combination_generation.max_per_operation ({operation_limit})"
            )
        if estimated_work > remaining_capacity:
            warnings.append(f"Estimated work ({estimated_work}) exceeds remaining capacity ({remaining_capacity})")
        return {
            "options_considered": options_considered,
            "theoretical_total": theoretical_total,
            "existing_combinations": existing_combinations,
            "new_combinations": new_combinations,
            "duplicate_combinations": 0,
            "tenant_limit": tenant_limit,
            "remaining_capacity": remaining_capacity,
            "warnings": warnings,
            "estimated_work": estimated_work,
        }

    # --- M3.2 Attributes and Product Specifications ---

    async def create_attribute(self, data: dict[str, Any]) -> Any:
        data_type = data["data_type"]
        if data_type not in ATTRIBUTE_DATA_TYPES:
            raise CatalogPolicyError(f"Unsupported attribute data_type: {data_type}")
        row = await self.repository.create_attribute(
            self.actor.tenant_id,
            self.actor.user_id,
            {
                "code": normalized_code(data["code"]),
                "name": data["name"].strip(),
                "description": data.get("description"),
                "data_type": data_type,
                "unit": data.get("unit"),
                "is_required": data.get("is_required", False),
                "is_filterable": data.get("is_filterable", False),
                "is_searchable": data.get("is_searchable", False),
                "is_comparable": data.get("is_comparable", False),
                "is_visible_storefront": data.get("is_visible_storefront", True),
                "position": data.get("position", 0),
                "status": "active",
            },
        )
        await self.repository.flush()
        await self.repository.add_event(
            self._event(
                "catalog.attribute.created.v1", "catalog.attribute", row.id, row.version,
                {"code": row.code, "name": row.name, "data_type": row.data_type},
            )
        )
        await self._audit("catalog.attribute_created", "success", row.id)
        return row

    async def update_attribute(self, resource_id: UUID, expected: int, data: dict[str, Any]) -> Any:
        row = await self.repository.get_attribute(self.actor.tenant_id, resource_id, lock=True)
        if row is None:
            await self._missing("attribute", resource_id)
        await self._version("attribute", row, expected)
        ensure_reference_active(row.status, "Attribute")
        ensure_attribute_type_immutable(row.data_type, data.get("data_type"))
        changed: list[str] = []
        for field in (
            "name", "description", "unit", "is_required", "is_filterable",
            "is_searchable", "is_comparable", "is_visible_storefront", "position",
        ):
            if field in data and data[field] is not None:
                value = data[field].strip() if isinstance(data[field], str) else data[field]
                if getattr(row, field) != value:
                    setattr(row, field, value)
                    changed.append(field)
        row.updated_by = self.actor.user_id
        row.version += 1
        await self.repository.add_event(
            self._event("catalog.attribute.updated.v1", "catalog.attribute", row.id, row.version, {"changed_fields": changed})
        )
        await self._audit("catalog.attribute_updated", "success", row.id, {"changed_fields": changed})
        return row

    async def archive_attribute(self, resource_id: UUID, expected: int) -> Any:
        row = await self.repository.get_attribute(self.actor.tenant_id, resource_id, lock=True)
        if row is None:
            await self._missing("attribute", resource_id)
        await self._version("attribute", row, expected)
        if row.status != "archived":
            row.status = "archived"
            row.archived_at = datetime.now(UTC)
            row.updated_by = self.actor.user_id
            row.version += 1
            await self.repository.add_event(
                self._event("catalog.attribute.archived.v1", "catalog.attribute", row.id, row.version, {"status": row.status})
            )
            await self._audit("catalog.attribute_archived", "success", row.id)
        return row

    async def restore_attribute(self, resource_id: UUID, expected: int) -> Any:
        row = await self.repository.get_attribute(self.actor.tenant_id, resource_id, lock=True)
        if row is None:
            await self._missing("attribute", resource_id)
        await self._version("attribute", row, expected)
        if row.status == "archived":
            row.status = "active"
            row.archived_at = None
            row.updated_by = self.actor.user_id
            row.version += 1
            await self.repository.add_event(
                self._event("catalog.attribute.restored.v1", "catalog.attribute", row.id, row.version, {"status": row.status})
            )
            await self._audit("catalog.attribute_restored", "success", row.id)
        return row

    async def upsert_attribute_translation(self, attribute_id: UUID, locale_value: str, data: dict[str, Any]) -> Any:
        attribute = await self.repository.get_attribute(self.actor.tenant_id, attribute_id, lock=True)
        if attribute is None:
            await self._missing("attribute", attribute_id)
        ensure_reference_active(attribute.status, "Attribute")
        locale = normalize_locale(locale_value)
        row = await self.repository.upsert_attribute_translation(
            self.actor.tenant_id, attribute.id, locale,
            {"name": data["name"].strip(), "description": data.get("description")},
        )
        attribute.updated_by = self.actor.user_id
        attribute.version += 1
        await self.repository.flush()
        await self.repository.add_event(
            self._event(
                "catalog.attribute.updated.v1", "catalog.attribute", attribute.id, attribute.version,
                {"changed_fields": ["translations"], "locales": [locale]},
            )
        )
        await self._audit("catalog.attribute_translation_updated", "success", attribute.id, {"locale": locale})
        return row

    async def create_attribute_option(self, attribute_id: UUID, data: dict[str, Any]) -> Any:
        attribute = await self.repository.get_attribute(self.actor.tenant_id, attribute_id, lock=True)
        if attribute is None:
            await self._missing("attribute", attribute_id)
        ensure_reference_active(attribute.status, "Attribute")
        ensure_attribute_options_supported(attribute.data_type)
        limit = await self.repository.entitlement_limit(self.actor.tenant_id, "catalog.attribute_options.max_per_attribute")
        current = await self.repository.count_attribute_options(self.actor.tenant_id, attribute.id)
        await self._attributes_quota("catalog.attribute_options.max_per_attribute", current, limit, attribute.id)
        row = await self.repository.create_attribute_option(
            self.actor.tenant_id,
            self.actor.user_id,
            {
                "attribute_id": attribute.id,
                "code": normalized_code(data["code"]),
                "label": data["label"].strip(),
                "position": data.get("position", 0),
                "status": "active",
            },
        )
        await self.repository.flush()
        await self.repository.add_event(
            self._event(
                "catalog.attribute_option.created.v1", "catalog.attribute", attribute.id, attribute.version,
                {"attribute_option_id": str(row.id), "code": row.code, "label": row.label},
            )
        )
        await self._audit("catalog.attribute_option_created", "success", row.id, {"attribute_id": str(attribute.id)})
        return row

    async def update_attribute_option(self, resource_id: UUID, expected: int, data: dict[str, Any]) -> Any:
        row = await self.repository.get_attribute_option(self.actor.tenant_id, resource_id, lock=True)
        if row is None:
            await self._missing("attribute_option", resource_id)
        await self._version("attribute_option", row, expected)
        ensure_reference_active(row.status, "Attribute Option")
        changed: list[str] = []
        for field in ("label", "position"):
            if field in data and data[field] is not None:
                value = data[field].strip() if isinstance(data[field], str) else data[field]
                if getattr(row, field) != value:
                    setattr(row, field, value)
                    changed.append(field)
        row.updated_by = self.actor.user_id
        row.version += 1
        await self.repository.add_event(
            self._event(
                "catalog.attribute_option.updated.v1", "catalog.attribute", row.attribute_id, row.version,
                {"attribute_option_id": str(row.id), "changed_fields": changed},
            )
        )
        await self._audit("catalog.attribute_option_updated", "success", row.id, {"changed_fields": changed})
        return row

    async def archive_attribute_option(self, resource_id: UUID, expected: int) -> Any:
        row = await self.repository.get_attribute_option(self.actor.tenant_id, resource_id, lock=True)
        if row is None:
            await self._missing("attribute_option", resource_id)
        await self._version("attribute_option", row, expected)
        if row.status != "archived":
            row.status = "archived"
            row.archived_at = datetime.now(UTC)
            row.updated_by = self.actor.user_id
            row.version += 1
            await self.repository.add_event(
                self._event(
                    "catalog.attribute_option.archived.v1", "catalog.attribute", row.attribute_id, row.version,
                    {"attribute_option_id": str(row.id), "status": row.status},
                )
            )
            await self._audit("catalog.attribute_option_archived", "success", row.id)
        return row

    async def upsert_attribute_option_translation(self, attribute_option_id: UUID, locale_value: str, data: dict[str, Any]) -> Any:
        value = await self.repository.get_attribute_option(self.actor.tenant_id, attribute_option_id, lock=True)
        if value is None:
            await self._missing("attribute_option", attribute_option_id)
        ensure_reference_active(value.status, "Attribute Option")
        locale = normalize_locale(locale_value)
        row = await self.repository.upsert_attribute_option_translation(
            self.actor.tenant_id, value.id, locale, {"label": data["label"].strip()}
        )
        value.updated_by = self.actor.user_id
        value.version += 1
        await self.repository.flush()
        await self.repository.add_event(
            self._event(
                "catalog.attribute_option.updated.v1", "catalog.attribute", value.attribute_id, value.version,
                {"attribute_option_id": str(value.id), "changed_fields": ["translations"], "locales": [locale]},
            )
        )
        await self._audit("catalog.attribute_option_translation_updated", "success", value.id, {"locale": locale})
        return row

    async def create_attribute_group(self, data: dict[str, Any]) -> Any:
        row = await self.repository.create_attribute_group(
            self.actor.tenant_id,
            self.actor.user_id,
            {
                "code": normalized_code(data["code"]),
                "name": data["name"].strip(),
                "description": data.get("description"),
                "position": data.get("position", 0),
                "status": "active",
            },
        )
        await self.repository.flush()
        await self.repository.add_event(
            self._event("catalog.attribute_group.created.v1", "catalog.attribute_group", row.id, row.version, {"code": row.code})
        )
        await self._audit("catalog.attribute_group_created", "success", row.id)
        return row

    async def update_attribute_group(self, resource_id: UUID, expected: int, data: dict[str, Any]) -> Any:
        row = await self.repository.get_attribute_group(self.actor.tenant_id, resource_id, lock=True)
        if row is None:
            await self._missing("attribute_group", resource_id)
        await self._version("attribute_group", row, expected)
        ensure_reference_active(row.status, "Attribute Group")
        changed: list[str] = []
        for field in ("name", "description", "position"):
            if field in data and data[field] is not None:
                value = data[field].strip() if isinstance(data[field], str) else data[field]
                if getattr(row, field) != value:
                    setattr(row, field, value)
                    changed.append(field)
        row.updated_by = self.actor.user_id
        row.version += 1
        await self.repository.add_event(
            self._event("catalog.attribute_group.updated.v1", "catalog.attribute_group", row.id, row.version, {"changed_fields": changed})
        )
        await self._audit("catalog.attribute_group_updated", "success", row.id, {"changed_fields": changed})
        return row

    async def archive_attribute_group(self, resource_id: UUID, expected: int) -> Any:
        row = await self.repository.get_attribute_group(self.actor.tenant_id, resource_id, lock=True)
        if row is None:
            await self._missing("attribute_group", resource_id)
        await self._version("attribute_group", row, expected)
        if row.status != "archived":
            row.status = "archived"
            row.archived_at = datetime.now(UTC)
            row.updated_by = self.actor.user_id
            row.version += 1
            await self.repository.add_event(
                self._event("catalog.attribute_group.archived.v1", "catalog.attribute_group", row.id, row.version, {"status": row.status})
            )
            await self._audit("catalog.attribute_group_archived", "success", row.id)
        return row

    async def restore_attribute_group(self, resource_id: UUID, expected: int) -> Any:
        row = await self.repository.get_attribute_group(self.actor.tenant_id, resource_id, lock=True)
        if row is None:
            await self._missing("attribute_group", resource_id)
        await self._version("attribute_group", row, expected)
        if row.status == "archived":
            row.status = "active"
            row.archived_at = None
            row.updated_by = self.actor.user_id
            row.version += 1
            await self.repository.add_event(
                self._event("catalog.attribute_group.restored.v1", "catalog.attribute_group", row.id, row.version, {"status": row.status})
            )
            await self._audit("catalog.attribute_group_restored", "success", row.id)
        return row

    async def upsert_attribute_group_translation(self, group_id: UUID, locale_value: str, data: dict[str, Any]) -> Any:
        group = await self.repository.get_attribute_group(self.actor.tenant_id, group_id, lock=True)
        if group is None:
            await self._missing("attribute_group", group_id)
        ensure_reference_active(group.status, "Attribute Group")
        locale = normalize_locale(locale_value)
        row = await self.repository.upsert_attribute_group_translation(
            self.actor.tenant_id, group.id, locale,
            {"name": data["name"].strip(), "description": data.get("description")},
        )
        group.updated_by = self.actor.user_id
        group.version += 1
        await self.repository.flush()
        await self.repository.add_event(
            self._event(
                "catalog.attribute_group.updated.v1", "catalog.attribute_group", group.id, group.version,
                {"changed_fields": ["translations"], "locales": [locale]},
            )
        )
        await self._audit("catalog.attribute_group_translation_updated", "success", group.id, {"locale": locale})
        return row

    async def set_product_type_attributes(
        self, product_type_id: UUID, expected: int, assignments: list[dict[str, Any]]
    ) -> list[Any]:
        product_type = await self.repository.get_product_type(self.actor.tenant_id, product_type_id, lock=True)
        if product_type is None:
            await self._missing("product_type", product_type_id)
        await self._version("product_type", product_type, expected)
        seen: set[UUID] = set()
        normalized: list[dict[str, Any]] = []
        for item in assignments:
            attribute_id = item["attribute_id"]
            if attribute_id in seen:
                raise CatalogConflict("Duplicate Attribute in product type attribute assignment")
            seen.add(attribute_id)
            attribute = await self.repository.get_attribute(self.actor.tenant_id, attribute_id)
            if attribute is None:
                await self._missing("attribute", attribute_id)
            ensure_product_type_attribute_assignable(attribute.status)
            group_id = item.get("group_id")
            if group_id is not None:
                group = await self.repository.get_attribute_group(self.actor.tenant_id, group_id)
                if group is None:
                    await self._missing("attribute_group", group_id)
                ensure_reference_active(group.status, "Attribute Group")
            normalized.append(
                {
                    "attribute_id": attribute.id,
                    "group_id": group_id,
                    "position": item.get("position", 0),
                    "required": item.get("required", False),
                    "visible_override": item.get("visible_override"),
                    "filterable_override": item.get("filterable_override"),
                    "comparable_override": item.get("comparable_override"),
                }
            )
        limit = await self.repository.entitlement_limit(
            self.actor.tenant_id, "catalog.product_type_attributes.max_per_product_type"
        )
        await self._attributes_quota(
            "catalog.product_type_attributes.max_per_product_type", len(normalized) - 1, limit, product_type.id
        )
        existing = await self.repository.list_product_type_attributes(self.actor.tenant_id, product_type.id)
        existing_ids = {row.attribute_id for row in existing}
        await self.repository.replace_product_type_attributes(self.actor.tenant_id, product_type.id, normalized)
        product_type.updated_by = self.actor.user_id
        product_type.version += 1
        await self.repository.add_event(
            self._event(
                "catalog.product_type.attributes_changed.v1", "catalog.product_type", product_type.id, product_type.version,
                {"attribute_ids": [str(i) for i in seen]},
            )
        )
        await self._audit(
            "catalog.product_type_attributes_changed", "success", product_type.id,
            {"attached": [str(i) for i in seen - existing_ids], "detached": [str(i) for i in existing_ids - seen]},
        )
        return await self.repository.list_product_type_attributes(self.actor.tenant_id, product_type.id)

    async def set_product_attribute_values(
        self, product_id: UUID, expected: int, values: list[dict[str, Any]]
    ) -> list[Any]:
        product = await self.repository.get_product(self.actor.tenant_id, product_id, lock=True)
        if product is None:
            await self._missing("product", product_id)
        await self._version("product", product, expected)
        ensure_product_mutable(product.status)

        assignments = [
            item for item in await self.repository.list_product_type_attributes(self.actor.tenant_id, product.product_type_id)
            if item.archived_at is None
        ]
        assignment_by_attribute = {item.attribute_id: item for item in assignments}

        rows: list[dict[str, Any]] = []
        multi_select: list[dict[str, Any]] = []
        provided_attribute_ids: set[UUID] = set()
        for item in values:
            attribute_id = item["attribute_id"]
            if attribute_id in provided_attribute_ids:
                raise CatalogConflict("Duplicate Attribute in product specification values")
            provided_attribute_ids.add(attribute_id)
            assignment = assignment_by_attribute.get(attribute_id)
            attribute = await self.repository.get_attribute(self.actor.tenant_id, attribute_id)
            if attribute is None:
                await self._missing("attribute", attribute_id)
            ensure_product_attribute_value_assignable(attribute.status, assignment is not None)

            row: dict[str, Any] = {
                "attribute_id": attribute.id,
                "value_text": None,
                "value_long_text": None,
                "value_integer": None,
                "value_decimal": None,
                "value_boolean": None,
                "value_date": None,
                "value_datetime": None,
                "value_option_id": None,
                "updated_by": self.actor.user_id,
            }
            if attribute.data_type == "MULTI_SELECT":
                try:
                    option_ids = normalize_multi_select_values(item.get("value"))
                except ValueError as exc:
                    raise CatalogPolicyError(str(exc)) from exc
                for option_id in option_ids:
                    option = await self.repository.get_attribute_option(self.actor.tenant_id, option_id)
                    if option is None or option.attribute_id != attribute.id:
                        raise CatalogPolicyError("MULTI_SELECT value references an Attribute Option that does not belong to this Attribute")
                    ensure_reference_active(option.status, "Attribute Option")
                    multi_select.append({"attribute_id": attribute.id, "attribute_option_id": option_id})
            else:
                try:
                    column, python_value = normalize_attribute_value(attribute.data_type, item.get("value"))
                except ValueError as exc:
                    raise CatalogPolicyError(str(exc)) from exc
                if column == "value_option_id":
                    option = await self.repository.get_attribute_option(self.actor.tenant_id, python_value)
                    if option is None or option.attribute_id != attribute.id:
                        raise CatalogPolicyError("SELECT value references an Attribute Option that does not belong to this Attribute")
                    ensure_reference_active(option.status, "Attribute Option")
                row[column] = python_value
            rows.append(row)

        required_attribute_ids = frozenset(item.attribute_id for item in assignments if item.required)
        ensure_required_attributes_present(required_attribute_ids, frozenset(provided_attribute_ids))

        await self.repository.replace_product_attribute_values(self.actor.tenant_id, product.id, rows, multi_select)
        product.updated_by = self.actor.user_id
        product.version += 1
        await self.repository.add_event(
            self._event(
                "catalog.product.attribute_values_changed.v1", "catalog.product", product.id, product.version,
                {"attribute_ids": [str(i) for i in provided_attribute_ids]},
            )
        )
        await self._audit(
            "catalog.product_attribute_values_changed", "success", product.id,
            {"attribute_ids": [str(i) for i in provided_attribute_ids]},
        )
        return await self.repository.list_product_attribute_values(self.actor.tenant_id, product.id)

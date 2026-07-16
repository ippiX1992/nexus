from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, NoReturn
from uuid import UUID

from app.application.auth import audit
from app.modules.catalog.contracts.repositories import CatalogRepository
from app.modules.catalog.domain.policies import (
    CatalogConflict,
    CatalogNotFound,
    CatalogPolicyError,
    CatalogQuotaExceeded,
    CatalogVersionConflict,
    CategoryCycle,
    ensure_expected_version,
    ensure_product_activation,
    ensure_product_mutable,
    ensure_quota,
    ensure_reference_active,
    ensure_store_assignment,
    ensure_variant_archive,
)
from app.modules.catalog.domain.values import (
    normalize_identifier,
    normalize_locale,
    normalize_sku,
    normalize_slug,
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

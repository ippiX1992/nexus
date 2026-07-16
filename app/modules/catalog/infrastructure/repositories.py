from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, delete, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.infrastructure.models import (
    BrandModel,
    CategoryClosureModel,
    CategoryModel,
    OptionModel,
    OptionTranslationModel,
    OptionValueModel,
    OptionValueTranslationModel,
    ProductCategoryModel,
    ProductIdentifierModel,
    ProductModel,
    ProductOptionModel,
    ProductSeoModel,
    ProductStoreModel,
    ProductTranslationModel,
    ProductTypeModel,
    ProductVariantModel,
    TaxonomyModel,
    VariantOptionValueModel,
)
from app.modules.platform.contracts.events import EventEnvelope
from app.modules.platform.infrastructure.models import (
    EntitlementDefinitionModel,
    EntitlementOverrideModel,
    OutboxEventModel,
    StoreLocaleModel,
    StoreModel,
)

RESOURCE_MODELS: dict[str, Any] = {
    "product_type": ProductTypeModel,
    "brand": BrandModel,
    "taxonomy": TaxonomyModel,
    "option": OptionModel,
}


class SqlAlchemyCatalogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def lock_tenant(self, tenant_id: UUID) -> None:
        await self.session.execute(
            text(
                "SELECT pg_advisory_xact_lock(hashtextextended(CAST(:tenant_id AS text), 0))"
            ),
            {"tenant_id": str(tenant_id)},
        )

    async def entitlement_limit(self, tenant_id: UUID, key: str) -> int:
        value = await self.session.scalar(
            select(func.coalesce(EntitlementOverrideModel.value, EntitlementDefinitionModel.default_value))
            .select_from(EntitlementDefinitionModel)
            .outerjoin(
                EntitlementOverrideModel,
                (EntitlementOverrideModel.key == EntitlementDefinitionModel.key)
                & (EntitlementOverrideModel.tenant_id == tenant_id),
            )
            .where(EntitlementDefinitionModel.key == key)
        )
        if value is None:
            raise KeyError(f"Unknown entitlement {key}")
        return int(value)

    async def count_products(self, tenant_id: UUID) -> int:
        return int(
            await self.session.scalar(
                select(func.count()).select_from(ProductModel).where(
                    ProductModel.tenant_id == tenant_id, ProductModel.status != "archived"
                )
            )
            or 0
        )

    async def count_variants(self, tenant_id: UUID, product_id: UUID) -> int:
        return int(
            await self.session.scalar(
                select(func.count()).select_from(ProductVariantModel).where(
                    ProductVariantModel.tenant_id == tenant_id,
                    ProductVariantModel.product_id == product_id,
                    ProductVariantModel.status != "archived",
                )
            )
            or 0
        )

    async def count_active_variants(self, tenant_id: UUID, product_id: UUID) -> int:
        return int(
            await self.session.scalar(
                select(func.count()).select_from(ProductVariantModel).where(
                    ProductVariantModel.tenant_id == tenant_id,
                    ProductVariantModel.product_id == product_id,
                    ProductVariantModel.status == "active",
                )
            )
            or 0
        )

    async def _get(self, model: Any, tenant_id: UUID, resource_id: UUID, lock: bool) -> Any | None:
        statement = select(model).where(model.tenant_id == tenant_id, model.id == resource_id)
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def get_product_type(self, tenant_id: UUID, resource_id: UUID, *, lock: bool = False) -> ProductTypeModel | None:
        return await self._get(ProductTypeModel, tenant_id, resource_id, lock)

    async def get_brand(self, tenant_id: UUID, resource_id: UUID, *, lock: bool = False) -> BrandModel | None:
        return await self._get(BrandModel, tenant_id, resource_id, lock)

    async def get_product(self, tenant_id: UUID, resource_id: UUID, *, lock: bool = False) -> ProductModel | None:
        return await self._get(ProductModel, tenant_id, resource_id, lock)

    async def get_variant(self, tenant_id: UUID, resource_id: UUID, *, lock: bool = False) -> ProductVariantModel | None:
        return await self._get(ProductVariantModel, tenant_id, resource_id, lock)

    async def get_taxonomy(self, tenant_id: UUID, resource_id: UUID, *, lock: bool = False) -> TaxonomyModel | None:
        return await self._get(TaxonomyModel, tenant_id, resource_id, lock)

    async def get_category(self, tenant_id: UUID, resource_id: UUID, *, lock: bool = False) -> CategoryModel | None:
        return await self._get(CategoryModel, tenant_id, resource_id, lock)

    async def get_identifier(self, tenant_id: UUID, resource_id: UUID, *, lock: bool = False) -> ProductIdentifierModel | None:
        return await self._get(ProductIdentifierModel, tenant_id, resource_id, lock)

    async def get_store(self, tenant_id: UUID, resource_id: UUID, *, lock: bool = False) -> StoreModel | None:
        return await self._get(StoreModel, tenant_id, resource_id, lock)

    async def get_store_assignment(
        self, tenant_id: UUID, product_id: UUID, store_id: UUID, *, lock: bool = False
    ) -> ProductStoreModel | None:
        statement = select(ProductStoreModel).where(
            ProductStoreModel.tenant_id == tenant_id,
            ProductStoreModel.product_id == product_id,
            ProductStoreModel.store_id == store_id,
        )
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def locale_enabled(self, tenant_id: UUID, locale: str) -> bool:
        value = await self.session.scalar(
            select(StoreLocaleModel.locale_code)
            .join(
                StoreModel,
                (StoreModel.tenant_id == StoreLocaleModel.tenant_id)
                & (StoreModel.id == StoreLocaleModel.store_id),
            )
            .where(
                StoreLocaleModel.tenant_id == tenant_id,
                StoreLocaleModel.locale_code == locale,
                StoreModel.status != "archived",
            )
            .limit(1)
        )
        return value is not None

    @staticmethod
    def _after_cursor(statement: Any, model: Any, cursor: tuple[datetime, UUID] | None) -> Any:
        if cursor is None:
            return statement
        created_at, resource_id = cursor
        return statement.where(
            or_(model.created_at < created_at, and_(model.created_at == created_at, model.id < resource_id))
        )

    async def list_resources(
        self,
        kind: str,
        tenant_id: UUID,
        *,
        limit: int,
        cursor: tuple[datetime, UUID] | None,
        status: str | None = None,
    ) -> tuple[list[Any], bool]:
        model = RESOURCE_MODELS[kind]
        statement = select(model).where(model.tenant_id == tenant_id)
        if status:
            statement = statement.where(model.status == status)
        statement = self._after_cursor(statement, model, cursor).order_by(model.created_at.desc(), model.id.desc()).limit(limit + 1)
        rows = list((await self.session.scalars(statement)).all())
        return rows[:limit], len(rows) > limit

    async def list_products(
        self,
        tenant_id: UUID,
        *,
        limit: int,
        cursor: tuple[datetime, UUID] | None,
        status: str | None,
        product_type_id: UUID | None,
        brand_id: UUID | None,
        store_id: UUID | None,
        search: str | None,
    ) -> tuple[list[ProductModel], bool]:
        statement = select(ProductModel).where(ProductModel.tenant_id == tenant_id)
        if status:
            statement = statement.where(ProductModel.status == status)
        if product_type_id:
            statement = statement.where(ProductModel.product_type_id == product_type_id)
        if brand_id:
            statement = statement.where(ProductModel.brand_id == brand_id)
        if store_id:
            statement = statement.join(
                ProductStoreModel,
                (ProductStoreModel.tenant_id == ProductModel.tenant_id)
                & (ProductStoreModel.product_id == ProductModel.id),
            ).where(ProductStoreModel.store_id == store_id, ProductStoreModel.status != "archived")
        if search:
            term = search.strip().casefold() + "%"
            statement = (
                statement.outerjoin(
                    ProductVariantModel,
                    (ProductVariantModel.tenant_id == ProductModel.tenant_id)
                    & (ProductVariantModel.product_id == ProductModel.id),
                )
                .outerjoin(
                    ProductTranslationModel,
                    (ProductTranslationModel.tenant_id == ProductModel.tenant_id)
                    & (ProductTranslationModel.product_id == ProductModel.id),
                )
                .where(
                    or_(
                        ProductVariantModel.sku_normalized.like(term),
                        func.lower(ProductTranslationModel.name).like(term),
                    )
                )
                .distinct()
            )
        statement = self._after_cursor(statement, ProductModel, cursor)
        statement = statement.order_by(ProductModel.created_at.desc(), ProductModel.id.desc()).limit(limit + 1)
        rows = list((await self.session.scalars(statement)).unique().all())
        return rows[:limit], len(rows) > limit

    async def list_variants(
        self,
        tenant_id: UUID,
        product_id: UUID,
        *,
        limit: int,
        cursor: tuple[datetime, UUID] | None,
    ) -> tuple[list[ProductVariantModel], bool]:
        statement = select(ProductVariantModel).where(
            ProductVariantModel.tenant_id == tenant_id, ProductVariantModel.product_id == product_id
        )
        statement = self._after_cursor(statement, ProductVariantModel, cursor)
        statement = statement.order_by(ProductVariantModel.created_at.desc(), ProductVariantModel.id.desc()).limit(limit + 1)
        rows = list((await self.session.scalars(statement)).all())
        return rows[:limit], len(rows) > limit

    async def list_identifiers(self, tenant_id: UUID, variant_id: UUID) -> list[ProductIdentifierModel]:
        return list(
            (
                await self.session.scalars(
                    select(ProductIdentifierModel).where(
                        ProductIdentifierModel.tenant_id == tenant_id,
                        ProductIdentifierModel.variant_id == variant_id,
                        ProductIdentifierModel.archived_at.is_(None),
                    ).order_by(ProductIdentifierModel.created_at, ProductIdentifierModel.id)
                )
            ).all()
        )

    async def list_translations(self, tenant_id: UUID, product_id: UUID) -> list[ProductTranslationModel]:
        return list(
            (
                await self.session.scalars(
                    select(ProductTranslationModel).where(
                        ProductTranslationModel.tenant_id == tenant_id,
                        ProductTranslationModel.product_id == product_id,
                    ).order_by(ProductTranslationModel.locale)
                )
            ).all()
        )

    async def list_seo(self, tenant_id: UUID, product_id: UUID) -> list[ProductSeoModel]:
        return list(
            (
                await self.session.scalars(
                    select(ProductSeoModel).where(
                        ProductSeoModel.tenant_id == tenant_id, ProductSeoModel.product_id == product_id
                    ).order_by(ProductSeoModel.locale)
                )
            ).all()
        )

    async def list_categories(self, tenant_id: UUID, taxonomy_id: UUID) -> list[CategoryModel]:
        return list(
            (
                await self.session.scalars(
                    select(CategoryModel).where(
                        CategoryModel.tenant_id == tenant_id, CategoryModel.taxonomy_id == taxonomy_id
                    ).order_by(CategoryModel.parent_id.nullsfirst(), CategoryModel.position, CategoryModel.id)
                )
            ).all()
        )

    async def list_product_categories(self, tenant_id: UUID, product_id: UUID) -> list[ProductCategoryModel]:
        return list(
            (
                await self.session.scalars(
                    select(ProductCategoryModel).where(
                        ProductCategoryModel.tenant_id == tenant_id,
                        ProductCategoryModel.product_id == product_id,
                    ).order_by(ProductCategoryModel.taxonomy_id, ProductCategoryModel.position)
                )
            ).all()
        )

    async def list_product_stores(self, tenant_id: UUID, product_id: UUID) -> list[ProductStoreModel]:
        return list(
            (
                await self.session.scalars(
                    select(ProductStoreModel).where(
                        ProductStoreModel.tenant_id == tenant_id, ProductStoreModel.product_id == product_id
                    ).order_by(ProductStoreModel.created_at, ProductStoreModel.id)
                )
            ).all()
        )

    async def create_product_type(self, tenant_id: UUID, actor_id: UUID, data: dict[str, Any]) -> ProductTypeModel:
        row = ProductTypeModel(tenant_id=tenant_id, created_by=actor_id, updated_by=actor_id, **data)
        self.session.add(row)
        return row

    async def create_brand(self, tenant_id: UUID, actor_id: UUID, data: dict[str, Any]) -> BrandModel:
        row = BrandModel(tenant_id=tenant_id, created_by=actor_id, updated_by=actor_id, **data)
        self.session.add(row)
        return row

    async def create_product(self, tenant_id: UUID, actor_id: UUID, data: dict[str, Any]) -> ProductModel:
        row = ProductModel(tenant_id=tenant_id, created_by=actor_id, updated_by=actor_id, **data)
        self.session.add(row)
        return row

    async def create_variant(self, tenant_id: UUID, actor_id: UUID, data: dict[str, Any]) -> ProductVariantModel:
        row = ProductVariantModel(tenant_id=tenant_id, created_by=actor_id, updated_by=actor_id, **data)
        self.session.add(row)
        return row

    async def create_identifier(self, tenant_id: UUID, data: dict[str, Any]) -> ProductIdentifierModel:
        row = ProductIdentifierModel(tenant_id=tenant_id, **data)
        self.session.add(row)
        return row

    async def upsert_translation(
        self, tenant_id: UUID, product_id: UUID, locale: str, data: dict[str, Any]
    ) -> ProductTranslationModel:
        row = await self.session.scalar(
            select(ProductTranslationModel).where(
                ProductTranslationModel.tenant_id == tenant_id,
                ProductTranslationModel.product_id == product_id,
                ProductTranslationModel.locale == locale,
            ).with_for_update()
        )
        if row is None:
            row = ProductTranslationModel(tenant_id=tenant_id, product_id=product_id, locale=locale, **data)
            self.session.add(row)
        else:
            for key, value in data.items():
                setattr(row, key, value)
        return row

    async def upsert_seo(
        self, tenant_id: UUID, product_id: UUID, locale: str, data: dict[str, Any]
    ) -> ProductSeoModel:
        row = await self.session.scalar(
            select(ProductSeoModel).where(
                ProductSeoModel.tenant_id == tenant_id,
                ProductSeoModel.product_id == product_id,
                ProductSeoModel.locale == locale,
            ).with_for_update()
        )
        if row is None:
            row = ProductSeoModel(tenant_id=tenant_id, product_id=product_id, locale=locale, **data)
            self.session.add(row)
        else:
            for key, value in data.items():
                setattr(row, key, value)
        return row

    async def create_taxonomy(self, tenant_id: UUID, actor_id: UUID, data: dict[str, Any]) -> TaxonomyModel:
        row = TaxonomyModel(tenant_id=tenant_id, created_by=actor_id, updated_by=actor_id, **data)
        self.session.add(row)
        return row

    async def create_category(self, tenant_id: UUID, actor_id: UUID, data: dict[str, Any]) -> CategoryModel:
        row = CategoryModel(tenant_id=tenant_id, created_by=actor_id, updated_by=actor_id, **data)
        self.session.add(row)
        return row

    async def add_category_closure(
        self, tenant_id: UUID, taxonomy_id: UUID, category_id: UUID, parent_id: UUID | None
    ) -> None:
        self.session.add(
            CategoryClosureModel(
                tenant_id=tenant_id,
                taxonomy_id=taxonomy_id,
                ancestor_id=category_id,
                descendant_id=category_id,
                depth=0,
            )
        )
        if parent_id is None:
            return
        ancestors = (
            await self.session.execute(
                select(CategoryClosureModel.ancestor_id, CategoryClosureModel.depth).where(
                    CategoryClosureModel.tenant_id == tenant_id,
                    CategoryClosureModel.taxonomy_id == taxonomy_id,
                    CategoryClosureModel.descendant_id == parent_id,
                )
            )
        ).all()
        self.session.add_all(
            [
                CategoryClosureModel(
                    tenant_id=tenant_id,
                    taxonomy_id=taxonomy_id,
                    ancestor_id=ancestor_id,
                    descendant_id=category_id,
                    depth=depth + 1,
                )
                for ancestor_id, depth in ancestors
            ]
        )

    async def category_would_cycle(
        self, tenant_id: UUID, taxonomy_id: UUID, category_id: UUID, parent_id: UUID
    ) -> bool:
        value = await self.session.scalar(
            select(CategoryClosureModel.ancestor_id).where(
                CategoryClosureModel.tenant_id == tenant_id,
                CategoryClosureModel.taxonomy_id == taxonomy_id,
                CategoryClosureModel.ancestor_id == category_id,
                CategoryClosureModel.descendant_id == parent_id,
            )
        )
        return value is not None

    async def move_category_closure(
        self, tenant_id: UUID, taxonomy_id: UUID, category_id: UUID, parent_id: UUID | None
    ) -> None:
        subtree = (
            await self.session.execute(
                select(CategoryClosureModel.descendant_id, CategoryClosureModel.depth)
                .where(
                    CategoryClosureModel.tenant_id == tenant_id,
                    CategoryClosureModel.taxonomy_id == taxonomy_id,
                    CategoryClosureModel.ancestor_id == category_id,
                )
                .with_for_update()
            )
        ).all()
        descendant_ids = [row[0] for row in subtree]
        await self.session.execute(
            delete(CategoryClosureModel).where(
                CategoryClosureModel.tenant_id == tenant_id,
                CategoryClosureModel.taxonomy_id == taxonomy_id,
                CategoryClosureModel.descendant_id.in_(descendant_ids),
                CategoryClosureModel.ancestor_id.not_in(descendant_ids),
            )
        )
        if parent_id is None:
            return
        ancestors = (
            await self.session.execute(
                select(CategoryClosureModel.ancestor_id, CategoryClosureModel.depth).where(
                    CategoryClosureModel.tenant_id == tenant_id,
                    CategoryClosureModel.taxonomy_id == taxonomy_id,
                    CategoryClosureModel.descendant_id == parent_id,
                )
            )
        ).all()
        self.session.add_all(
            [
                CategoryClosureModel(
                    tenant_id=tenant_id,
                    taxonomy_id=taxonomy_id,
                    ancestor_id=ancestor_id,
                    descendant_id=descendant_id,
                    depth=ancestor_depth + 1 + subtree_depth,
                )
                for ancestor_id, ancestor_depth in ancestors
                for descendant_id, subtree_depth in subtree
            ]
        )

    async def replace_product_categories(
        self, tenant_id: UUID, product_id: UUID, assignments: list[dict[str, Any]]
    ) -> None:
        await self.session.execute(
            delete(ProductCategoryModel).where(
                ProductCategoryModel.tenant_id == tenant_id, ProductCategoryModel.product_id == product_id
            )
        )
        self.session.add_all(
            [ProductCategoryModel(tenant_id=tenant_id, product_id=product_id, **item) for item in assignments]
        )

    async def create_store_assignment(
        self, tenant_id: UUID, actor_id: UUID, data: dict[str, Any]
    ) -> ProductStoreModel:
        row = ProductStoreModel(tenant_id=tenant_id, created_by=actor_id, updated_by=actor_id, **data)
        self.session.add(row)
        return row

    # --- M3.1 Options and Variant Combinations ---
    async def get_option(self, tenant_id: UUID, resource_id: UUID, *, lock: bool = False) -> OptionModel | None:
        return await self._get(OptionModel, tenant_id, resource_id, lock)

    async def get_option_by_code(self, tenant_id: UUID, code: str) -> OptionModel | None:
        return await self.session.scalar(
            select(OptionModel).where(OptionModel.tenant_id == tenant_id, OptionModel.code == code)
        )

    async def get_option_value(self, tenant_id: UUID, resource_id: UUID, *, lock: bool = False) -> OptionValueModel | None:
        return await self._get(OptionValueModel, tenant_id, resource_id, lock)

    async def list_option_values(self, tenant_id: UUID, option_id: UUID) -> list[OptionValueModel]:
        return list(
            (
                await self.session.scalars(
                    select(OptionValueModel).where(
                        OptionValueModel.tenant_id == tenant_id, OptionValueModel.option_id == option_id
                    ).order_by(OptionValueModel.position, OptionValueModel.id)
                )
            ).all()
        )

    async def count_option_values(self, tenant_id: UUID, option_id: UUID) -> int:
        return int(
            await self.session.scalar(
                select(func.count()).select_from(OptionValueModel).where(
                    OptionValueModel.tenant_id == tenant_id,
                    OptionValueModel.option_id == option_id,
                    OptionValueModel.status != "archived",
                )
            )
            or 0
        )

    async def create_option(self, tenant_id: UUID, actor_id: UUID, data: dict[str, Any]) -> OptionModel:
        row = OptionModel(tenant_id=tenant_id, created_by=actor_id, updated_by=actor_id, **data)
        self.session.add(row)
        return row

    async def create_option_value(self, tenant_id: UUID, actor_id: UUID, data: dict[str, Any]) -> OptionValueModel:
        row = OptionValueModel(tenant_id=tenant_id, created_by=actor_id, updated_by=actor_id, **data)
        self.session.add(row)
        return row

    async def get_product_option(
        self, tenant_id: UUID, product_id: UUID, option_id: UUID, *, lock: bool = False
    ) -> ProductOptionModel | None:
        statement = select(ProductOptionModel).where(
            ProductOptionModel.tenant_id == tenant_id,
            ProductOptionModel.product_id == product_id,
            ProductOptionModel.option_id == option_id,
        )
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def list_product_options(self, tenant_id: UUID, product_id: UUID) -> list[ProductOptionModel]:
        return list(
            (
                await self.session.scalars(
                    select(ProductOptionModel).where(
                        ProductOptionModel.tenant_id == tenant_id,
                        ProductOptionModel.product_id == product_id,
                    ).order_by(ProductOptionModel.position, ProductOptionModel.option_id)
                )
            ).all()
        )

    async def count_product_options(self, tenant_id: UUID, product_id: UUID) -> int:
        return int(
            await self.session.scalar(
                select(func.count()).select_from(ProductOptionModel).where(
                    ProductOptionModel.tenant_id == tenant_id, ProductOptionModel.product_id == product_id
                )
            )
            or 0
        )

    async def replace_product_options(
        self, tenant_id: UUID, product_id: UUID, assignments: list[dict[str, Any]]
    ) -> None:
        await self.session.execute(
            delete(ProductOptionModel).where(
                ProductOptionModel.tenant_id == tenant_id, ProductOptionModel.product_id == product_id
            )
        )
        self.session.add_all(
            [ProductOptionModel(tenant_id=tenant_id, product_id=product_id, **item) for item in assignments]
        )

    async def count_active_variants_using_option(self, tenant_id: UUID, product_id: UUID, option_id: UUID) -> int:
        return int(
            await self.session.scalar(
                select(func.count(func.distinct(VariantOptionValueModel.variant_id)))
                .select_from(VariantOptionValueModel)
                .join(
                    ProductVariantModel,
                    (ProductVariantModel.tenant_id == VariantOptionValueModel.tenant_id)
                    & (ProductVariantModel.id == VariantOptionValueModel.variant_id),
                )
                .where(
                    VariantOptionValueModel.tenant_id == tenant_id,
                    VariantOptionValueModel.product_id == product_id,
                    VariantOptionValueModel.option_id == option_id,
                    ProductVariantModel.status == "active",
                )
            )
            or 0
        )

    async def count_variant_combinations(self, tenant_id: UUID, product_id: UUID) -> int:
        return int(
            await self.session.scalar(
                select(func.count()).select_from(ProductVariantModel).where(
                    ProductVariantModel.tenant_id == tenant_id,
                    ProductVariantModel.product_id == product_id,
                    ProductVariantModel.archived_at.is_(None),
                    ProductVariantModel.combination_fingerprint.is_not(None),
                )
            )
            or 0
        )

    async def get_variant_by_fingerprint(
        self, tenant_id: UUID, product_id: UUID, fingerprint: str
    ) -> ProductVariantModel | None:
        return await self.session.scalar(
            select(ProductVariantModel).where(
                ProductVariantModel.tenant_id == tenant_id,
                ProductVariantModel.product_id == product_id,
                ProductVariantModel.combination_fingerprint == fingerprint,
                ProductVariantModel.archived_at.is_(None),
            )
        )

    async def list_variant_option_values(self, tenant_id: UUID, variant_id: UUID) -> list[VariantOptionValueModel]:
        return list(
            (
                await self.session.scalars(
                    select(VariantOptionValueModel).where(
                        VariantOptionValueModel.tenant_id == tenant_id,
                        VariantOptionValueModel.variant_id == variant_id,
                    )
                )
            ).all()
        )

    async def replace_variant_option_values(
        self, tenant_id: UUID, variant_id: UUID, product_id: UUID, pairs: list[dict[str, Any]]
    ) -> None:
        await self.session.execute(
            delete(VariantOptionValueModel).where(
                VariantOptionValueModel.tenant_id == tenant_id, VariantOptionValueModel.variant_id == variant_id
            )
        )
        self.session.add_all(
            [
                VariantOptionValueModel(tenant_id=tenant_id, variant_id=variant_id, product_id=product_id, **item)
                for item in pairs
            ]
        )

    async def set_variant_fingerprint(self, tenant_id: UUID, variant_id: UUID, fingerprint: str | None) -> None:
        variant = await self.session.scalar(
            select(ProductVariantModel).where(
                ProductVariantModel.tenant_id == tenant_id, ProductVariantModel.id == variant_id
            ).with_for_update()
        )
        if variant is not None:
            variant.combination_fingerprint = fingerprint

    async def list_option_translations(self, tenant_id: UUID, option_id: UUID) -> list[OptionTranslationModel]:
        return list(
            (
                await self.session.scalars(
                    select(OptionTranslationModel).where(
                        OptionTranslationModel.tenant_id == tenant_id,
                        OptionTranslationModel.option_id == option_id,
                    ).order_by(OptionTranslationModel.locale)
                )
            ).all()
        )

    async def upsert_option_translation(
        self, tenant_id: UUID, option_id: UUID, locale: str, data: dict[str, Any]
    ) -> OptionTranslationModel:
        row = await self.session.scalar(
            select(OptionTranslationModel).where(
                OptionTranslationModel.tenant_id == tenant_id,
                OptionTranslationModel.option_id == option_id,
                OptionTranslationModel.locale == locale,
            ).with_for_update()
        )
        if row is None:
            row = OptionTranslationModel(tenant_id=tenant_id, option_id=option_id, locale=locale, **data)
            self.session.add(row)
        else:
            for key, value in data.items():
                setattr(row, key, value)
        return row

    async def list_option_value_translations(
        self, tenant_id: UUID, option_value_id: UUID
    ) -> list[OptionValueTranslationModel]:
        return list(
            (
                await self.session.scalars(
                    select(OptionValueTranslationModel).where(
                        OptionValueTranslationModel.tenant_id == tenant_id,
                        OptionValueTranslationModel.option_value_id == option_value_id,
                    ).order_by(OptionValueTranslationModel.locale)
                )
            ).all()
        )

    async def upsert_option_value_translation(
        self, tenant_id: UUID, option_value_id: UUID, locale: str, data: dict[str, Any]
    ) -> OptionValueTranslationModel:
        row = await self.session.scalar(
            select(OptionValueTranslationModel).where(
                OptionValueTranslationModel.tenant_id == tenant_id,
                OptionValueTranslationModel.option_value_id == option_value_id,
                OptionValueTranslationModel.locale == locale,
            ).with_for_update()
        )
        if row is None:
            row = OptionValueTranslationModel(
                tenant_id=tenant_id, option_value_id=option_value_id, locale=locale, **data
            )
            self.session.add(row)
        else:
            for key, value in data.items():
                setattr(row, key, value)
        return row

    async def add_event(self, envelope: EventEnvelope) -> None:
        payload = envelope.to_dict()
        self.session.add(
            OutboxEventModel(
                id=envelope.event_id,
                tenant_id=envelope.tenant_id,
                store_id=envelope.store_id,
                aggregate_type=envelope.aggregate_type,
                aggregate_id=envelope.aggregate_id,
                event_type=envelope.event_type,
                event_version=envelope.event_version,
                payload=payload,
                metadata_json={"actor": payload["actor"]},
                correlation_id=envelope.correlation_id,
                causation_id=envelope.causation_id,
                occurred_at=envelope.occurred_at,
                available_at=envelope.occurred_at,
            )
        )

    async def flush(self) -> None:
        await self.session.flush()

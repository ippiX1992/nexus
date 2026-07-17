from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.models import Base


class CatalogResourceMixin:
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class ProductTypeModel(CatalogResourceMixin, Base):
    __tablename__ = "catalog_product_types"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_catalog_product_types_tenant_id"),
        UniqueConstraint("tenant_id", "code", name="uq_catalog_product_types_tenant_code"),
        CheckConstraint("status IN ('active','archived')", name="ck_catalog_product_type_status"),
        CheckConstraint("version > 0", name="ck_catalog_product_type_version"),
        Index("ix_catalog_product_types_tenant_status_created", "tenant_id", "status", "created_at", "id"),
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")


class BrandModel(CatalogResourceMixin, Base):
    __tablename__ = "catalog_brands"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_catalog_brands_tenant_id"),
        UniqueConstraint("tenant_id", "code", name="uq_catalog_brands_tenant_code"),
        UniqueConstraint("tenant_id", "slug", name="uq_catalog_brands_tenant_slug"),
        CheckConstraint("status IN ('active','archived')", name="ck_catalog_brand_status"),
        CheckConstraint("version > 0", name="ck_catalog_brand_version"),
        Index("ix_catalog_brands_tenant_status_created", "tenant_id", "status", "created_at", "id"),
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")


class ProductModel(CatalogResourceMixin, Base):
    __tablename__ = "catalog_products"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "product_type_id"],
            ["catalog_product_types.tenant_id", "catalog_product_types.id"],
            ondelete="RESTRICT",
            name="fk_catalog_products_tenant_product_type",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "brand_id"],
            ["catalog_brands.tenant_id", "catalog_brands.id"],
            ondelete="RESTRICT",
            name="fk_catalog_products_tenant_brand",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_catalog_products_tenant_id"),
        UniqueConstraint("tenant_id", "code", name="uq_catalog_products_tenant_code"),
        CheckConstraint("status IN ('draft','active','archived')", name="ck_catalog_product_status"),
        CheckConstraint("version > 0", name="ck_catalog_product_version"),
        Index("ix_catalog_products_tenant_status_created", "tenant_id", "status", "created_at", "id"),
        Index("ix_catalog_products_tenant_type_status", "tenant_id", "product_type_id", "status", "id"),
        Index("ix_catalog_products_tenant_brand_status", "tenant_id", "brand_id", "status", "id"),
    )
    product_type_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    brand_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    code: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")


class ProductVariantModel(CatalogResourceMixin, Base):
    __tablename__ = "catalog_product_variants"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["catalog_products.tenant_id", "catalog_products.id"],
            ondelete="RESTRICT",
            name="fk_catalog_variants_tenant_product",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_catalog_variants_tenant_id"),
        UniqueConstraint("tenant_id", "product_id", "id", name="uq_catalog_variants_tenant_product_id"),
        UniqueConstraint("tenant_id", "sku_normalized", name="uq_catalog_variants_tenant_sku"),
        CheckConstraint(
            "status IN ('draft','active','archived')",
            name="ck_catalog_variant_status",
        ),
        CheckConstraint("length(sku_normalized) > 0", name="ck_catalog_variant_sku_nonempty"),
        CheckConstraint("version > 0", name="ck_catalog_variant_version"),
        Index(
            "uq_catalog_variant_default",
            "tenant_id",
            "product_id",
            unique=True,
            postgresql_where=text("is_default"),
        ),
        Index("ix_catalog_variants_tenant_product_status", "tenant_id", "product_id", "status", "created_at", "id"),
        CheckConstraint(
            "combination_fingerprint IS NULL OR combination_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_catalog_variant_fingerprint_format",
        ),
        Index(
            "uq_catalog_variant_combination_fingerprint",
            "tenant_id",
            "product_id",
            "combination_fingerprint",
            unique=True,
            postgresql_where=text("archived_at IS NULL AND combination_fingerprint IS NOT NULL"),
        ),
    )
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    sku: Mapped[str] = mapped_column(String(160), nullable=False)
    sku_normalized: Mapped[str] = mapped_column(String(160), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    combination_fingerprint: Mapped[str | None] = mapped_column(String(64))


class ProductIdentifierModel(Base):
    __tablename__ = "catalog_product_identifiers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["catalog_product_variants.tenant_id", "catalog_product_variants.id"],
            ondelete="RESTRICT",
            name="fk_catalog_identifiers_tenant_variant",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_catalog_identifiers_tenant_id"),
        UniqueConstraint(
            "tenant_id", "identifier_type", "normalized_value", name="uq_catalog_identifier_tenant_type_value"
        ),
        CheckConstraint(
            "identifier_type IN ('ean','upc','isbn','mpn','external')",
            name="ck_catalog_identifier_type",
        ),
        CheckConstraint("length(normalized_value) > 0", name="ck_catalog_identifier_nonempty"),
        CheckConstraint(
            "identifier_type <> 'external' OR source_system IS NOT NULL",
            name="ck_catalog_external_identifier_source",
        ),
        Index(
            "uq_catalog_identifier_primary",
            "tenant_id",
            "variant_id",
            "identifier_type",
            unique=True,
            postgresql_where=text("is_primary AND archived_at IS NULL"),
        ),
        Index("ix_catalog_identifiers_tenant_variant", "tenant_id", "variant_id", "archived_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    variant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    identifier_type: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_value: Mapped[str] = mapped_column(String(255), nullable=False)
    source_system: Mapped[str | None] = mapped_column(String(100))
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProductTranslationModel(Base):
    __tablename__ = "catalog_product_translations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["catalog_products.tenant_id", "catalog_products.id"],
            ondelete="RESTRICT",
            name="fk_catalog_translations_tenant_product",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_catalog_translations_tenant_id"),
        UniqueConstraint("tenant_id", "product_id", "locale", name="uq_catalog_translation_product_locale"),
        UniqueConstraint("tenant_id", "locale", "slug", name="uq_catalog_translation_tenant_locale_slug"),
        Index("ix_catalog_translations_tenant_name", "tenant_id", "locale", "name", "product_id"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    locale: Mapped[str] = mapped_column(String(35), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    short_description: Mapped[str | None] = mapped_column(String(1000))
    long_description: Mapped[str | None] = mapped_column(Text)
    slug: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ProductSeoModel(Base):
    __tablename__ = "catalog_product_seo"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["catalog_products.tenant_id", "catalog_products.id"],
            ondelete="RESTRICT",
            name="fk_catalog_seo_tenant_product",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_catalog_seo_tenant_id"),
        UniqueConstraint("tenant_id", "product_id", "locale", name="uq_catalog_seo_product_locale"),
        Index("ix_catalog_seo_tenant_product", "tenant_id", "product_id", "locale"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    locale: Mapped[str] = mapped_column(String(35), nullable=False)
    title: Mapped[str | None] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(String(500))
    canonical_path: Mapped[str | None] = mapped_column(String(500))
    robots_index: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    robots_follow: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class TaxonomyModel(CatalogResourceMixin, Base):
    __tablename__ = "catalog_taxonomies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_catalog_taxonomies_tenant_id"),
        UniqueConstraint("tenant_id", "code", name="uq_catalog_taxonomies_tenant_code"),
        CheckConstraint("status IN ('active','archived')", name="ck_catalog_taxonomy_status"),
        CheckConstraint("version > 0", name="ck_catalog_taxonomy_version"),
        Index("ix_catalog_taxonomies_tenant_status_created", "tenant_id", "status", "created_at", "id"),
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")


class CategoryModel(CatalogResourceMixin, Base):
    __tablename__ = "catalog_categories"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "taxonomy_id"],
            ["catalog_taxonomies.tenant_id", "catalog_taxonomies.id"],
            ondelete="RESTRICT",
            name="fk_catalog_categories_tenant_taxonomy",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "taxonomy_id", "parent_id"],
            ["catalog_categories.tenant_id", "catalog_categories.taxonomy_id", "catalog_categories.id"],
            ondelete="RESTRICT",
            name="fk_catalog_categories_tenant_parent",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_catalog_categories_tenant_id"),
        UniqueConstraint("tenant_id", "taxonomy_id", "id", name="uq_catalog_categories_tenant_taxonomy_id"),
        UniqueConstraint("tenant_id", "taxonomy_id", "code", name="uq_catalog_categories_taxonomy_code"),
        UniqueConstraint("tenant_id", "taxonomy_id", "slug", name="uq_catalog_categories_taxonomy_slug"),
        CheckConstraint("status IN ('active','archived')", name="ck_catalog_category_status"),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="ck_catalog_category_not_own_parent"),
        CheckConstraint("position >= 0", name="ck_catalog_category_position"),
        CheckConstraint("version > 0", name="ck_catalog_category_version"),
        Index("ix_catalog_categories_tenant_parent", "tenant_id", "taxonomy_id", "parent_id", "position", "id"),
    )
    taxonomy_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    parent_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    code: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")


class CategoryClosureModel(Base):
    __tablename__ = "catalog_category_closure"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "taxonomy_id", "ancestor_id"],
            ["catalog_categories.tenant_id", "catalog_categories.taxonomy_id", "catalog_categories.id"],
            ondelete="RESTRICT",
            name="fk_catalog_closure_tenant_ancestor",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "taxonomy_id", "descendant_id"],
            ["catalog_categories.tenant_id", "catalog_categories.taxonomy_id", "catalog_categories.id"],
            ondelete="RESTRICT",
            name="fk_catalog_closure_tenant_descendant",
        ),
        CheckConstraint("depth >= 0", name="ck_catalog_category_closure_depth"),
        Index("ix_catalog_closure_descendant", "tenant_id", "taxonomy_id", "descendant_id", "depth", "ancestor_id"),
    )
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True)
    taxonomy_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    ancestor_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    descendant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ProductCategoryModel(Base):
    __tablename__ = "catalog_product_categories"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["catalog_products.tenant_id", "catalog_products.id"],
            ondelete="RESTRICT",
            name="fk_catalog_product_categories_tenant_product",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "taxonomy_id", "category_id"],
            ["catalog_categories.tenant_id", "catalog_categories.taxonomy_id", "catalog_categories.id"],
            ondelete="RESTRICT",
            name="fk_catalog_product_categories_tenant_category",
        ),
        CheckConstraint("position >= 0", name="ck_catalog_product_category_position"),
        Index(
            "uq_catalog_product_primary_category",
            "tenant_id",
            "product_id",
            "taxonomy_id",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
        Index("ix_catalog_product_categories_category", "tenant_id", "category_id", "product_id"),
    )
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True)
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    category_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    taxonomy_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ProductStoreModel(CatalogResourceMixin, Base):
    __tablename__ = "catalog_product_stores"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["catalog_products.tenant_id", "catalog_products.id"],
            ondelete="RESTRICT",
            name="fk_catalog_product_stores_tenant_product",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "store_id"],
            ["platform_stores.tenant_id", "platform_stores.id"],
            ondelete="RESTRICT",
            name="fk_catalog_product_stores_tenant_store",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_catalog_product_stores_tenant_id"),
        UniqueConstraint("tenant_id", "product_id", "store_id", name="uq_catalog_product_store_assignment"),
        CheckConstraint("status IN ('draft','active','suspended','archived')", name="ck_catalog_product_store_status"),
        CheckConstraint("version > 0", name="ck_catalog_product_store_version"),
        Index("ix_catalog_product_stores_store_status", "tenant_id", "store_id", "status", "product_id"),
        Index("ix_catalog_product_stores_product", "tenant_id", "product_id", "status", "store_id"),
    )
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    store_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class OptionModel(CatalogResourceMixin, Base):
    __tablename__ = "catalog_options"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_catalog_options_tenant_id"),
        UniqueConstraint("tenant_id", "code", name="uq_catalog_options_tenant_code"),
        CheckConstraint("status IN ('active','archived')", name="ck_catalog_option_status"),
        CheckConstraint("input_type IN ('select','swatch')", name="ck_catalog_option_input_type"),
        CheckConstraint("version > 0", name="ck_catalog_option_version"),
        Index("ix_catalog_options_tenant_status_position", "tenant_id", "status", "position", "id"),
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    input_type: Mapped[str] = mapped_column(String(20), nullable=False, default="select")
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")


class OptionTranslationModel(Base):
    __tablename__ = "catalog_option_translations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "option_id"],
            ["catalog_options.tenant_id", "catalog_options.id"],
            ondelete="RESTRICT",
            name="fk_catalog_option_translations_tenant_option",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_catalog_option_translations_tenant_id"),
        UniqueConstraint("tenant_id", "option_id", "locale", name="uq_catalog_option_translation_option_locale"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    option_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    locale: Mapped[str] = mapped_column(String(35), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class OptionValueModel(CatalogResourceMixin, Base):
    __tablename__ = "catalog_option_values"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "option_id"],
            ["catalog_options.tenant_id", "catalog_options.id"],
            ondelete="RESTRICT",
            name="fk_catalog_option_values_tenant_option",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_catalog_option_values_tenant_id"),
        UniqueConstraint("tenant_id", "option_id", "id", name="uq_catalog_option_values_tenant_option_id"),
        UniqueConstraint("tenant_id", "option_id", "code", name="uq_catalog_option_value_tenant_option_code"),
        CheckConstraint("status IN ('active','archived')", name="ck_catalog_option_value_status"),
        CheckConstraint(
            "swatch_hex IS NULL OR swatch_hex ~ '^#[0-9a-fA-F]{6}$'",
            name="ck_catalog_option_value_swatch_hex",
        ),
        CheckConstraint("version > 0", name="ck_catalog_option_value_version"),
        Index(
            "ix_catalog_option_values_tenant_option_status",
            "tenant_id",
            "option_id",
            "status",
            "position",
            "id",
        ),
    )
    option_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(String(200), nullable=False)
    swatch_hex: Mapped[str | None] = mapped_column(String(7))
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")


class OptionValueTranslationModel(Base):
    __tablename__ = "catalog_option_value_translations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "option_value_id"],
            ["catalog_option_values.tenant_id", "catalog_option_values.id"],
            ondelete="RESTRICT",
            name="fk_catalog_option_value_translations_tenant_value",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_catalog_option_value_translations_tenant_id"),
        UniqueConstraint(
            "tenant_id", "option_value_id", "locale", name="uq_catalog_option_value_translation_value_locale"
        ),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    option_value_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    locale: Mapped[str] = mapped_column(String(35), nullable=False)
    value: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ProductOptionModel(Base):
    __tablename__ = "catalog_product_options"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["catalog_products.tenant_id", "catalog_products.id"],
            ondelete="RESTRICT",
            name="fk_catalog_product_options_tenant_product",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "option_id"],
            ["catalog_options.tenant_id", "catalog_options.id"],
            ondelete="RESTRICT",
            name="fk_catalog_product_options_tenant_option",
        ),
        CheckConstraint("position >= 0", name="ck_catalog_product_option_position"),
        Index("ix_catalog_product_options_product", "tenant_id", "product_id", "position", "option_id"),
    )
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True)
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    option_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VariantOptionValueModel(Base):
    __tablename__ = "catalog_variant_option_values"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["catalog_product_variants.tenant_id", "catalog_product_variants.id"],
            ondelete="RESTRICT",
            name="fk_catalog_variant_option_values_tenant_variant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["catalog_products.tenant_id", "catalog_products.id"],
            ondelete="RESTRICT",
            name="fk_catalog_variant_option_values_tenant_product",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "product_id", "option_id"],
            ["catalog_product_options.tenant_id", "catalog_product_options.product_id", "catalog_product_options.option_id"],
            ondelete="RESTRICT",
            name="fk_catalog_variant_option_values_tenant_product_option",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "option_id", "option_value_id"],
            ["catalog_option_values.tenant_id", "catalog_option_values.option_id", "catalog_option_values.id"],
            ondelete="RESTRICT",
            name="fk_catalog_variant_option_values_tenant_value",
        ),
        UniqueConstraint(
            "tenant_id", "variant_id", "option_id", name="uq_catalog_variant_option_one_value_per_option"
        ),
        Index("ix_catalog_variant_option_values_value", "tenant_id", "option_value_id", "variant_id"),
    )
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True)
    variant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    option_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    option_value_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AttributeModel(CatalogResourceMixin, Base):
    __tablename__ = "catalog_attributes"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_catalog_attributes_tenant_id"),
        UniqueConstraint("tenant_id", "code", name="uq_catalog_attributes_tenant_code"),
        CheckConstraint("status IN ('active','archived')", name="ck_catalog_attribute_status"),
        CheckConstraint(
            "data_type IN ('TEXT','LONG_TEXT','INTEGER','DECIMAL','BOOLEAN','DATE','DATETIME','SELECT','MULTI_SELECT')",
            name="ck_catalog_attribute_data_type",
        ),
        CheckConstraint("version > 0", name="ck_catalog_attribute_version"),
        Index("ix_catalog_attributes_tenant_status_position", "tenant_id", "status", "position", "id"),
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000))
    data_type: Mapped[str] = mapped_column(String(20), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(50))
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_filterable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_searchable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_comparable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_visible_storefront: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")


class AttributeTranslationModel(Base):
    __tablename__ = "catalog_attribute_translations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "attribute_id"],
            ["catalog_attributes.tenant_id", "catalog_attributes.id"],
            ondelete="RESTRICT",
            name="fk_catalog_attribute_translations_tenant_attribute",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_catalog_attribute_translations_tenant_id"),
        UniqueConstraint(
            "tenant_id", "attribute_id", "locale", name="uq_catalog_attribute_translation_attribute_locale"
        ),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    attribute_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    locale: Mapped[str] = mapped_column(String(35), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class AttributeOptionModel(CatalogResourceMixin, Base):
    __tablename__ = "catalog_attribute_options"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "attribute_id"],
            ["catalog_attributes.tenant_id", "catalog_attributes.id"],
            ondelete="RESTRICT",
            name="fk_catalog_attribute_options_tenant_attribute",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_catalog_attribute_options_tenant_id"),
        UniqueConstraint(
            "tenant_id", "attribute_id", "id", name="uq_catalog_attribute_options_tenant_attribute_id"
        ),
        UniqueConstraint(
            "tenant_id", "attribute_id", "code", name="uq_catalog_attribute_option_tenant_attribute_code"
        ),
        CheckConstraint("status IN ('active','archived')", name="ck_catalog_attribute_option_status"),
        CheckConstraint("version > 0", name="ck_catalog_attribute_option_version"),
        Index(
            "ix_catalog_attribute_options_tenant_attribute_status",
            "tenant_id",
            "attribute_id",
            "status",
            "position",
            "id",
        ),
    )
    attribute_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")


class AttributeOptionTranslationModel(Base):
    __tablename__ = "catalog_attribute_option_translations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "attribute_option_id"],
            ["catalog_attribute_options.tenant_id", "catalog_attribute_options.id"],
            ondelete="RESTRICT",
            name="fk_catalog_attribute_option_translations_tenant_option",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_catalog_attribute_option_translations_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "attribute_option_id",
            "locale",
            name="uq_catalog_attribute_option_translation_option_locale",
        ),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    attribute_option_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    locale: Mapped[str] = mapped_column(String(35), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class AttributeGroupModel(CatalogResourceMixin, Base):
    __tablename__ = "catalog_attribute_groups"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_catalog_attribute_groups_tenant_id"),
        UniqueConstraint("tenant_id", "code", name="uq_catalog_attribute_groups_tenant_code"),
        CheckConstraint("status IN ('active','archived')", name="ck_catalog_attribute_group_status"),
        CheckConstraint("version > 0", name="ck_catalog_attribute_group_version"),
        Index("ix_catalog_attribute_groups_tenant_status_position", "tenant_id", "status", "position", "id"),
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000))
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")


class AttributeGroupTranslationModel(Base):
    __tablename__ = "catalog_attribute_group_translations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "group_id"],
            ["catalog_attribute_groups.tenant_id", "catalog_attribute_groups.id"],
            ondelete="RESTRICT",
            name="fk_catalog_attribute_group_translations_tenant_group",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_catalog_attribute_group_translations_tenant_id"),
        UniqueConstraint(
            "tenant_id", "group_id", "locale", name="uq_catalog_attribute_group_translation_group_locale"
        ),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    group_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    locale: Mapped[str] = mapped_column(String(35), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ProductTypeAttributeModel(Base):
    __tablename__ = "catalog_product_type_attributes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "product_type_id"],
            ["catalog_product_types.tenant_id", "catalog_product_types.id"],
            ondelete="RESTRICT",
            name="fk_catalog_product_type_attributes_tenant_product_type",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "attribute_id"],
            ["catalog_attributes.tenant_id", "catalog_attributes.id"],
            ondelete="RESTRICT",
            name="fk_catalog_product_type_attributes_tenant_attribute",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "group_id"],
            ["catalog_attribute_groups.tenant_id", "catalog_attribute_groups.id"],
            ondelete="RESTRICT",
            name="fk_catalog_product_type_attributes_tenant_group",
        ),
        CheckConstraint("position >= 0", name="ck_catalog_product_type_attribute_position"),
        Index(
            "ix_catalog_product_type_attributes_type",
            "tenant_id",
            "product_type_id",
            "position",
            "attribute_id",
        ),
    )
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True)
    product_type_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    attribute_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    group_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    visible_override: Mapped[bool | None] = mapped_column(Boolean)
    filterable_override: Mapped[bool | None] = mapped_column(Boolean)
    comparable_override: Mapped[bool | None] = mapped_column(Boolean)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProductAttributeValueModel(Base):
    __tablename__ = "catalog_product_attribute_values"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["catalog_products.tenant_id", "catalog_products.id"],
            ondelete="RESTRICT",
            name="fk_catalog_product_attribute_values_tenant_product",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "attribute_id"],
            ["catalog_attributes.tenant_id", "catalog_attributes.id"],
            ondelete="RESTRICT",
            name="fk_catalog_product_attribute_values_tenant_attribute",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "attribute_id", "value_option_id"],
            [
                "catalog_attribute_options.tenant_id",
                "catalog_attribute_options.attribute_id",
                "catalog_attribute_options.id",
            ],
            ondelete="RESTRICT",
            name="fk_catalog_product_attribute_values_tenant_option",
        ),
        Index(
            "ix_catalog_product_attribute_values_attribute",
            "tenant_id",
            "attribute_id",
            "product_id",
        ),
        CheckConstraint(
            "(CASE WHEN value_text IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN value_long_text IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN value_integer IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN value_decimal IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN value_boolean IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN value_date IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN value_datetime IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN value_option_id IS NOT NULL THEN 1 ELSE 0 END) <= 1",
            name="ck_catalog_product_attribute_value_single_column",
        ),
    )
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True)
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    attribute_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    value_text: Mapped[str | None] = mapped_column(String(500))
    value_long_text: Mapped[str | None] = mapped_column(Text)
    value_integer: Mapped[int | None] = mapped_column(BigInteger)
    value_decimal: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    value_boolean: Mapped[bool | None] = mapped_column(Boolean)
    value_date: Mapped[date | None] = mapped_column(Date)
    value_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    value_option_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    updated_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class ProductAttributeValueOptionModel(Base):
    __tablename__ = "catalog_product_attribute_value_options"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "product_id", "attribute_id"],
            [
                "catalog_product_attribute_values.tenant_id",
                "catalog_product_attribute_values.product_id",
                "catalog_product_attribute_values.attribute_id",
            ],
            ondelete="CASCADE",
            name="fk_catalog_product_attribute_value_options_tenant_value",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "attribute_id", "attribute_option_id"],
            [
                "catalog_attribute_options.tenant_id",
                "catalog_attribute_options.attribute_id",
                "catalog_attribute_options.id",
            ],
            ondelete="RESTRICT",
            name="fk_catalog_product_attribute_value_options_tenant_option",
        ),
        Index(
            "ix_catalog_product_attribute_value_options_option",
            "tenant_id",
            "attribute_option_id",
            "product_id",
        ),
    )
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True)
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    attribute_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    attribute_option_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


__all__ = [
    "AttributeGroupModel",
    "AttributeGroupTranslationModel",
    "AttributeModel",
    "AttributeOptionModel",
    "AttributeOptionTranslationModel",
    "AttributeTranslationModel",
    "BrandModel",
    "CategoryClosureModel",
    "CategoryModel",
    "OptionModel",
    "OptionTranslationModel",
    "OptionValueModel",
    "OptionValueTranslationModel",
    "ProductAttributeValueModel",
    "ProductAttributeValueOptionModel",
    "ProductCategoryModel",
    "ProductIdentifierModel",
    "ProductModel",
    "ProductOptionModel",
    "ProductSeoModel",
    "ProductStoreModel",
    "ProductTranslationModel",
    "ProductTypeAttributeModel",
    "ProductTypeModel",
    "ProductVariantModel",
    "TaxonomyModel",
    "VariantOptionValueModel",
]

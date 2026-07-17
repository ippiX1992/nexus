from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CatalogSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProductTypeCreate(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)


class ProductTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)


class ProductTypeResponse(CatalogSchema):
    id: UUID
    tenant_id: UUID
    code: str
    name: str
    description: str | None
    status: str
    version: int
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class ProductTypePage(BaseModel):
    items: list[ProductTypeResponse]
    next_cursor: str | None
    has_more: bool


class BrandCreate(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=160)


class BrandUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(default=None, min_length=1, max_length=160)


class BrandResponse(CatalogSchema):
    id: UUID
    tenant_id: UUID
    code: str
    name: str
    slug: str
    status: str
    version: int
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class BrandPage(BaseModel):
    items: list[BrandResponse]
    next_cursor: str | None
    has_more: bool


class ProductTranslationInput(BaseModel):
    locale: str = Field(min_length=2, max_length=35)
    name: str = Field(min_length=1, max_length=300)
    short_description: str | None = Field(default=None, max_length=1000)
    long_description: str | None = Field(default=None, max_length=100_000)
    slug: str = Field(min_length=1, max_length=200)


class ProductCreate(BaseModel):
    product_type_id: UUID
    brand_id: UUID | None = None
    code: str | None = Field(default=None, min_length=1, max_length=160)
    sku: str = Field(min_length=1, max_length=160)
    translation: ProductTranslationInput | None = None


class ProductUpdate(BaseModel):
    brand_id: UUID | None = None
    code: str | None = Field(default=None, min_length=1, max_length=160)


class ProductResponse(CatalogSchema):
    id: UUID
    tenant_id: UUID
    product_type_id: UUID
    brand_id: UUID | None
    code: str | None
    status: str
    version: int
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class ProductSummary(ProductResponse):
    name: str | None = None
    default_sku: str | None = None


class ProductPage(BaseModel):
    items: list[ProductSummary]
    next_cursor: str | None
    has_more: bool


class VariantCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=160)
    option_value_ids: list[UUID] | None = Field(default=None, max_length=20)


class VariantUpdate(BaseModel):
    sku: str | None = Field(default=None, min_length=1, max_length=160)


class VariantResponse(CatalogSchema):
    id: UUID
    tenant_id: UUID
    product_id: UUID
    sku: str
    is_default: bool
    status: str
    combination_fingerprint: str | None = None
    version: int
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class VariantPage(BaseModel):
    items: list[VariantResponse]
    next_cursor: str | None
    has_more: bool


class ProductTranslationPut(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    short_description: str | None = Field(default=None, max_length=1000)
    long_description: str | None = Field(default=None, max_length=100_000)
    slug: str = Field(min_length=1, max_length=200)


class ProductTranslationResponse(CatalogSchema):
    id: UUID
    product_id: UUID
    locale: str
    name: str
    short_description: str | None
    long_description: str | None
    slug: str
    created_at: datetime
    updated_at: datetime


class ProductSeoPut(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=500)
    canonical_path: str | None = Field(default=None, max_length=500)
    robots_index: bool = True
    robots_follow: bool = True


class ProductSeoResponse(CatalogSchema):
    id: UUID
    product_id: UUID
    locale: str
    title: str | None
    description: str | None
    canonical_path: str | None
    robots_index: bool
    robots_follow: bool
    created_at: datetime
    updated_at: datetime


class IdentifierCreate(BaseModel):
    identifier_type: Literal["ean", "upc", "isbn", "mpn", "external"]
    value: str = Field(min_length=1, max_length=255)
    source_system: str | None = Field(default=None, max_length=100)
    is_primary: bool = False


class IdentifierResponse(CatalogSchema):
    id: UUID
    tenant_id: UUID
    variant_id: UUID
    identifier_type: str
    value: str
    source_system: str | None
    is_primary: bool
    created_at: datetime
    archived_at: datetime | None


class TaxonomyCreate(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)


class TaxonomyResponse(CatalogSchema):
    id: UUID
    tenant_id: UUID
    code: str
    name: str
    status: str
    version: int
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class TaxonomyPage(BaseModel):
    items: list[TaxonomyResponse]
    next_cursor: str | None
    has_more: bool


class CategoryCreate(BaseModel):
    parent_id: UUID | None = None
    code: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=250)
    slug: str = Field(min_length=1, max_length=200)
    position: int = Field(default=0, ge=0, le=1_000_000)


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=250)
    slug: str | None = Field(default=None, min_length=1, max_length=200)
    position: int | None = Field(default=None, ge=0, le=1_000_000)


class CategoryMove(BaseModel):
    parent_id: UUID | None = None
    position: int = Field(default=0, ge=0, le=1_000_000)


class CategoryResponse(CatalogSchema):
    id: UUID
    tenant_id: UUID
    taxonomy_id: UUID
    parent_id: UUID | None
    code: str
    name: str
    slug: str
    position: int
    status: str
    version: int
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class ProductCategoryAssignment(BaseModel):
    category_id: UUID
    is_primary: bool = False
    position: int = Field(default=0, ge=0, le=1_000_000)


class ProductCategoriesPut(BaseModel):
    assignments: list[ProductCategoryAssignment] = Field(max_length=500)


class ProductCategoryResponse(CatalogSchema):
    product_id: UUID
    category_id: UUID
    taxonomy_id: UUID
    is_primary: bool
    position: int
    created_at: datetime
    updated_at: datetime


class ProductStorePut(BaseModel):
    status: Literal["draft", "active", "suspended"] = "draft"
    version: int | None = Field(default=None, ge=1)


class ProductStoreResponse(CatalogSchema):
    id: UUID
    product_id: UUID
    store_id: UUID
    status: str
    eligible: bool
    version: int
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class ProductDetail(BaseModel):
    product: ProductResponse
    variants: list[VariantResponse]
    translations: list[ProductTranslationResponse]
    seo: list[ProductSeoResponse]
    categories: list[ProductCategoryResponse]
    stores: list[ProductStoreResponse]


class CatalogUsageResponse(BaseModel):
    products: int
    product_limit: int


class OptionCreate(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    input_type: Literal["select", "swatch"] = "select"
    position: int = Field(default=0, ge=0, le=1_000_000)


class OptionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    input_type: Literal["select", "swatch"] | None = None
    position: int | None = Field(default=None, ge=0, le=1_000_000)


class OptionResponse(CatalogSchema):
    id: UUID
    tenant_id: UUID
    code: str
    name: str
    input_type: str
    position: int
    status: str
    version: int
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class OptionPage(BaseModel):
    items: list[OptionResponse]
    next_cursor: str | None
    has_more: bool


class OptionTranslationPut(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class OptionTranslationResponse(CatalogSchema):
    id: UUID
    option_id: UUID
    locale: str
    name: str
    created_at: datetime
    updated_at: datetime


class OptionValueCreate(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=200)
    swatch_hex: str | None = Field(default=None, min_length=7, max_length=7)
    position: int = Field(default=0, ge=0, le=1_000_000)


class OptionValueUpdate(BaseModel):
    value: str | None = Field(default=None, min_length=1, max_length=200)
    swatch_hex: str | None = Field(default=None, min_length=7, max_length=7)
    position: int | None = Field(default=None, ge=0, le=1_000_000)


class OptionValueResponse(CatalogSchema):
    id: UUID
    tenant_id: UUID
    option_id: UUID
    code: str
    value: str
    swatch_hex: str | None
    position: int
    status: str
    version: int
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class OptionValueTranslationPut(BaseModel):
    value: str = Field(min_length=1, max_length=200)


class OptionValueTranslationResponse(CatalogSchema):
    id: UUID
    option_value_id: UUID
    locale: str
    value: str
    created_at: datetime
    updated_at: datetime


class ProductOptionInput(BaseModel):
    option_id: UUID
    position: int = Field(default=0, ge=0, le=1_000_000)


class ProductOptionsPut(BaseModel):
    options: list[ProductOptionInput] = Field(max_length=50)


class ProductOptionResponse(CatalogSchema):
    tenant_id: UUID
    product_id: UUID
    option_id: UUID
    required: bool
    position: int
    version: int
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class VariantOptionValueResponse(CatalogSchema):
    tenant_id: UUID
    variant_id: UUID
    product_id: UUID
    option_id: UUID
    option_value_id: UUID


class VariantGenerationPreviewResponse(BaseModel):
    options_considered: list[dict[str, Any]]
    theoretical_total: int
    existing_combinations: int
    new_combinations: int
    duplicate_combinations: int
    tenant_limit: int
    remaining_capacity: int
    warnings: list[str]
    estimated_work: int


class VariantGenerationAccepted(BaseModel):
    operation_id: UUID
    status: str


AttributeDataType = Literal[
    "TEXT", "LONG_TEXT", "INTEGER", "DECIMAL", "BOOLEAN", "DATE", "DATETIME", "SELECT", "MULTI_SELECT"
]


class AttributeCreate(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    data_type: AttributeDataType
    unit: str | None = Field(default=None, max_length=50)
    is_required: bool = False
    is_filterable: bool = False
    is_searchable: bool = False
    is_comparable: bool = False
    is_visible_storefront: bool = True
    position: int = Field(default=0, ge=0, le=1_000_000)


class AttributeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    data_type: AttributeDataType | None = None
    unit: str | None = Field(default=None, max_length=50)
    is_required: bool | None = None
    is_filterable: bool | None = None
    is_searchable: bool | None = None
    is_comparable: bool | None = None
    is_visible_storefront: bool | None = None
    position: int | None = Field(default=None, ge=0, le=1_000_000)


class AttributeResponse(CatalogSchema):
    id: UUID
    tenant_id: UUID
    code: str
    name: str
    description: str | None
    data_type: str
    unit: str | None
    is_required: bool
    is_filterable: bool
    is_searchable: bool
    is_comparable: bool
    is_visible_storefront: bool
    position: int
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class AttributePage(BaseModel):
    items: list[AttributeResponse]
    next_cursor: str | None
    has_more: bool


class AttributeTranslationPut(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class AttributeTranslationResponse(CatalogSchema):
    id: UUID
    attribute_id: UUID
    locale: str
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class AttributeOptionCreate(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=200)
    position: int = Field(default=0, ge=0, le=1_000_000)


class AttributeOptionUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    position: int | None = Field(default=None, ge=0, le=1_000_000)


class AttributeOptionResponse(CatalogSchema):
    id: UUID
    tenant_id: UUID
    attribute_id: UUID
    code: str
    label: str
    position: int
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class AttributeOptionTranslationPut(BaseModel):
    label: str = Field(min_length=1, max_length=200)


class AttributeOptionTranslationResponse(CatalogSchema):
    id: UUID
    attribute_option_id: UUID
    locale: str
    label: str
    created_at: datetime
    updated_at: datetime


class AttributeGroupCreate(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    position: int = Field(default=0, ge=0, le=1_000_000)


class AttributeGroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    position: int | None = Field(default=None, ge=0, le=1_000_000)


class AttributeGroupResponse(CatalogSchema):
    id: UUID
    tenant_id: UUID
    code: str
    name: str
    description: str | None
    position: int
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class AttributeGroupPage(BaseModel):
    items: list[AttributeGroupResponse]
    next_cursor: str | None
    has_more: bool


class AttributeGroupTranslationPut(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class AttributeGroupTranslationResponse(CatalogSchema):
    id: UUID
    group_id: UUID
    locale: str
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class ProductTypeAttributeInput(BaseModel):
    attribute_id: UUID
    group_id: UUID | None = None
    position: int = Field(default=0, ge=0, le=1_000_000)
    required: bool = False
    visible_override: bool | None = None
    filterable_override: bool | None = None
    comparable_override: bool | None = None


class ProductTypeAttributesPut(BaseModel):
    attributes: list[ProductTypeAttributeInput] = Field(max_length=100)


class ProductTypeAttributeResponse(CatalogSchema):
    tenant_id: UUID
    product_type_id: UUID
    attribute_id: UUID
    group_id: UUID | None
    position: int
    required: bool
    visible_override: bool | None
    filterable_override: bool | None
    comparable_override: bool | None
    version: int
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class ProductAttributeValueInput(BaseModel):
    attribute_id: UUID
    value: Any


class ProductAttributeValuesPut(BaseModel):
    values: list[ProductAttributeValueInput] = Field(max_length=200)


class ProductAttributeValueOptionResponse(CatalogSchema):
    tenant_id: UUID
    product_id: UUID
    attribute_id: UUID
    attribute_option_id: UUID


class ProductAttributeValueResponse(CatalogSchema):
    tenant_id: UUID
    product_id: UUID
    attribute_id: UUID
    value_text: str | None
    value_long_text: str | None
    value_integer: int | None
    value_decimal: Decimal | None
    value_boolean: bool | None
    value_date: date | None
    value_datetime: datetime | None
    value_option_id: UUID | None
    version: int
    created_at: datetime
    updated_at: datetime

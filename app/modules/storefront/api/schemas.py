from decimal import Decimal

from pydantic import BaseModel


class StorefrontMeta(BaseModel):
    key: str
    name: str
    currency: str
    locale: str
    brand: str | None = None
    product_count: int


class StorefrontProduct(BaseModel):
    slug: str
    name: str
    short_description: str | None = None
    brand: str | None = None
    sku: str
    price: Decimal | None = None
    compare_at: Decimal | None = None
    currency: str
    available: int
    in_stock: bool


class StorefrontProductDetail(StorefrontProduct):
    long_description: str | None = None


class StorefrontProductList(BaseModel):
    items: list[StorefrontProduct]
    total: int

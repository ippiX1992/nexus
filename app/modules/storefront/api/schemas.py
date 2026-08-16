from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


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
    image: str | None = None
    sku: str
    price: Decimal | None = None
    compare_at: Decimal | None = None
    currency: str
    available: int
    in_stock: bool


class StorefrontProductDetail(StorefrontProduct):
    long_description: str | None = None
    images: list[str] = []


class StorefrontProductList(BaseModel):
    items: list[StorefrontProduct]
    total: int


class StorefrontCategory(BaseModel):
    slug: str
    name: str
    product_count: int
    children: list["StorefrontCategory"] = []


StorefrontCategory.model_rebuild()


class StockStatus(BaseModel):
    slug: str
    available: int
    in_stock: bool


class OrderItemInput(BaseModel):
    slug: str
    quantity: int = Field(default=1, ge=1, le=99)


class OrderCreate(BaseModel):
    customer_name: str = Field(min_length=2, max_length=160)
    customer_email: str | None = Field(default=None, max_length=255)
    customer_phone: str | None = Field(default=None, max_length=40)
    shipping_address: str | None = Field(default=None, max_length=500)
    items: list[OrderItemInput] = Field(min_length=1)


class OrderLine(BaseModel):
    sku: str
    name: str
    unit_amount: Decimal | None = None
    quantity: int
    line_total: Decimal


class OrderResponse(BaseModel):
    order_number: str
    tracking_number: str
    status: str
    currency: str
    subtotal: Decimal
    item_count: int
    customer_name: str
    placed_at: datetime
    items: list[OrderLine] = []


class TrackingStage(BaseModel):
    status: str
    label: str
    at: datetime
    done: bool


class TrackingResponse(BaseModel):
    order_number: str
    tracking_number: str
    status: str
    estimated_delivery: datetime
    stages: list[TrackingStage]

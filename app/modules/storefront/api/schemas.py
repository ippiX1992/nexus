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
    image2: str | None = None
    sku: str
    price: Decimal | None = None
    compare_at: Decimal | None = None
    currency: str
    available: int
    in_stock: bool


class SpecItem(BaseModel):
    label: str
    value: str


class StorefrontProductDetail(StorefrontProduct):
    long_description: str | None = None
    images: list[str] = []
    videos: list[str] = []
    specs: list[SpecItem] = []
    category_slug: str | None = None


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
    shipping_province: str | None = Field(default=None, max_length=80)
    shipping_city: str | None = Field(default=None, max_length=80)
    shipping_method: str = Field(default="standard")
    coupon_code: str | None = Field(default=None, max_length=40)
    items: list[OrderItemInput] = Field(min_length=1)


class CouponInfo(BaseModel):
    code: str
    valid: bool
    label: str | None = None
    discount_type: str | None = None
    value: float | None = None


class ReviewInput(BaseModel):
    author: str = Field(min_length=2, max_length=120)
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)


class Review(BaseModel):
    author: str
    rating: int
    comment: str | None = None
    created_at: datetime


class ReviewSummary(BaseModel):
    average: float
    count: int
    items: list[Review] = []


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
    shipping_method: str = "standard"
    shipping_amount: Decimal = Decimal("0")
    shipping_province: str | None = None
    shipping_city: str | None = None
    coupon_code: str | None = None
    discount_amount: Decimal = Decimal("0")
    total: Decimal = Decimal("0")
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

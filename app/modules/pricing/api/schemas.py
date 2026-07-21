from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

ScopeType = Literal["store", "channel", "market"]


class PricingSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Price Lists ---


class PriceListCreate(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    currency_code: str = Field(min_length=3, max_length=3)
    is_default: bool = False
    notes: str | None = Field(default=None, max_length=2000)


class PriceListUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    is_default: bool | None = None


class PriceListResponse(PricingSchema):
    id: UUID
    tenant_id: UUID
    code: str
    name: str
    currency_code: str
    is_default: bool
    notes: str | None
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class PriceListPage(BaseModel):
    items: list[PriceListResponse]
    next_cursor: str | None
    has_more: bool


# --- Price List Entries ---


class PriceListEntrySet(BaseModel):
    unit_amount: Decimal = Field(ge=0)
    compare_at_amount: Decimal | None = Field(default=None, ge=0)
    msrp_amount: Decimal | None = Field(default=None, ge=0)
    cost_amount: Decimal | None = Field(default=None, ge=0)
    reason: str | None = Field(default=None, max_length=500)


class PriceListEntryResponse(PricingSchema):
    id: UUID
    tenant_id: UUID
    price_list_id: UUID
    variant_id: UUID
    unit_amount: Decimal
    compare_at_amount: Decimal | None
    msrp_amount: Decimal | None
    cost_amount: Decimal | None
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class PriceListEntryPage(BaseModel):
    items: list[PriceListEntryResponse]
    next_cursor: str | None
    has_more: bool


# --- Assignments ---


class AssignmentCreate(BaseModel):
    price_list_id: UUID
    scope_type: ScopeType
    store_id: UUID | None = None
    channel_id: UUID | None = None
    market_id: UUID | None = None
    priority: int = Field(default=0, ge=0, le=1_000_000)
    effective_from: datetime | None = None
    effective_until: datetime | None = None

    @model_validator(mode="after")
    def _validate_scope(self) -> "AssignmentCreate":
        columns = {"store": self.store_id, "channel": self.channel_id, "market": self.market_id}
        for name, value in columns.items():
            if name == self.scope_type and value is None:
                raise ValueError(f"scope_type '{self.scope_type}' requires {name}_id")
            if name != self.scope_type and value is not None:
                raise ValueError(f"{name}_id must be omitted when scope_type is '{self.scope_type}'")
        return self


class AssignmentResponse(PricingSchema):
    id: UUID
    tenant_id: UUID
    price_list_id: UUID
    scope_type: str
    store_id: UUID | None
    channel_id: UUID | None
    market_id: UUID | None
    priority: int
    effective_from: datetime | None
    effective_until: datetime | None
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class AssignmentPage(BaseModel):
    items: list[AssignmentResponse]
    next_cursor: str | None
    has_more: bool


# --- Variant Price Overrides ---


class OverrideCreate(BaseModel):
    variant_id: UUID
    scope_type: ScopeType
    store_id: UUID | None = None
    channel_id: UUID | None = None
    market_id: UUID | None = None
    unit_amount: Decimal = Field(ge=0)
    compare_at_amount: Decimal | None = Field(default=None, ge=0)
    currency_code: str = Field(min_length=3, max_length=3)
    priority: int = Field(default=0, ge=0, le=1_000_000)
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _validate_scope(self) -> "OverrideCreate":
        columns = {"store": self.store_id, "channel": self.channel_id, "market": self.market_id}
        for name, value in columns.items():
            if name == self.scope_type and value is None:
                raise ValueError(f"scope_type '{self.scope_type}' requires {name}_id")
            if name != self.scope_type and value is not None:
                raise ValueError(f"{name}_id must be omitted when scope_type is '{self.scope_type}'")
        return self


class OverrideResponse(PricingSchema):
    id: UUID
    tenant_id: UUID
    variant_id: UUID
    scope_type: str
    store_id: UUID | None
    channel_id: UUID | None
    market_id: UUID | None
    unit_amount: Decimal
    compare_at_amount: Decimal | None
    currency_code: str
    priority: int
    effective_from: datetime | None
    effective_until: datetime | None
    reason: str | None
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class OverridePage(BaseModel):
    items: list[OverrideResponse]
    next_cursor: str | None
    has_more: bool


# --- Resolution ---


class ResolvedPriceResponse(PricingSchema):
    source: str
    source_id: UUID
    variant_id: UUID
    unit_amount: Decimal
    compare_at_amount: Decimal | None
    msrp_amount: Decimal | None
    cost_amount: Decimal | None
    currency_code: str
    price_list_id: UUID | None


# --- History ---


class PriceHistoryResponse(PricingSchema):
    id: UUID
    tenant_id: UUID
    entity_type: str
    entity_id: UUID
    variant_id: UUID
    field_name: str
    previous_amount: Decimal | None
    new_amount: Decimal | None
    currency_code: str
    changed_by: UUID | None
    changed_at: datetime
    reason: str | None


class PriceHistoryPage(BaseModel):
    items: list[PriceHistoryResponse]
    next_cursor: str | None
    has_more: bool

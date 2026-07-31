from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

ScopeType = Literal["store", "channel", "market"]
LocationType = Literal["storage", "picking", "staging", "returns", "quarantine"]


class InventorySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Warehouses ---


class WarehouseCreate(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)


class WarehouseResponse(InventorySchema):
    id: UUID
    tenant_id: UUID
    code: str
    name: str
    country_code: str | None
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class WarehousePage(BaseModel):
    items: list[WarehouseResponse]
    next_cursor: str | None
    has_more: bool


# --- Locations ---


class LocationCreate(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    location_type: LocationType = "storage"


class LocationResponse(InventorySchema):
    id: UUID
    tenant_id: UUID
    warehouse_id: UUID
    code: str
    name: str
    location_type: str
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class LocationPage(BaseModel):
    items: list[LocationResponse]
    next_cursor: str | None
    has_more: bool


# --- Stock ---


class StockAdjust(BaseModel):
    delta: int = Field(description="Signed whole-unit change; must be non-zero")
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _non_zero(self) -> "StockAdjust":
        if self.delta == 0:
            raise ValueError("delta must be non-zero")
        return self


class StockReceive(BaseModel):
    quantity: int = Field(gt=0)
    reason: str | None = Field(default=None, max_length=500)


class StockRecount(BaseModel):
    counted: int = Field(ge=0)
    reason: str | None = Field(default=None, max_length=500)


class StockLevelResponse(InventorySchema):
    id: UUID
    tenant_id: UUID
    location_id: UUID
    variant_id: UUID
    on_hand: int
    reserved: int
    incoming: int
    available: int
    version: int
    created_at: datetime
    updated_at: datetime


class StockLevelPage(BaseModel):
    items: list[StockLevelResponse]
    next_cursor: str | None
    has_more: bool


# --- Ledger ---


class LedgerEntryResponse(InventorySchema):
    id: UUID
    tenant_id: UUID
    location_id: UUID
    variant_id: UUID
    entry_type: str
    quantity_delta: int
    on_hand_after: int
    reason: str | None
    reference_type: str | None
    reference_id: UUID | None
    created_by: UUID | None
    created_at: datetime


class LedgerPage(BaseModel):
    items: list[LedgerEntryResponse]
    next_cursor: str | None
    has_more: bool


# --- Transfers ---


class TransferCreate(BaseModel):
    from_location_id: UUID
    to_location_id: UUID
    variant_id: UUID
    quantity: int = Field(gt=0)
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _distinct_locations(self) -> "TransferCreate":
        if self.from_location_id == self.to_location_id:
            raise ValueError("from_location_id and to_location_id must differ")
        return self


class TransferResponse(InventorySchema):
    id: UUID
    tenant_id: UUID
    from_location_id: UUID
    to_location_id: UUID
    variant_id: UUID
    quantity: int
    reason: str | None
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class TransferPage(BaseModel):
    items: list[TransferResponse]
    next_cursor: str | None
    has_more: bool


# --- Reservations ---


class ReservationCreate(BaseModel):
    variant_id: UUID
    quantity: int = Field(gt=0)
    scope_type: ScopeType
    scope_id: UUID
    reference_type: str | None = Field(default=None, max_length=50)
    reference_id: UUID | None = None
    expires_at: datetime | None = None


class ReservationResponse(InventorySchema):
    id: UUID
    tenant_id: UUID
    variant_id: UUID
    location_id: UUID
    quantity: int
    scope_type: str | None
    store_id: UUID | None
    channel_id: UUID | None
    market_id: UUID | None
    reference_type: str | None
    reference_id: UUID | None
    expires_at: datetime | None
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class ReservationPage(BaseModel):
    items: list[ReservationResponse]
    next_cursor: str | None
    has_more: bool


class ReservationBatchResponse(BaseModel):
    """A reservation request can fan out across several locations (the
    allocation engine may split it), so the create endpoint returns the whole
    batch under a stable envelope -- which also keeps the idempotent replay
    body consistent with the live response shape."""

    items: list[ReservationResponse]


# --- Fulfillment scopes ---


class FulfillmentScopeCreate(BaseModel):
    warehouse_id: UUID
    scope_type: ScopeType
    store_id: UUID | None = None
    channel_id: UUID | None = None
    market_id: UUID | None = None
    priority: int = Field(default=0, ge=0, le=1_000_000)

    @model_validator(mode="after")
    def _validate_scope(self) -> "FulfillmentScopeCreate":
        columns = {"store": self.store_id, "channel": self.channel_id, "market": self.market_id}
        for name, value in columns.items():
            if name == self.scope_type and value is None:
                raise ValueError(f"scope_type '{self.scope_type}' requires {name}_id")
            if name != self.scope_type and value is not None:
                raise ValueError(f"{name}_id must be omitted when scope_type is '{self.scope_type}'")
        return self


class FulfillmentScopeResponse(InventorySchema):
    id: UUID
    tenant_id: UUID
    warehouse_id: UUID
    scope_type: str
    store_id: UUID | None
    channel_id: UUID | None
    market_id: UUID | None
    priority: int
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class FulfillmentScopePage(BaseModel):
    items: list[FulfillmentScopeResponse]
    next_cursor: str | None
    has_more: bool


# --- Allocation ---


class AllocationLine(BaseModel):
    location_id: UUID
    warehouse_id: UUID
    quantity: int


class AllocationPlanResponse(BaseModel):
    requested: int
    allocated: int
    shortfall: int
    fully_allocated: bool
    allocations: list[AllocationLine]

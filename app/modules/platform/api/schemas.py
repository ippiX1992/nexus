from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PlatformSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class StoreCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=2, max_length=160)
    slug: str = Field(min_length=1, max_length=100)
    default_locale: str = Field(min_length=2, max_length=35)
    default_currency: str = Field(min_length=3, max_length=3)
    timezone: str = Field(min_length=1, max_length=64)


class StoreUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    slug: str | None = Field(default=None, min_length=1, max_length=100)
    default_locale: str | None = None
    default_currency: str | None = None
    timezone: str | None = None


class StoreResponse(PlatformSchema):
    id: UUID
    tenant_id: UUID
    code: str
    name: str
    slug: str
    status: str
    default_locale: str
    default_currency: str
    timezone: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class SiteCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=2, max_length=160)
    slug: str = Field(min_length=1, max_length=100)
    site_type: Literal["commerce", "content", "landing", "portal"]
    primary_domain_placeholder: str | None = Field(default=None, max_length=253)


class SiteUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    slug: str | None = Field(default=None, min_length=1, max_length=100)
    primary_domain_placeholder: str | None = Field(default=None, max_length=253)


class SiteResponse(PlatformSchema):
    id: UUID
    tenant_id: UUID
    store_id: UUID
    code: str
    name: str
    slug: str
    site_type: str
    status: str
    primary_domain_placeholder: str | None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class ChannelCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=2, max_length=160)
    channel_type: Literal["web", "mobile", "marketplace", "b2b", "social", "pos", "api"]


class ChannelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)


class ChannelResponse(PlatformSchema):
    id: UUID
    tenant_id: UUID
    store_id: UUID
    code: str
    name: str
    channel_type: str
    status: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class EnvironmentCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=2, max_length=160)
    environment_type: Literal["development", "preview", "staging", "production"]


class EnvironmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)


class EnvironmentResponse(PlatformSchema):
    id: UUID
    tenant_id: UUID
    store_id: UUID
    code: str
    name: str
    environment_type: str
    is_production: bool
    status: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class MarketCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=2, max_length=160)
    country_code: str = Field(min_length=2, max_length=2)
    currency_code: str = Field(min_length=3, max_length=3)
    default_locale: str = Field(min_length=2, max_length=35)
    timezone: str = Field(min_length=1, max_length=64)


class MarketUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    default_locale: str | None = None
    timezone: str | None = None


class MarketResponse(PlatformSchema):
    id: UUID
    tenant_id: UUID
    store_id: UUID
    code: str
    name: str
    country_code: str
    currency_code: str
    default_locale: str
    timezone: str
    status: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class OperationResponse(PlatformSchema):
    id: UUID
    operation_type: str
    status: str
    progress: int
    message: str | None
    result: dict | None
    error: str | None
    correlation_id: UUID
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class EntitlementResponse(BaseModel):
    key: str
    value: int
    source: Literal["default", "override"]


class EntitlementOverrideRequest(BaseModel):
    value: int = Field(ge=0, le=1_000_000)


class UsageResponse(BaseModel):
    stores: int
    sites: int
    channels: int
    environments: int
    markets: int
    users: int

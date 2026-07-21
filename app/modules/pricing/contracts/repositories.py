from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from app.modules.platform.contracts.events import EventEnvelope


class PricingRepository(Protocol):
    # --- Price Lists ---
    async def get_price_list(self, tenant_id: UUID, resource_id: UUID, *, lock: bool = False) -> Any | None: ...
    async def get_price_list_by_code(self, tenant_id: UUID, code: str) -> Any | None: ...
    async def get_default_price_list(self, tenant_id: UUID) -> Any | None: ...
    async def list_price_lists(
        self, tenant_id: UUID, *, limit: int, cursor: tuple[datetime, UUID] | None, status: str | None = None
    ) -> tuple[list[Any], bool]: ...
    async def create_price_list(self, tenant_id: UUID, actor_id: UUID, data: dict[str, Any]) -> Any: ...

    # --- Price List Entries ---
    async def get_price_list_entry(self, tenant_id: UUID, resource_id: UUID, *, lock: bool = False) -> Any | None: ...
    async def get_price_list_entry_by_variant(
        self, tenant_id: UUID, price_list_id: UUID, variant_id: UUID, *, lock: bool = False
    ) -> Any | None: ...
    async def list_price_list_entries(
        self, tenant_id: UUID, price_list_id: UUID, *, limit: int, cursor: tuple[datetime, UUID] | None
    ) -> tuple[list[Any], bool]: ...
    async def list_entries_for_variant_in_lists(
        self, tenant_id: UUID, variant_id: UUID, price_list_ids: list[UUID]
    ) -> list[Any]: ...
    async def upsert_price_list_entry(
        self, tenant_id: UUID, actor_id: UUID, price_list_id: UUID, variant_id: UUID, data: dict[str, Any]
    ) -> tuple[Any, Any | None]: ...

    # --- Assignments ---
    async def get_assignment(self, tenant_id: UUID, resource_id: UUID, *, lock: bool = False) -> Any | None: ...
    async def list_assignments(
        self,
        tenant_id: UUID,
        *,
        limit: int,
        cursor: tuple[datetime, UUID] | None,
        price_list_id: UUID | None = None,
        status: str | None = None,
    ) -> tuple[list[Any], bool]: ...
    async def list_active_assignments_for_scope(
        self, tenant_id: UUID, scope_type: str, scope_id: UUID
    ) -> list[Any]: ...
    async def create_assignment(self, tenant_id: UUID, actor_id: UUID, data: dict[str, Any]) -> Any: ...

    # --- Variant Price Overrides ---
    async def get_override(self, tenant_id: UUID, resource_id: UUID, *, lock: bool = False) -> Any | None: ...
    async def list_overrides(
        self,
        tenant_id: UUID,
        *,
        limit: int,
        cursor: tuple[datetime, UUID] | None,
        variant_id: UUID | None = None,
        status: str | None = None,
    ) -> tuple[list[Any], bool]: ...
    async def list_active_overrides_for_variant_scope(
        self, tenant_id: UUID, variant_id: UUID, scope_type: str, scope_id: UUID
    ) -> list[Any]: ...
    async def create_override(self, tenant_id: UUID, actor_id: UUID, data: dict[str, Any]) -> Any: ...

    # --- History ---
    async def add_history_entry(self, tenant_id: UUID, data: dict[str, Any]) -> Any: ...
    async def list_history(
        self,
        tenant_id: UUID,
        *,
        limit: int,
        cursor: tuple[datetime, UUID] | None,
        variant_id: UUID | None = None,
        price_list_id: UUID | None = None,
    ) -> tuple[list[Any], bool]: ...

    # --- Catalog cross-references (read-only, composite-FK backed) ---
    async def variant_exists(self, tenant_id: UUID, variant_id: UUID) -> bool: ...

    # --- Outbox / persistence ---
    async def add_event(self, envelope: EventEnvelope) -> None: ...
    async def flush(self) -> None: ...

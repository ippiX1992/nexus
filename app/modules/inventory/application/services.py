from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, NoReturn
from uuid import UUID

from app.application.auth import audit
from app.modules.inventory.contracts.repositories import InventoryRepository
from app.modules.inventory.domain.policies import (
    InsufficientStock,
    InventoryConflict,
    InventoryNotFound,
    InventoryVersionConflict,
    ensure_adjustment_keeps_on_hand_nonnegative,
    ensure_can_reserve,
    ensure_can_ship_transfer,
    ensure_expected_version,
    ensure_positive_quantity,
    ensure_recount_nonnegative,
    ensure_reference_active,
    ensure_reservation_not_expired,
    ensure_reservation_releasable,
    ensure_scope_reference,
    ensure_transfer_completable,
)
from app.modules.inventory.domain.values import (
    AllocationPlan,
    LocationCandidate,
    allocate,
    normalized_code,
)
from app.modules.platform.contracts.events import EventActor, EventEnvelope


@dataclass(frozen=True, slots=True)
class InventoryActor:
    # user_id is None for system-driven writes with no authenticated user
    # (e.g. a public storefront checkout or the expiry sweeper); created_by /
    # audit actor_id / event actor all accept a null user.
    user_id: UUID | None
    session_id: UUID | None
    tenant_id: UUID
    correlation_id: UUID


class InventoryService:
    def __init__(self, repository: InventoryRepository, actor: InventoryActor, audit_session: Any) -> None:
        self.repository = repository
        self.actor = actor
        self.audit_session = audit_session

    def _event(
        self, event_type: str, aggregate_type: str, aggregate_id: UUID, version: int, data: dict[str, Any]
    ) -> EventEnvelope:
        return EventEnvelope.create(
            event_type=event_type,
            tenant_id=self.actor.tenant_id,
            store_id=None,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            correlation_id=self.actor.correlation_id,
            actor=EventActor(self.actor.user_id, self.actor.session_id),
            data={"aggregate_version": version, **data},
        )

    async def _audit(self, action: str, result: str, resource: UUID | str | None, metadata: dict[str, Any] | None = None) -> None:
        await audit(
            self.audit_session,
            action,
            result,
            self.actor.user_id,
            self.actor.tenant_id,
            resource=str(resource) if resource else None,
            metadata={**(metadata or {}), "correlation_id": str(self.actor.correlation_id)},
        )

    async def _missing(self, kind: str, resource_id: UUID) -> NoReturn:
        await self._audit("inventory.scope_denied", "denied", resource_id, {"kind": kind})
        raise InventoryNotFound(f"{kind.replace('_', ' ').title()} not found")

    async def _version(self, kind: str, resource: Any, expected: int) -> None:
        try:
            ensure_expected_version(resource.version, expected)
        except InventoryVersionConflict:
            await self._audit(
                "inventory.version_conflict", "denied", resource.id,
                {"kind": kind, "expected": expected, "current": resource.version},
            )
            raise

    async def _ledger(
        self,
        location_id: UUID,
        variant_id: UUID,
        entry_type: str,
        quantity_delta: int,
        on_hand_after: int,
        *,
        reason: str | None = None,
        reference_type: str | None = None,
        reference_id: UUID | None = None,
    ) -> None:
        await self.repository.add_ledger_entry(
            self.actor.tenant_id,
            {
                "location_id": location_id,
                "variant_id": variant_id,
                "entry_type": entry_type,
                "quantity_delta": quantity_delta,
                "on_hand_after": on_hand_after,
                "reason": reason,
                "reference_type": reference_type,
                "reference_id": reference_id,
                "created_by": self.actor.user_id,
            },
        )

    # --- Warehouses ---

    async def create_warehouse(self, data: dict[str, Any]) -> Any:
        row = await self.repository.create_warehouse(
            self.actor.tenant_id,
            self.actor.user_id,
            {
                "code": normalized_code(data["code"]),
                "name": data["name"].strip(),
                "country_code": (data.get("country_code") or None),
                "status": "active",
            },
        )
        await self.repository.flush()
        await self.repository.add_event(
            self._event("inventory.warehouse.created.v1", "inventory.warehouse", row.id, row.version, {"code": row.code})
        )
        await self._audit("inventory.warehouse_created", "success", row.id)
        return row

    async def archive_warehouse(self, resource_id: UUID, expected: int) -> Any:
        row = await self.repository.get_warehouse(self.actor.tenant_id, resource_id, lock=True)
        if row is None:
            await self._missing("warehouse", resource_id)
        await self._version("warehouse", row, expected)
        row.status = "archived"
        row.archived_at = datetime.now(UTC)
        row.updated_by = self.actor.user_id
        row.version += 1
        await self.repository.add_event(
            self._event("inventory.warehouse.archived.v1", "inventory.warehouse", row.id, row.version, {})
        )
        await self._audit("inventory.warehouse_archived", "success", row.id)
        return row

    # --- Locations ---

    async def create_location(self, warehouse_id: UUID, data: dict[str, Any]) -> Any:
        warehouse = await self.repository.get_warehouse(self.actor.tenant_id, warehouse_id)
        if warehouse is None:
            await self._missing("warehouse", warehouse_id)
        ensure_reference_active(warehouse.status, "Warehouse")
        row = await self.repository.create_location(
            self.actor.tenant_id,
            self.actor.user_id,
            {
                "warehouse_id": warehouse_id,
                "code": normalized_code(data["code"]),
                "name": data["name"].strip(),
                "location_type": data.get("location_type", "storage"),
                "status": "active",
            },
        )
        await self.repository.flush()
        await self.repository.add_event(
            self._event("inventory.location.created.v1", "inventory.location", row.id, row.version,
                        {"warehouse_id": str(warehouse_id), "code": row.code})
        )
        await self._audit("inventory.location_created", "success", row.id)
        return row

    # --- Stock movements ---

    async def adjust_stock(self, location_id: UUID, variant_id: UUID, delta: int, reason: str | None) -> Any:
        if not isinstance(delta, int) or isinstance(delta, bool) or delta == 0:
            raise InventoryConflict("Adjustment delta must be a non-zero whole number")
        location = await self.repository.get_location(self.actor.tenant_id, location_id)
        if location is None:
            await self._missing("location", location_id)
        ensure_reference_active(location.status, "Location")
        if not await self.repository.variant_exists(self.actor.tenant_id, variant_id):
            await self._missing("variant", variant_id)

        level = await self.repository.get_or_create_stock_level(
            self.actor.tenant_id, self.actor.user_id, location_id, variant_id
        )
        try:
            ensure_adjustment_keeps_on_hand_nonnegative(level.on_hand, delta)
        except InsufficientStock:
            await self._audit("inventory.stock_insufficient", "denied", level.id,
                              {"location_id": str(location_id), "variant_id": str(variant_id), "delta": delta})
            raise
        if delta < 0 and level.reserved > level.on_hand + delta:
            raise InsufficientStock("Adjustment would leave fewer units than are currently reserved")
        level.on_hand += delta
        level.updated_by = self.actor.user_id
        level.version += 1
        await self._ledger(location_id, variant_id, "adjustment", delta, level.on_hand, reason=reason)
        await self.repository.flush()
        await self.repository.add_event(
            self._event("inventory.stock.adjusted.v1", "inventory.stock_level", level.id, level.version,
                        {"location_id": str(location_id), "variant_id": str(variant_id), "delta": delta,
                         "on_hand": level.on_hand})
        )
        await self._audit("inventory.stock_adjusted", "success", level.id,
                          {"variant_id": str(variant_id), "delta": delta})
        return level

    async def receive_stock(self, location_id: UUID, variant_id: UUID, quantity: int, reason: str | None) -> Any:
        """A receipt is a positive adjustment with its own ledger entry type, so
        goods-in is distinguishable from a manual correction in the ledger."""
        ensure_positive_quantity(quantity)
        location = await self.repository.get_location(self.actor.tenant_id, location_id)
        if location is None:
            await self._missing("location", location_id)
        ensure_reference_active(location.status, "Location")
        if not await self.repository.variant_exists(self.actor.tenant_id, variant_id):
            await self._missing("variant", variant_id)
        level = await self.repository.get_or_create_stock_level(
            self.actor.tenant_id, self.actor.user_id, location_id, variant_id
        )
        level.on_hand += quantity
        level.updated_by = self.actor.user_id
        level.version += 1
        await self._ledger(location_id, variant_id, "receipt", quantity, level.on_hand, reason=reason)
        await self.repository.flush()
        await self.repository.add_event(
            self._event("inventory.stock.received.v1", "inventory.stock_level", level.id, level.version,
                        {"location_id": str(location_id), "variant_id": str(variant_id), "quantity": quantity,
                         "on_hand": level.on_hand})
        )
        await self._audit("inventory.stock_received", "success", level.id, {"variant_id": str(variant_id)})
        return level

    async def recount_stock(self, location_id: UUID, variant_id: UUID, counted: int, reason: str | None) -> Any:
        """A recount sets on_hand to a physically counted value; the ledger
        records the signed delta so the correction is fully explained."""
        ensure_recount_nonnegative(counted)
        location = await self.repository.get_location(self.actor.tenant_id, location_id)
        if location is None:
            await self._missing("location", location_id)
        ensure_reference_active(location.status, "Location")
        if not await self.repository.variant_exists(self.actor.tenant_id, variant_id):
            await self._missing("variant", variant_id)
        level = await self.repository.get_or_create_stock_level(
            self.actor.tenant_id, self.actor.user_id, location_id, variant_id
        )
        if counted < level.reserved:
            raise InsufficientStock("Recounted quantity is below the units currently reserved at this location")
        delta = counted - level.on_hand
        level.on_hand = counted
        level.updated_by = self.actor.user_id
        level.version += 1
        await self._ledger(location_id, variant_id, "recount", delta, level.on_hand, reason=reason)
        await self.repository.flush()
        await self.repository.add_event(
            self._event("inventory.recount.applied.v1", "inventory.stock_level", level.id, level.version,
                        {"location_id": str(location_id), "variant_id": str(variant_id), "counted": counted,
                         "delta": delta})
        )
        await self._audit("inventory.stock_recounted", "success", level.id, {"variant_id": str(variant_id)})
        return level

    # --- Transfers ---

    async def create_transfer(self, data: dict[str, Any]) -> Any:
        quantity = data["quantity"]
        ensure_positive_quantity(quantity)
        from_location_id = data["from_location_id"]
        to_location_id = data["to_location_id"]
        variant_id = data["variant_id"]
        if from_location_id == to_location_id:
            raise InventoryConflict("A transfer must move stock between two different Locations")
        source = await self.repository.get_location(self.actor.tenant_id, from_location_id)
        if source is None:
            await self._missing("location", from_location_id)
        destination = await self.repository.get_location(self.actor.tenant_id, to_location_id)
        if destination is None:
            await self._missing("location", to_location_id)
        ensure_reference_active(source.status, "Location")
        ensure_reference_active(destination.status, "Location")
        if not await self.repository.variant_exists(self.actor.tenant_id, variant_id):
            await self._missing("variant", variant_id)

        source_level = await self.repository.get_stock_level_by_location_variant(
            self.actor.tenant_id, from_location_id, variant_id, lock=True
        )
        available = source_level.available if source_level is not None else 0
        if source_level is None or quantity > available:
            await self._audit("inventory.stock_insufficient", "denied", from_location_id,
                              {"variant_id": str(variant_id), "requested": quantity, "available": available})
            ensure_can_ship_transfer(available, quantity)  # raises InsufficientStock
            raise InsufficientStock(f"Cannot transfer {quantity}; source location has no stock")

        # Ship: decrement source on_hand now; count as incoming at destination.
        source_level.on_hand -= quantity
        source_level.updated_by = self.actor.user_id
        source_level.version += 1
        destination_level = await self.repository.get_or_create_stock_level(
            self.actor.tenant_id, self.actor.user_id, to_location_id, variant_id
        )
        destination_level.incoming += quantity
        destination_level.updated_by = self.actor.user_id
        destination_level.version += 1

        transfer = await self.repository.create_transfer(
            self.actor.tenant_id,
            self.actor.user_id,
            {
                "from_location_id": from_location_id,
                "to_location_id": to_location_id,
                "variant_id": variant_id,
                "quantity": quantity,
                "reason": data.get("reason"),
                "status": "in_transit",
            },
        )
        await self.repository.flush()
        await self._ledger(from_location_id, variant_id, "transfer_out", -quantity, source_level.on_hand,
                           reference_type="transfer", reference_id=transfer.id)
        await self.repository.add_event(
            self._event("inventory.transfer.created.v1", "inventory.transfer", transfer.id, transfer.version,
                        {"variant_id": str(variant_id), "quantity": quantity, "from_location_id": str(from_location_id),
                         "to_location_id": str(to_location_id)})
        )
        await self._audit("inventory.transfer_created", "success", transfer.id)
        return transfer

    async def complete_transfer(self, resource_id: UUID, expected: int) -> Any:
        transfer = await self.repository.get_transfer(self.actor.tenant_id, resource_id, lock=True)
        if transfer is None:
            await self._missing("transfer", resource_id)
        await self._version("transfer", transfer, expected)
        ensure_transfer_completable(transfer.status)
        destination_level = await self.repository.get_or_create_stock_level(
            self.actor.tenant_id, self.actor.user_id, transfer.to_location_id, transfer.variant_id
        )
        destination_level.incoming -= transfer.quantity
        destination_level.on_hand += transfer.quantity
        destination_level.updated_by = self.actor.user_id
        destination_level.version += 1
        transfer.status = "completed"
        transfer.updated_by = self.actor.user_id
        transfer.version += 1
        await self.repository.flush()
        await self._ledger(transfer.to_location_id, transfer.variant_id, "transfer_in", transfer.quantity,
                           destination_level.on_hand, reference_type="transfer", reference_id=transfer.id)
        await self.repository.add_event(
            self._event("inventory.transfer.completed.v1", "inventory.transfer", transfer.id, transfer.version,
                        {"variant_id": str(transfer.variant_id), "quantity": transfer.quantity})
        )
        await self._audit("inventory.transfer_completed", "success", transfer.id)
        return transfer

    async def cancel_transfer(self, resource_id: UUID, expected: int) -> Any:
        transfer = await self.repository.get_transfer(self.actor.tenant_id, resource_id, lock=True)
        if transfer is None:
            await self._missing("transfer", resource_id)
        await self._version("transfer", transfer, expected)
        ensure_transfer_completable(transfer.status)
        # Return the in-transit units to the source; clear destination incoming.
        source_level = await self.repository.get_or_create_stock_level(
            self.actor.tenant_id, self.actor.user_id, transfer.from_location_id, transfer.variant_id
        )
        source_level.on_hand += transfer.quantity
        source_level.updated_by = self.actor.user_id
        source_level.version += 1
        destination_level = await self.repository.get_or_create_stock_level(
            self.actor.tenant_id, self.actor.user_id, transfer.to_location_id, transfer.variant_id
        )
        destination_level.incoming -= transfer.quantity
        destination_level.updated_by = self.actor.user_id
        destination_level.version += 1
        transfer.status = "cancelled"
        transfer.updated_by = self.actor.user_id
        transfer.version += 1
        await self.repository.flush()
        await self._ledger(transfer.from_location_id, transfer.variant_id, "transfer_in", transfer.quantity,
                           source_level.on_hand, reference_type="transfer", reference_id=transfer.id,
                           reason="transfer cancelled")
        await self.repository.add_event(
            self._event("inventory.transfer.cancelled.v1", "inventory.transfer", transfer.id, transfer.version, {})
        )
        await self._audit("inventory.transfer_cancelled", "success", transfer.id)
        return transfer

    # --- Allocation (pure planning over live stock) ---

    async def allocate_for_scope(
        self, variant_id: UUID, quantity: int, scope_type: str, scope_id: UUID
    ) -> AllocationPlan:
        ensure_positive_quantity(quantity)
        if scope_type not in ("store", "channel", "market"):
            raise InventoryConflict("scope_type must be one of: store, channel, market")
        if not await self.repository.variant_exists(self.actor.tenant_id, variant_id):
            await self._missing("variant", variant_id)
        candidates = await self._scope_candidates(variant_id, scope_type, scope_id)
        return allocate(quantity, candidates)

    async def _scope_candidates(self, variant_id: UUID, scope_type: str, scope_id: UUID) -> list[LocationCandidate]:
        scopes = await self.repository.list_active_scopes_for(self.actor.tenant_id, scope_type, scope_id)
        priority_by_warehouse = {scope.warehouse_id: scope.priority for scope in scopes}
        location_ids = await self.repository.active_location_ids_for_warehouses(
            self.actor.tenant_id, list(priority_by_warehouse.keys())
        )
        levels = await self.repository.list_available_candidates(self.actor.tenant_id, variant_id, location_ids)
        # Map each candidate location back to its warehouse priority.
        location_to_warehouse: dict[UUID, UUID] = {}
        for level in levels:
            location = await self.repository.get_location(self.actor.tenant_id, level.location_id)
            if location is not None:
                location_to_warehouse[level.location_id] = location.warehouse_id
        return [
            LocationCandidate(
                location_id=level.location_id,
                warehouse_id=location_to_warehouse[level.location_id],
                priority=priority_by_warehouse.get(location_to_warehouse[level.location_id], 0),
                available=level.available,
            )
            for level in levels
            if level.location_id in location_to_warehouse
        ]

    # --- Reservations ---

    async def reserve_for_scope(self, data: dict[str, Any]) -> list[Any]:
        variant_id = data["variant_id"]
        quantity = data["quantity"]
        scope_type = data["scope_type"]
        scope_id = data["scope_id"]
        ensure_positive_quantity(quantity)
        ensure_scope_reference(
            scope_type,
            scope_id if scope_type == "store" else None,
            scope_id if scope_type == "channel" else None,
            scope_id if scope_type == "market" else None,
        )
        if not await self.repository.variant_exists(self.actor.tenant_id, variant_id):
            await self._missing("variant", variant_id)

        candidates = await self._scope_candidates(variant_id, scope_type, scope_id)
        plan = allocate(quantity, candidates)
        if not plan.fully_allocated:
            await self._audit("inventory.reservation_shortfall", "denied", variant_id,
                              {"requested": quantity, "allocated": plan.allocated})
            raise InsufficientStock(
                f"Cannot reserve {quantity}; only {plan.allocated} available across the scope's warehouses"
            )
        return await self._commit_reservation_plan(data, plan, scope_type, scope_id)

    async def _commit_reservation_plan(
        self, data: dict[str, Any], plan: AllocationPlan, scope_type: str, scope_id: UUID
    ) -> list[Any]:
        variant_id = data["variant_id"]
        expires_at = data.get("expires_at")
        reservations: list[Any] = []
        for allocation in plan.allocations:
            reservation = await self._hold(
                variant_id=variant_id,
                location_id=allocation.location_id,
                quantity=allocation.quantity,
                scope_type=scope_type,
                store_id=scope_id if scope_type == "store" else None,
                channel_id=scope_id if scope_type == "channel" else None,
                market_id=scope_id if scope_type == "market" else None,
                reference_type=data.get("reference_type"),
                reference_id=data.get("reference_id"),
                expires_at=expires_at,
            )
            reservations.append(reservation)
        await self.repository.flush()
        return reservations

    async def _hold(
        self,
        *,
        variant_id: UUID,
        location_id: UUID,
        quantity: int,
        scope_type: str | None = None,
        store_id: UUID | None = None,
        channel_id: UUID | None = None,
        market_id: UUID | None = None,
        reference_type: str | None = None,
        reference_id: UUID | None = None,
        expires_at: datetime | None = None,
    ) -> Any:
        """The single place a hold is placed: locks the level, checks available
        under the lock (no overselling), increments reserved, writes the
        reservation row + ledger entry + event. Shared by scope-based reserves
        and the scopeless storefront checkout."""
        level = await self.repository.get_stock_level_by_location_variant(
            self.actor.tenant_id, location_id, variant_id, lock=True
        )
        if level is None:
            raise InsufficientStock("Stock disappeared before it could be reserved")
        ensure_can_reserve(level.available, quantity)
        level.reserved += quantity
        level.updated_by = self.actor.user_id
        level.version += 1
        reservation = await self.repository.create_reservation(
            self.actor.tenant_id,
            self.actor.user_id,
            {
                "variant_id": variant_id,
                "location_id": location_id,
                "quantity": quantity,
                "scope_type": scope_type,
                "store_id": store_id,
                "channel_id": channel_id,
                "market_id": market_id,
                "reference_type": reference_type,
                "reference_id": reference_id,
                "expires_at": expires_at,
                "status": "held",
            },
        )
        await self.repository.flush()
        await self._ledger(location_id, variant_id, "reservation_hold", 0, level.on_hand,
                           reference_type="reservation", reference_id=reservation.id)
        await self.repository.add_event(
            self._event("inventory.reservation.held.v1", "inventory.reservation", reservation.id, reservation.version,
                        {"variant_id": str(variant_id), "location_id": str(location_id), "quantity": quantity})
        )
        await self._audit("inventory.reservation_held", "success", reservation.id)
        return reservation

    async def reserve_available(
        self,
        variant_id: UUID,
        quantity: int,
        *,
        reference_type: str,
        reference_id: UUID,
        expires_at: datetime | None = None,
    ) -> list[Any]:
        """Reserve `quantity` of a variant across the tenant's active locations
        (no fulfillment scope required) — the entry point for a single-store
        storefront checkout. Fails atomically with InsufficientStock if the
        full quantity can't be covered, so a checkout can never oversell."""
        ensure_positive_quantity(quantity)
        if not await self.repository.variant_exists(self.actor.tenant_id, variant_id):
            await self._missing("variant", variant_id)
        candidates = await self._available_candidates(variant_id)
        plan = allocate(quantity, candidates)
        if not plan.fully_allocated:
            await self._audit("inventory.reservation_shortfall", "denied", variant_id,
                              {"requested": quantity, "allocated": plan.allocated})
            raise InsufficientStock(
                f"Cannot reserve {quantity}; only {plan.allocated} available for this variant"
            )
        reservations: list[Any] = []
        for allocation in plan.allocations:
            reservations.append(
                await self._hold(
                    variant_id=variant_id,
                    location_id=allocation.location_id,
                    quantity=allocation.quantity,
                    reference_type=reference_type,
                    reference_id=reference_id,
                    expires_at=expires_at,
                )
            )
        await self.repository.flush()
        return reservations

    async def _available_candidates(self, variant_id: UUID) -> list[LocationCandidate]:
        location_ids = await self.repository.active_location_ids(self.actor.tenant_id)
        levels = await self.repository.list_available_candidates(self.actor.tenant_id, variant_id, location_ids)
        candidates: list[LocationCandidate] = []
        for level in levels:
            location = await self.repository.get_location(self.actor.tenant_id, level.location_id)
            warehouse_id = location.warehouse_id if location is not None else level.location_id
            candidates.append(
                LocationCandidate(
                    location_id=level.location_id,
                    warehouse_id=warehouse_id,
                    priority=0,
                    available=level.available,
                )
            )
        return candidates

    async def release_reservation(self, resource_id: UUID, expected: int) -> Any:
        reservation = await self.repository.get_reservation(self.actor.tenant_id, resource_id, lock=True)
        if reservation is None:
            await self._missing("reservation", resource_id)
        await self._version("reservation", reservation, expected)
        return await self._release_one(reservation)

    async def commit_reservation(self, resource_id: UUID, expected: int) -> Any:
        """Fulfillment: consumes the hold. Decrements both on_hand and reserved
        by the reserved quantity, turning a promise into a shipped unit."""
        reservation = await self.repository.get_reservation(self.actor.tenant_id, resource_id, lock=True)
        if reservation is None:
            await self._missing("reservation", resource_id)
        await self._version("reservation", reservation, expected)
        return await self._commit_one(reservation)

    async def _release_one(self, reservation: Any, *, reason: str | None = None, expired: bool = False) -> Any:
        """Return a held reservation's units to available. `expired` marks it as
        auto-expired (sweeper) rather than manually released; both undo the same
        `reserved` increment."""
        ensure_reservation_releasable(reservation.status)
        level = await self.repository.get_stock_level_by_location_variant(
            self.actor.tenant_id, reservation.location_id, reservation.variant_id, lock=True
        )
        if level is not None:
            level.reserved -= reservation.quantity
            level.updated_by = self.actor.user_id
            level.version += 1
        reservation.status = "expired" if expired else "released"
        reservation.updated_by = self.actor.user_id
        reservation.version += 1
        await self.repository.flush()
        await self._ledger(reservation.location_id, reservation.variant_id, "reservation_release", 0,
                           level.on_hand if level is not None else 0,
                           reference_type="reservation", reference_id=reservation.id, reason=reason)
        event_type = "inventory.reservation.expired.v1" if expired else "inventory.reservation.released.v1"
        await self.repository.add_event(
            self._event(event_type, "inventory.reservation", reservation.id,
                        reservation.version, {"variant_id": str(reservation.variant_id)})
        )
        await self._audit(
            "inventory.reservation_expired" if expired else "inventory.reservation_released",
            "success", reservation.id,
        )
        return reservation

    async def _commit_one(self, reservation: Any) -> Any:
        ensure_reservation_releasable(reservation.status)
        ensure_reservation_not_expired(reservation.expires_at, datetime.now(UTC))
        level = await self.repository.get_stock_level_by_location_variant(
            self.actor.tenant_id, reservation.location_id, reservation.variant_id, lock=True
        )
        if level is None or level.reserved < reservation.quantity or level.on_hand < reservation.quantity:
            raise InsufficientStock("Stock level no longer supports committing this reservation")
        level.reserved -= reservation.quantity
        level.on_hand -= reservation.quantity
        level.updated_by = self.actor.user_id
        level.version += 1
        reservation.status = "committed"
        reservation.updated_by = self.actor.user_id
        reservation.version += 1
        await self.repository.flush()
        await self._ledger(reservation.location_id, reservation.variant_id, "reservation_commit",
                           -reservation.quantity, level.on_hand,
                           reference_type="reservation", reference_id=reservation.id)
        await self.repository.add_event(
            self._event("inventory.reservation.committed.v1", "inventory.reservation", reservation.id,
                        reservation.version, {"variant_id": str(reservation.variant_id),
                                              "quantity": reservation.quantity})
        )
        await self._audit("inventory.reservation_committed", "success", reservation.id)
        return reservation

    # --- Order-driven reservation lifecycle (by reference) ---

    async def commit_reservations_for(self, reference_type: str, reference_id: UUID) -> int:
        """Consume every held reservation a document placed (e.g. dispatch of a
        storefront order). Idempotent: only 'held' rows are acted on, so
        re-running commits nothing a second time."""
        held = await self.repository.list_reservations_by_reference(
            self.actor.tenant_id, reference_type, reference_id, status="held", lock=True
        )
        for reservation in held:
            await self._commit_one(reservation)
        return len(held)

    async def release_reservations_for(
        self, reference_type: str, reference_id: UUID, *, reason: str | None = None
    ) -> int:
        """Release every still-held reservation a document placed (cancel /
        payment failure before dispatch)."""
        held = await self.repository.list_reservations_by_reference(
            self.actor.tenant_id, reference_type, reference_id, status="held", lock=True
        )
        for reservation in held:
            await self._release_one(reservation, reason=reason)
        return len(held)

    async def restock_committed_for(
        self, reference_type: str, reference_id: UUID, *, reason: str | None = None
    ) -> int:
        """Cancel after dispatch: the stock already left on_hand, so a release
        would be wrong. Put the units back as an explicit `adjustment` (restock)
        movement in the ledger, at the same location they shipped from."""
        committed = await self.repository.list_reservations_by_reference(
            self.actor.tenant_id, reference_type, reference_id, status="committed", lock=True
        )
        for reservation in committed:
            level = await self.repository.get_or_create_stock_level(
                self.actor.tenant_id, self.actor.user_id, reservation.location_id, reservation.variant_id
            )
            level.on_hand += reservation.quantity
            level.updated_by = self.actor.user_id
            level.version += 1
            await self.repository.flush()
            await self._ledger(reservation.location_id, reservation.variant_id, "adjustment",
                               reservation.quantity, level.on_hand,
                               reference_type="reservation", reference_id=reservation.id,
                               reason=reason or "restock (order cancelled after dispatch)")
            await self.repository.add_event(
                self._event("inventory.stock.adjusted.v1", "inventory.stock_level", level.id, level.version,
                            {"location_id": str(reservation.location_id), "variant_id": str(reservation.variant_id),
                             "delta": reservation.quantity, "on_hand": level.on_hand, "reason": "restock"})
            )
            await self._audit("inventory.stock_adjusted", "success", level.id,
                              {"variant_id": str(reservation.variant_id), "delta": reservation.quantity, "restock": True})
        return len(committed)

    async def expire_due_reservations(self, *, now: datetime | None = None, limit: int = 100) -> int:
        """Release every held reservation whose expiry has passed. Rows are
        locked with SKIP LOCKED, so several sweeper workers are safe and each
        run is idempotent."""
        moment = now or datetime.now(UTC)
        due = await self.repository.list_due_reservations(self.actor.tenant_id, moment, limit=limit)
        for reservation in due:
            await self._release_one(reservation, reason="reservation expired", expired=True)
        return len(due)

    # --- Fulfillment scopes ---

    async def create_fulfillment_scope(self, data: dict[str, Any]) -> Any:
        warehouse = await self.repository.get_warehouse(self.actor.tenant_id, data["warehouse_id"])
        if warehouse is None:
            await self._missing("warehouse", data["warehouse_id"])
        ensure_reference_active(warehouse.status, "Warehouse")
        ensure_scope_reference(data["scope_type"], data.get("store_id"), data.get("channel_id"), data.get("market_id"))
        row = await self.repository.create_fulfillment_scope(
            self.actor.tenant_id,
            self.actor.user_id,
            {
                "warehouse_id": data["warehouse_id"],
                "scope_type": data["scope_type"],
                "store_id": data.get("store_id"),
                "channel_id": data.get("channel_id"),
                "market_id": data.get("market_id"),
                "priority": data.get("priority", 0),
                "status": "active",
            },
        )
        await self.repository.flush()
        await self.repository.add_event(
            self._event("inventory.fulfillment_scope.created.v1", "inventory.fulfillment_scope", row.id, row.version,
                        {"warehouse_id": str(row.warehouse_id), "scope_type": row.scope_type, "priority": row.priority})
        )
        await self._audit("inventory.fulfillment_scope_created", "success", row.id)
        return row

    async def archive_fulfillment_scope(self, resource_id: UUID, expected: int) -> Any:
        row = await self.repository.get_fulfillment_scope(self.actor.tenant_id, resource_id, lock=True)
        if row is None:
            await self._missing("fulfillment_scope", resource_id)
        await self._version("fulfillment_scope", row, expected)
        row.status = "archived"
        row.archived_at = datetime.now(UTC)
        row.updated_by = self.actor.user_id
        row.version += 1
        await self.repository.add_event(
            self._event("inventory.fulfillment_scope.archived.v1", "inventory.fulfillment_scope", row.id, row.version, {})
        )
        await self._audit("inventory.fulfillment_scope_archived", "success", row.id)
        return row

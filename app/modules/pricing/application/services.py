from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, NoReturn
from uuid import UUID

from app.application.auth import audit
from app.modules.platform.contracts.events import EventActor, EventEnvelope
from app.modules.pricing.contracts.repositories import PricingRepository
from app.modules.pricing.domain.policies import (
    PricingConflict,
    PricingNotFound,
    PricingVersionConflict,
    ensure_effective_window,
    ensure_expected_version,
    ensure_price_list_mutable,
    ensure_reference_active,
    ensure_scope_reference,
)
from app.modules.pricing.domain.values import (
    AssignmentCandidate,
    EntryCandidate,
    OverrideCandidate,
    ResolvedPrice,
    normalize_currency,
    normalized_code,
    resolve_effective_price,
)

_ENTRY_MONEY_FIELDS = ("unit_amount", "compare_at_amount", "msrp_amount", "cost_amount")
_SCOPE_TYPES = ("store", "channel", "market")


@dataclass(frozen=True, slots=True)
class PricingActor:
    user_id: UUID
    session_id: UUID | None
    tenant_id: UUID
    correlation_id: UUID


class PricingService:
    def __init__(self, repository: PricingRepository, actor: PricingActor, audit_session: Any) -> None:
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
        await self._audit("pricing.scope_denied", "denied", resource_id, {"kind": kind})
        raise PricingNotFound(f"{kind.replace('_', ' ').title()} not found")

    async def _version(self, kind: str, resource: Any, expected: int) -> None:
        try:
            ensure_expected_version(resource.version, expected)
        except PricingVersionConflict:
            await self._audit(
                "pricing.version_conflict", "denied", resource.id,
                {"kind": kind, "expected": expected, "current": resource.version},
            )
            raise

    # --- Price Lists ---

    async def create_price_list(self, data: dict[str, Any]) -> Any:
        currency_code = normalize_currency(data["currency_code"])
        if data.get("is_default"):
            existing_default = await self.repository.get_default_price_list(self.actor.tenant_id)
            if existing_default is not None:
                raise PricingConflict("Tenant already has a default Price List; unset it before assigning a new one")
        row = await self.repository.create_price_list(
            self.actor.tenant_id,
            self.actor.user_id,
            {
                "code": normalized_code(data["code"]),
                "name": data["name"].strip(),
                "currency_code": currency_code,
                "is_default": data.get("is_default", False),
                "notes": data.get("notes"),
                "status": "active",
            },
        )
        await self.repository.flush()
        await self.repository.add_event(
            self._event(
                "pricing.price_list.created.v1", "pricing.price_list", row.id, row.version,
                {"code": row.code, "currency_code": row.currency_code, "is_default": row.is_default},
            )
        )
        await self._audit("pricing.price_list_created", "success", row.id)
        return row

    async def update_price_list(self, resource_id: UUID, expected: int, data: dict[str, Any]) -> Any:
        row = await self.repository.get_price_list(self.actor.tenant_id, resource_id, lock=True)
        if row is None:
            await self._missing("price_list", resource_id)
        await self._version("price_list", row, expected)
        ensure_price_list_mutable(row.status)
        if data.get("is_default") and not row.is_default:
            existing_default = await self.repository.get_default_price_list(self.actor.tenant_id)
            if existing_default is not None and existing_default.id != row.id:
                raise PricingConflict("Tenant already has a default Price List; unset it before assigning a new one")
        changed: list[str] = []
        for field in ("name", "notes", "is_default"):
            if field in data and data[field] is not None:
                value = data[field].strip() if isinstance(data[field], str) else data[field]
                if getattr(row, field) != value:
                    setattr(row, field, value)
                    changed.append(field)
        row.updated_by = self.actor.user_id
        row.version += 1
        await self.repository.add_event(
            self._event("pricing.price_list.updated.v1", "pricing.price_list", row.id, row.version, {"changed_fields": changed})
        )
        await self._audit("pricing.price_list_updated", "success", row.id, {"changed_fields": changed})
        return row

    async def archive_price_list(self, resource_id: UUID, expected: int) -> Any:
        row = await self.repository.get_price_list(self.actor.tenant_id, resource_id, lock=True)
        if row is None:
            await self._missing("price_list", resource_id)
        await self._version("price_list", row, expected)
        row.status = "archived"
        row.archived_at = datetime.now(UTC)
        row.updated_by = self.actor.user_id
        row.version += 1
        await self.repository.add_event(
            self._event("pricing.price_list.archived.v1", "pricing.price_list", row.id, row.version, {})
        )
        await self._audit("pricing.price_list_archived", "success", row.id)
        return row

    # --- Price List Entries ---

    async def set_price_list_entry(self, price_list_id: UUID, variant_id: UUID, data: dict[str, Any]) -> Any:
        price_list = await self.repository.get_price_list(self.actor.tenant_id, price_list_id)
        if price_list is None:
            await self._missing("price_list", price_list_id)
        ensure_reference_active(price_list.status, "Price List")
        if not await self.repository.variant_exists(self.actor.tenant_id, variant_id):
            await self._missing("variant", variant_id)

        row, previous = await self.repository.upsert_price_list_entry(
            self.actor.tenant_id,
            self.actor.user_id,
            price_list_id,
            variant_id,
            {
                "unit_amount": data["unit_amount"],
                "compare_at_amount": data.get("compare_at_amount"),
                "msrp_amount": data.get("msrp_amount"),
                "cost_amount": data.get("cost_amount"),
                "status": "active",
            },
        )
        if previous is None:
            row.version = 1
        else:
            row.version += 1
        await self.repository.flush()

        for field in _ENTRY_MONEY_FIELDS:
            new_value = getattr(row, field)
            old_value = previous.get(field) if previous else None
            if old_value != new_value:
                await self.repository.add_history_entry(
                    self.actor.tenant_id,
                    {
                        "entity_type": "price_list_entry",
                        "entity_id": row.id,
                        "variant_id": row.variant_id,
                        "field_name": field,
                        "previous_amount": old_value,
                        "new_amount": new_value,
                        "currency_code": price_list.currency_code,
                        "changed_by": self.actor.user_id,
                        "reason": data.get("reason"),
                    },
                )

        await self.repository.add_event(
            self._event(
                "pricing.price_list_entry.set.v1",
                "pricing.price_list_entry",
                row.id,
                row.version,
                {"price_list_id": str(price_list_id), "variant_id": str(variant_id), "unit_amount": str(row.unit_amount)},
            )
        )
        await self._audit("pricing.price_list_entry_set", "success", row.id, {"variant_id": str(variant_id)})
        return row

    # --- Assignments ---

    async def create_assignment(self, data: dict[str, Any]) -> Any:
        price_list = await self.repository.get_price_list(self.actor.tenant_id, data["price_list_id"])
        if price_list is None:
            await self._missing("price_list", data["price_list_id"])
        ensure_reference_active(price_list.status, "Price List")
        ensure_scope_reference(data["scope_type"], data.get("store_id"), data.get("channel_id"), data.get("market_id"))
        ensure_effective_window(data.get("effective_from"), data.get("effective_until"))

        row = await self.repository.create_assignment(
            self.actor.tenant_id,
            self.actor.user_id,
            {
                "price_list_id": data["price_list_id"],
                "scope_type": data["scope_type"],
                "store_id": data.get("store_id"),
                "channel_id": data.get("channel_id"),
                "market_id": data.get("market_id"),
                "priority": data.get("priority", 0),
                "effective_from": data.get("effective_from"),
                "effective_until": data.get("effective_until"),
                "status": "active",
            },
        )
        await self.repository.flush()
        await self.repository.add_event(
            self._event(
                "pricing.assignment.created.v1", "pricing.assignment", row.id, row.version,
                {"price_list_id": str(row.price_list_id), "scope_type": row.scope_type, "priority": row.priority},
            )
        )
        await self._audit("pricing.assignment_created", "success", row.id)
        return row

    async def archive_assignment(self, resource_id: UUID, expected: int) -> Any:
        row = await self.repository.get_assignment(self.actor.tenant_id, resource_id, lock=True)
        if row is None:
            await self._missing("assignment", resource_id)
        await self._version("assignment", row, expected)
        row.status = "archived"
        row.archived_at = datetime.now(UTC)
        row.updated_by = self.actor.user_id
        row.version += 1
        await self.repository.add_event(
            self._event("pricing.assignment.archived.v1", "pricing.assignment", row.id, row.version, {})
        )
        await self._audit("pricing.assignment_archived", "success", row.id)
        return row

    # --- Variant Price Overrides ---

    async def create_override(self, data: dict[str, Any]) -> Any:
        if not await self.repository.variant_exists(self.actor.tenant_id, data["variant_id"]):
            await self._missing("variant", data["variant_id"])
        ensure_scope_reference(data["scope_type"], data.get("store_id"), data.get("channel_id"), data.get("market_id"))
        ensure_effective_window(data.get("effective_from"), data.get("effective_until"))
        currency_code = normalize_currency(data["currency_code"])

        row = await self.repository.create_override(
            self.actor.tenant_id,
            self.actor.user_id,
            {
                "variant_id": data["variant_id"],
                "scope_type": data["scope_type"],
                "store_id": data.get("store_id"),
                "channel_id": data.get("channel_id"),
                "market_id": data.get("market_id"),
                "unit_amount": data["unit_amount"],
                "compare_at_amount": data.get("compare_at_amount"),
                "currency_code": currency_code,
                "priority": data.get("priority", 0),
                "effective_from": data.get("effective_from"),
                "effective_until": data.get("effective_until"),
                "reason": data.get("reason"),
                "status": "active",
            },
        )
        await self.repository.flush()
        await self.repository.add_history_entry(
            self.actor.tenant_id,
            {
                "entity_type": "variant_price_override",
                "entity_id": row.id,
                "variant_id": row.variant_id,
                "field_name": "unit_amount",
                "previous_amount": None,
                "new_amount": row.unit_amount,
                "currency_code": currency_code,
                "changed_by": self.actor.user_id,
                "reason": row.reason,
            },
        )
        await self.repository.add_event(
            self._event(
                "pricing.variant_override.set.v1", "pricing.variant_override", row.id, row.version,
                {"variant_id": str(row.variant_id), "scope_type": row.scope_type, "unit_amount": str(row.unit_amount)},
            )
        )
        await self._audit("pricing.variant_override_set", "success", row.id, {"variant_id": str(data["variant_id"])})
        return row

    async def archive_override(self, resource_id: UUID, expected: int) -> Any:
        row = await self.repository.get_override(self.actor.tenant_id, resource_id, lock=True)
        if row is None:
            await self._missing("variant_override", resource_id)
        await self._version("variant_override", row, expected)
        row.status = "archived"
        row.archived_at = datetime.now(UTC)
        row.updated_by = self.actor.user_id
        row.version += 1
        await self.repository.add_event(
            self._event("pricing.variant_override.archived.v1", "pricing.variant_override", row.id, row.version, {})
        )
        await self._audit("pricing.variant_override_archived", "success", row.id)
        return row

    # --- Resolution ---

    async def resolve_price(
        self,
        variant_id: UUID,
        *,
        store_id: UUID | None,
        channel_id: UUID | None,
        market_id: UUID | None,
        at: datetime | None = None,
    ) -> ResolvedPrice | None:
        if not await self.repository.variant_exists(self.actor.tenant_id, variant_id):
            await self._missing("variant", variant_id)
        resolution_time = at or datetime.now(UTC)
        scopes = {"store": store_id, "channel": channel_id, "market": market_id}

        override_rows: list[Any] = []
        assignment_rows: list[Any] = []
        for scope_type in _SCOPE_TYPES:
            scope_id = scopes[scope_type]
            if scope_id is None:
                continue
            override_rows.extend(
                await self.repository.list_active_overrides_for_variant_scope(
                    self.actor.tenant_id, variant_id, scope_type, scope_id
                )
            )
            assignment_rows.extend(
                await self.repository.list_active_assignments_for_scope(self.actor.tenant_id, scope_type, scope_id)
            )

        overrides = [
            OverrideCandidate(
                id=row.id, unit_amount=row.unit_amount, compare_at_amount=row.compare_at_amount,
                currency_code=row.currency_code, priority=row.priority,
                effective_from=row.effective_from, effective_until=row.effective_until,
            )
            for row in override_rows
        ]
        assignments = [
            AssignmentCandidate(
                id=row.id, price_list_id=row.price_list_id, priority=row.priority,
                effective_from=row.effective_from, effective_until=row.effective_until,
            )
            for row in assignment_rows
        ]

        price_list_ids = list({assignment.price_list_id for assignment in assignments})
        entry_rows = await self.repository.list_entries_for_variant_in_lists(self.actor.tenant_id, variant_id, price_list_ids)
        currency_by_price_list: dict[UUID, str] = {}
        for entry in entry_rows:
            if entry.price_list_id not in currency_by_price_list:
                price_list = await self.repository.get_price_list(self.actor.tenant_id, entry.price_list_id)
                assert price_list is not None
                currency_by_price_list[entry.price_list_id] = price_list.currency_code
        entries_by_price_list = {
            entry.price_list_id: EntryCandidate(
                id=entry.id, price_list_id=entry.price_list_id, unit_amount=entry.unit_amount,
                compare_at_amount=entry.compare_at_amount, msrp_amount=entry.msrp_amount,
                cost_amount=entry.cost_amount, currency_code=currency_by_price_list[entry.price_list_id],
            )
            for entry in entry_rows
        }

        default_entry = None
        default_price_list = await self.repository.get_default_price_list(self.actor.tenant_id)
        if default_price_list is not None:
            default_row = await self.repository.get_price_list_entry_by_variant(
                self.actor.tenant_id, default_price_list.id, variant_id
            )
            if default_row is not None and default_row.status == "active":
                default_entry = EntryCandidate(
                    id=default_row.id, price_list_id=default_row.price_list_id, unit_amount=default_row.unit_amount,
                    compare_at_amount=default_row.compare_at_amount, msrp_amount=default_row.msrp_amount,
                    cost_amount=default_row.cost_amount, currency_code=default_price_list.currency_code,
                )

        return resolve_effective_price(
            variant_id=variant_id,
            at=resolution_time,
            overrides=overrides,
            assignments=assignments,
            entries_by_price_list=entries_by_price_list,
            default_entry=default_entry,
        )

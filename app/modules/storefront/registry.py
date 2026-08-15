"""Public storefront registry: maps a public store key to the tenant/store it
serves, so the storefront read endpoints can resolve a shopper-facing key
(e.g. "clickhome") to the internal tenant without a cross-tenant lookup.

Why a registry and not a DB read: catalog/platform tables are protected by
RLS FORCE keyed on `app.current_tenant_id`, and the app role has no BYPASSRLS.
Resolving store_code -> tenant would need to read across tenants *before* the
tenant context exists (a chicken-and-egg). A real deployment resolves this from
the request host (a public, non-RLS `storefront_domains` table). For this
preview a small config map is enough; override with STOREFRONT_REGISTRY (JSON)
to point at other tenants/stores without code changes.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class Storefront:
    key: str
    tenant_id: UUID
    store_id: UUID
    name: str
    currency: str
    locale: str


# Demo/seed default: the ClickHome store in the Empresa Demo tenant.
_DEFAULT: dict[str, dict[str, str]] = {
    "clickhome": {
        "tenant_id": "7dacbd20-bde4-46c3-ac45-b890427bf9ba",
        "store_id": "c2a70387-1789-4758-aed7-b5f566225f43",
        "name": "ClickHome",
        "currency": "USD",
        "locale": "es-EC",
    }
}


def _load() -> dict[str, Storefront]:
    raw = os.getenv("STOREFRONT_REGISTRY")
    source = json.loads(raw) if raw else _DEFAULT
    registry: dict[str, Storefront] = {}
    for key, cfg in source.items():
        registry[key] = Storefront(
            key=key,
            tenant_id=UUID(cfg["tenant_id"]),
            store_id=UUID(cfg["store_id"]),
            name=cfg.get("name", key),
            currency=cfg.get("currency", "USD"),
            locale=cfg.get("locale", "es-EC"),
        )
    return registry


_REGISTRY = _load()


def resolve(key: str) -> Storefront | None:
    return _REGISTRY.get(key)

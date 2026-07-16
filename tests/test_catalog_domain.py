from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.modules.catalog.domain.policies import (
    CatalogPolicyError,
    CatalogQuotaExceeded,
    CatalogVersionConflict,
    ensure_expected_version,
    ensure_product_activation,
    ensure_quota,
    ensure_store_assignment,
    ensure_variant_archive,
)
from app.modules.catalog.domain.values import (
    decode_cursor,
    encode_cursor,
    normalize_identifier,
    normalize_locale,
    normalize_sku,
    normalize_slug,
)


def test_sku_normalization_is_unicode_aware_and_case_insensitive() -> None:
    display, normalized = normalize_sku("  CAFE\u0301-001  ")

    assert display == "CAF\u00c9-001"
    assert normalized == "caf\u00e9-001"
    assert normalize_sku("Caf\u00e9-001")[1] == normalized


@pytest.mark.parametrize("value", ["", "   ", "bad\nvalue", "x" * 161])
def test_sku_rejects_empty_control_or_oversized_values(value: str) -> None:
    with pytest.raises(ValueError, match="SKU"):
        normalize_sku(value)


def test_identifiers_are_normalized_and_external_source_is_required() -> None:
    assert normalize_identifier("EAN", "1234-5670", None) == ("12345670", None)
    assert normalize_identifier("isbn", "0-306-40615-2", None) == (
        "0306406152",
        None,
    )
    assert normalize_identifier("external", "  Vendor-42 ", "ERP-Main") == (
        "vendor-42",
        "erp-main",
    )

    with pytest.raises(ValueError, match="source_system"):
        normalize_identifier("external", "vendor-42", None)
    with pytest.raises(ValueError, match="Invalid UPC"):
        normalize_identifier("upc", "abc", None)


def test_catalog_slug_and_locale_reuse_platform_normalization() -> None:
    assert normalize_slug("  Summer SALE ") == "summer-sale"
    assert normalize_locale("es-ec") == "es-EC"


def test_cursor_round_trip_is_opaque_and_rejects_tampering() -> None:
    created_at = datetime(2026, 7, 14, 12, 30, tzinfo=UTC)
    resource_id = uuid4()

    cursor = encode_cursor(created_at, resource_id)

    assert decode_cursor(cursor) == (created_at, resource_id)
    assert str(resource_id) not in cursor
    with pytest.raises(ValueError, match="Invalid catalog cursor"):
        decode_cursor(cursor[:-2] + "xx")


def test_optimistic_concurrency_requires_the_exact_version() -> None:
    ensure_expected_version(3, 3)

    with pytest.raises(CatalogVersionConflict, match="expected 2, current 3"):
        ensure_expected_version(3, 2)
    with pytest.raises(CatalogVersionConflict):
        ensure_expected_version(1, 0)


def test_quota_and_lifecycle_policies_protect_catalog_invariants() -> None:
    ensure_quota("catalog.products.max", 9, 10)
    ensure_product_activation(1)
    ensure_variant_archive("draft", 1)
    ensure_store_assignment("active", "active", "active")

    with pytest.raises(CatalogQuotaExceeded) as quota:
        ensure_quota("catalog.products.max", 10, 10)
    assert quota.value.entitlement == "catalog.products.max"
    assert quota.value.limit == 10

    with pytest.raises(CatalogPolicyError, match="active variant"):
        ensure_product_activation(0)
    with pytest.raises(CatalogPolicyError, match="only active variant"):
        ensure_variant_archive("active", 1)
    with pytest.raises(CatalogPolicyError, match="Only active stores"):
        ensure_store_assignment("active", "suspended", "active")
    with pytest.raises(CatalogPolicyError, match="Archived products"):
        ensure_store_assignment("archived", "active", "draft")

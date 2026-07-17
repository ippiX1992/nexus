from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.modules.catalog.domain.policies import (
    CatalogAttributesQuotaExceeded,
    CatalogPolicyError,
    ensure_attribute_options_supported,
    ensure_attribute_type_immutable,
    ensure_attributes_quota,
    ensure_product_attribute_value_assignable,
    ensure_product_type_attribute_assignable,
    ensure_required_attributes_present,
)
from app.modules.catalog.domain.values import (
    normalize_attribute_value,
    normalize_multi_select_values,
)


def test_normalize_text_value_strips_and_validates_length():
    column, value = normalize_attribute_value("TEXT", "  Aluminio  ")
    assert column == "value_text"
    assert value == "Aluminio"
    with pytest.raises(ValueError):
        normalize_attribute_value("TEXT", "x" * 501)


def test_normalize_integer_rejects_bool_and_float():
    column, value = normalize_attribute_value("INTEGER", 500)
    assert column == "value_integer"
    assert value == 500
    with pytest.raises(ValueError):
        normalize_attribute_value("INTEGER", True)
    with pytest.raises(ValueError):
        normalize_attribute_value("INTEGER", 3.5)


def test_normalize_decimal_accepts_numeric_strings():
    column, value = normalize_attribute_value("DECIMAL", "12.50")
    assert column == "value_decimal"
    assert value == Decimal("12.50")
    with pytest.raises(ValueError):
        normalize_attribute_value("DECIMAL", "not-a-number")


def test_normalize_boolean_requires_actual_bool():
    column, value = normalize_attribute_value("BOOLEAN", True)
    assert column == "value_boolean"
    assert value is True
    with pytest.raises(ValueError):
        normalize_attribute_value("BOOLEAN", "true")


def test_normalize_date_requires_iso_format():
    column, value = normalize_attribute_value("DATE", "2026-07-17")
    assert column == "value_date"
    assert value == date(2026, 7, 17)
    with pytest.raises(ValueError):
        normalize_attribute_value("DATE", "17/07/2026")


def test_normalize_datetime_requires_timezone():
    column, value = normalize_attribute_value("DATETIME", "2026-07-17T10:00:00+00:00")
    assert column == "value_datetime"
    assert value == datetime(2026, 7, 17, 10, 0, tzinfo=UTC)
    with pytest.raises(ValueError):
        normalize_attribute_value("DATETIME", "2026-07-17T10:00:00")


def test_normalize_select_returns_option_uuid():
    option_id = uuid4()
    column, value = normalize_attribute_value("SELECT", str(option_id))
    assert column == "value_option_id"
    assert value == option_id
    with pytest.raises(ValueError):
        normalize_attribute_value("SELECT", "not-a-uuid")


def test_normalize_multi_select_rejects_empty_and_duplicates():
    a, b = uuid4(), uuid4()
    assert normalize_multi_select_values([str(a), str(b)]) == [a, b]
    with pytest.raises(ValueError):
        normalize_multi_select_values([])
    with pytest.raises(ValueError):
        normalize_multi_select_values([str(a), str(a)])


def test_normalize_attribute_value_rejects_unsupported_type():
    with pytest.raises(ValueError):
        normalize_attribute_value("NOT_A_TYPE", "x")


def test_ensure_attribute_type_immutable_allows_no_change_but_rejects_change():
    ensure_attribute_type_immutable("TEXT", None)
    ensure_attribute_type_immutable("TEXT", "TEXT")
    with pytest.raises(CatalogPolicyError):
        ensure_attribute_type_immutable("TEXT", "INTEGER")


def test_ensure_attribute_options_supported_only_for_select_types():
    ensure_attribute_options_supported("SELECT")
    ensure_attribute_options_supported("MULTI_SELECT")
    with pytest.raises(CatalogPolicyError):
        ensure_attribute_options_supported("TEXT")


def test_ensure_product_type_attribute_assignable_rejects_archived():
    ensure_product_type_attribute_assignable("active")
    with pytest.raises(CatalogPolicyError):
        ensure_product_type_attribute_assignable("archived")


def test_ensure_product_attribute_value_assignable_requires_active_and_assigned():
    ensure_product_attribute_value_assignable("active", True)
    with pytest.raises(CatalogPolicyError):
        ensure_product_attribute_value_assignable("archived", True)
    with pytest.raises(CatalogPolicyError):
        ensure_product_attribute_value_assignable("active", False)


def test_ensure_required_attributes_present():
    required = frozenset({uuid4()})
    ensure_required_attributes_present(required, required)
    with pytest.raises(CatalogPolicyError):
        ensure_required_attributes_present(required, frozenset())


def test_ensure_attributes_quota_raises_409_style_exception():
    ensure_attributes_quota("catalog.attribute_options.max_per_attribute", 1, 5)
    with pytest.raises(CatalogAttributesQuotaExceeded):
        ensure_attributes_quota("catalog.attribute_options.max_per_attribute", 5, 5)

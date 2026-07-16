from uuid import uuid4

import pytest

from app.modules.catalog.domain.policies import (
    CatalogOptionsQuotaExceeded,
    CatalogPolicyError,
    ensure_combination_complete,
    ensure_generation_within_limits,
    ensure_options_quota,
    ensure_product_option_retirable,
)
from app.modules.catalog.domain.values import (
    combination_fingerprint,
    derive_variant_sku,
    normalize_swatch_hex,
)


def test_fingerprint_is_order_independent_and_uses_only_stable_ids() -> None:
    option_a, option_b = uuid4(), uuid4()
    value_a, value_b = uuid4(), uuid4()

    forward = combination_fingerprint([(option_a, value_a), (option_b, value_b)])
    reversed_order = combination_fingerprint([(option_b, value_b), (option_a, value_a)])

    assert forward is not None
    assert forward == reversed_order
    assert len(forward) == 64
    assert all(c in "0123456789abcdef" for c in forward)


def test_fingerprint_changes_when_any_pair_changes() -> None:
    option_a, option_b = uuid4(), uuid4()
    value_a, value_b, value_c = uuid4(), uuid4(), uuid4()

    base = combination_fingerprint([(option_a, value_a), (option_b, value_b)])
    changed_value = combination_fingerprint([(option_a, value_a), (option_b, value_c)])
    fewer_pairs = combination_fingerprint([(option_a, value_a)])

    assert base != changed_value
    assert base != fewer_pairs


def test_fingerprint_is_none_for_empty_combination_not_hash_of_empty_string() -> None:
    assert combination_fingerprint([]) is None


def test_fingerprint_never_depends_on_position_or_insertion_order() -> None:
    # Same set of pairs supplied in three different orders must always
    # collapse to the same fingerprint -- this is what makes reordering
    # Options in the UI safe without invalidating existing combinations.
    pairs = [(uuid4(), uuid4()) for _ in range(4)]
    import random

    shuffled_once = pairs.copy()
    random.shuffle(shuffled_once)
    shuffled_twice = pairs.copy()
    random.shuffle(shuffled_twice)

    assert combination_fingerprint(pairs) == combination_fingerprint(shuffled_once) == combination_fingerprint(shuffled_twice)


def test_derive_variant_sku_is_deterministic_and_order_independent() -> None:
    sku_1, normalized_1 = derive_variant_sku("NX-SHIRT", ["red", "xl"])
    sku_2, normalized_2 = derive_variant_sku("nx-shirt", ["XL", "RED"])

    assert sku_1 == sku_2 == "NX-SHIRT-RED-XL"
    assert normalized_1 == normalized_2


def test_normalize_swatch_hex_accepts_hash_rrggbb_and_rejects_the_rest() -> None:
    assert normalize_swatch_hex(None) is None
    assert normalize_swatch_hex("#ff0000") == "#FF0000"

    with pytest.raises(ValueError, match="swatch_hex"):
        normalize_swatch_hex("red")
    with pytest.raises(ValueError, match="swatch_hex"):
        normalize_swatch_hex("#fff")


def test_combination_completeness_requires_exactly_the_required_options() -> None:
    required = frozenset({uuid4(), uuid4()})
    only_one = frozenset({next(iter(required))})
    extra = frozenset(required | {uuid4()})

    ensure_combination_complete(required, required)

    with pytest.raises(CatalogPolicyError, match="missing a value"):
        ensure_combination_complete(required, only_one)
    with pytest.raises(CatalogPolicyError, match="not assigned"):
        ensure_combination_complete(required, extra)


def test_product_option_retirable_only_when_no_active_variants_use_it() -> None:
    ensure_product_option_retirable(0)

    with pytest.raises(CatalogPolicyError, match="active Variants use it"):
        ensure_product_option_retirable(1)


def test_options_quota_raises_the_409_mapped_exception_not_the_429_one() -> None:
    ensure_options_quota("catalog.option_values.max_per_option", 5, 10)

    with pytest.raises(CatalogOptionsQuotaExceeded) as excinfo:
        ensure_options_quota("catalog.option_values.max_per_option", 10, 10)
    assert excinfo.value.entitlement == "catalog.option_values.max_per_option"
    assert excinfo.value.limit == 10


def test_generation_limits_check_both_per_operation_and_remaining_capacity() -> None:
    ensure_generation_within_limits(10, 50, 20)

    with pytest.raises(CatalogOptionsQuotaExceeded, match="combination_generation"):
        ensure_generation_within_limits(60, 50, 100)
    with pytest.raises(CatalogOptionsQuotaExceeded, match="variant_combinations"):
        ensure_generation_within_limits(30, 50, 20)

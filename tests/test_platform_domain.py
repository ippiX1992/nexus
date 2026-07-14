from decimal import Decimal
from uuid import uuid4

import pytest

from app.modules.platform.application.idempotency import request_fingerprint
from app.modules.platform.application.jobs import sanitize_job_error
from app.modules.platform.contracts.events import EventActor, EventEnvelope
from app.modules.platform.domain.policies import (
    PlatformPolicyError,
    QuotaExceeded,
    ResourceScope,
    ensure_environment_flags,
    ensure_quota,
    ensure_store_transition,
)
from app.modules.platform.domain.values import (
    MoneyConfiguration,
    normalize_code,
    validate_country,
    validate_currency,
    validate_locale,
    validate_timezone,
)


def test_standard_values_are_normalized() -> None:
    assert validate_locale("es_EC") == "es-EC"
    assert validate_country("ec") == "EC"
    assert validate_currency("usd") == ("USD", 2)
    assert validate_timezone("America/Guayaquil") == "America/Guayaquil"
    assert normalize_code(" Main_STORE ") == "main-store"
    assert MoneyConfiguration.from_currency("JPY").quantizer() == Decimal("1")


@pytest.mark.parametrize("value", ["not a code", "_bad", ""])
def test_resource_code_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_code(value)


def test_store_transitions_and_quotas_are_policies() -> None:
    ensure_store_transition("draft", "active")
    with pytest.raises(PlatformPolicyError):
        ensure_store_transition("archived", "active")
    with pytest.raises(QuotaExceeded):
        ensure_quota("stores.max", 1, 1)
    with pytest.raises(PlatformPolicyError):
        ensure_environment_flags("preview", True)


def test_event_envelope_has_stable_v1_contract() -> None:
    tenant_id, store_id, user_id, correlation_id = uuid4(), uuid4(), uuid4(), uuid4()
    event = EventEnvelope.create(event_type="platform.store.created.v1", tenant_id=tenant_id, store_id=store_id, aggregate_type="store", aggregate_id=store_id, correlation_id=correlation_id, actor=EventActor(user_id, None), data={"name": "Main"})
    value = event.to_dict()
    assert value["event_version"] == 1
    assert value["tenant_id"] == str(tenant_id)
    assert value["actor"]["user_id"] == str(user_id)
    with pytest.raises(ValueError):
        EventEnvelope.create(event_type="platform.store.created", tenant_id=tenant_id, store_id=store_id, aggregate_type="store", aggregate_id=store_id, correlation_id=correlation_id, actor=EventActor(user_id, None), data={})


def test_invalid_registered_standards_are_rejected() -> None:
    for validator, value in (
        (validate_locale, "not-a-real-locale"),
        (validate_country, "ZZ"),
        (validate_currency, "TOOLONG"),
        (validate_timezone, "Mars/Olympus"),
    ):
        with pytest.raises(ValueError):
            validator(value)


def test_scope_fingerprint_and_error_sanitization_are_deterministic() -> None:
    tenant_id, resource_id = uuid4(), uuid4()
    scope = ResourceScope(tenant_id, "store", resource_id, None)
    assert scope.contains(tenant_id, resource_id)
    assert not scope.contains(uuid4(), resource_id)
    first = request_fingerprint("post", "/stores", {"name": "A", "code": "a"})
    second = request_fingerprint("POST", "/stores", {"code": "a", "name": "A"})
    assert first == second
    assert sanitize_job_error(RuntimeError("safe")) == "RuntimeError: safe"

from datetime import UTC, datetime
from uuid import uuid4

import jwt
import pyotp
import pytest

from app.application.authorization import TenantContext, ensure_last_owner, require_permissions
from app.core.config import Settings
from app.core.security import (
    create_token,
    decode_token,
    decrypt_secret,
    encrypt_secret,
    generate_recovery_codes,
    hash_password,
    token_hash,
    verify_password,
)
from app.infrastructure.tenant_context import rls_tenant_clause


def settings(**changes): return Settings(jwt_secret="x"*40,**changes)
def test_password_hash_never_contains_plaintext():
    hashed=hash_password("Correct-Horse-99")
    assert "Correct-Horse-99" not in hashed and verify_password("Correct-Horse-99",hashed)
def test_refresh_hash_is_deterministic_and_one_way():
    assert token_hash("secret")==token_hash("secret") and token_hash("secret")!="secret"
def test_access_token_contains_type_and_expires():
    raw,expires,_=create_token(uuid4(),"access",settings())
    assert decode_token(raw,settings(),"access")["type"]=="access" and expires>datetime.now(UTC)
def test_expired_access_token_is_rejected():
    s=settings(access_token_minutes=-1); raw,_,_=create_token(uuid4(),"access",s)
    with pytest.raises(jwt.ExpiredSignatureError): decode_token(raw,s,"access")
def test_wrong_token_type_is_rejected():
    s=settings(); raw,_,_=create_token(uuid4(),"refresh",s)
    with pytest.raises(jwt.InvalidTokenError): decode_token(raw,s,"access")
def test_totp_secret_encrypted_at_rest():
    s=settings(); secret=pyotp.random_base32(); encrypted=encrypt_secret(secret,s)
    assert secret not in encrypted and decrypt_secret(encrypted,s)==secret
def test_recovery_codes_are_unique():
    codes=generate_recovery_codes(); assert len(codes)==10 and len(set(codes))==10
def test_permission_guard_denies_missing_permission():
    context=TenantContext(uuid4(),uuid4(),uuid4(),None,frozenset({"viewer"}),frozenset({"tenant.read"}))
    with pytest.raises(PermissionError): require_permissions(context,"tenant.update")
def test_last_owner_is_protected():
    with pytest.raises(ValueError): ensure_last_owner(1,True)
def test_owner_can_be_changed_when_another_owner_exists(): ensure_last_owner(2,True)

def test_rls_clause_uses_transaction_setting(): assert "app.current_tenant_id" in rls_tenant_clause()

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
import pyotp
from cryptography.fernet import Fernet
from pwdlib import PasswordHash

from app.core.config import Settings

_passwords=PasswordHash.recommended()
def hash_password(v:str)->str: return _passwords.hash(v)
def verify_password(v:str,h:str)->bool: return _passwords.verify(v,h)
def token_hash(v:str)->str: return hashlib.sha256(v.encode()).hexdigest()
def hash_recovery_code(v:str)->str: return _passwords.hash(v)
def verify_recovery_code(v:str,h:str)->bool: return _passwords.verify(v,h)
def _fernet(settings:Settings)->Fernet:
    key=base64.urlsafe_b64encode(hashlib.sha256(settings.jwt_secret.encode()).digest()); return Fernet(key)
def encrypt_secret(v:str,settings:Settings)->str: return _fernet(settings).encrypt(v.encode()).decode()
def decrypt_secret(v:str,settings:Settings)->str: return _fernet(settings).decrypt(v.encode()).decode()
def generate_recovery_codes(count:int=10)->list[str]: return [secrets.token_hex(5).upper() for _ in range(count)]
def create_token(subject:UUID,token_type:str,settings:Settings,**claims)->tuple[str,datetime,UUID]:
    now=datetime.now(UTC); minutes=settings.access_token_minutes if token_type=="access" else settings.two_factor_challenge_minutes
    expiry=now+(timedelta(days=settings.refresh_token_days) if token_type=="refresh" else timedelta(minutes=minutes)); jti=uuid4()
    payload={"sub":str(subject),"type":token_type,"jti":str(jti),"iat":now,"exp":expiry,**claims}
    return jwt.encode(payload,settings.jwt_secret,algorithm=settings.jwt_algorithm),expiry,jti
def decode_token(token:str,settings:Settings,expected_type:str|None=None)->dict:
    payload=jwt.decode(token,settings.jwt_secret,algorithms=[settings.jwt_algorithm])
    if expected_type and payload.get("type")!=expected_type: raise jwt.InvalidTokenError("wrong token type")
    return payload
def new_totp_secret()->str: return pyotp.random_base32()
def totp_uri(secret:str,email:str,issuer:str="Nexus")->str: return pyotp.TOTP(secret).provisioning_uri(email,issuer_name=issuer)
def verify_totp(secret:str,code:str)->bool: return pyotp.TOTP(secret).verify(code,valid_window=1)

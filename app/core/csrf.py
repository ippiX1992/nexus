import hmac
import secrets

from fastapi import HTTPException, Request

from app.core.config import Settings


def new_csrf_token()->str: return secrets.token_urlsafe(32)
def validate_csrf(request:Request,settings:Settings)->None:
    cookie=request.cookies.get("csrf_token"); header=request.headers.get("x-csrf-token"); origin=request.headers.get("origin")
    if not cookie or not header or not hmac.compare_digest(cookie,header): raise HTTPException(403,"CSRF validation failed")
    if origin not in settings.origins: raise HTTPException(403,"Origin is not allowed")

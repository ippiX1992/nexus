import json
import logging
import re
import time
from contextvars import ContextVar
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.config import get_settings

correlation_id_var: ContextVar[UUID | None] = ContextVar("correlation_id", default=None)
logger = logging.getLogger("nexus.http")
_safe_id = re.compile(r"^[0-9a-fA-F-]{36}$")


def correlation_id_from_header(value: str | None) -> UUID:
    if value is None:
        return uuid4()
    if len(value) > 64 or not _safe_id.fullmatch(value):
        raise ValueError("X-Correlation-ID must be a UUID")
    return UUID(value)


async def correlation_and_logging_middleware(request: Request, call_next):
    try:
        correlation_id = correlation_id_from_header(request.headers.get("x-correlation-id"))
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)
    token = correlation_id_var.set(correlation_id)
    request.state.correlation_id = correlation_id
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Correlation-ID"] = str(correlation_id)
        return response
    finally:
        route = request.scope.get("route")
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": "info" if status < 500 else "error",
            "service": get_settings().app_name,
            "environment": get_settings().environment,
            "correlation_id": str(correlation_id),
            "method": request.method,
            "endpoint": request.url.path,
            "status": status,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "operation": getattr(route, "name", None),
        }
        logger.info(json.dumps(entry, separators=(",", ":")))
        correlation_id_var.reset(token)

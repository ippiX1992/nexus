import base64
import json
import re
import unicodedata
from datetime import datetime
from uuid import UUID

from app.modules.platform.domain.values import normalize_code, validate_locale

IDENTIFIER_TYPES = frozenset({"ean", "upc", "isbn", "mpn", "external"})
_SKU_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def normalized_code(value: str) -> str:
    return normalize_code(value)


def normalize_sku(value: str) -> tuple[str, str]:
    display = unicodedata.normalize("NFKC", value).strip()
    if not display or len(display) > 160 or _SKU_CONTROL.search(display):
        raise ValueError("SKU must contain 1 to 160 printable characters")
    return display, display.casefold()


def normalize_slug(value: str) -> str:
    return normalize_code(value)


def normalize_locale(value: str) -> str:
    return validate_locale(value)


def normalize_identifier(identifier_type: str, value: str, source_system: str | None) -> tuple[str, str | None]:
    kind = identifier_type.strip().casefold()
    if kind not in IDENTIFIER_TYPES:
        raise ValueError("Unsupported product identifier type")
    raw = unicodedata.normalize("NFKC", value).strip()
    if not raw or len(raw) > 255:
        raise ValueError("Identifier value must contain 1 to 255 characters")
    source = normalize_code(source_system) if source_system else None
    if kind == "external" and source is None:
        raise ValueError("External identifiers require source_system")
    if kind in {"ean", "upc"}:
        normalized = re.sub(r"[\s-]", "", raw)
        allowed = {"ean": {8, 13, 14}, "upc": {8, 12}}[kind]
        if not normalized.isdigit() or len(normalized) not in allowed:
            raise ValueError(f"Invalid {kind.upper()} identifier")
    elif kind == "isbn":
        normalized = re.sub(r"[\s-]", "", raw).upper()
        if not ((len(normalized) == 10 and normalized[:-1].isdigit() and (normalized[-1].isdigit() or normalized[-1] == "X")) or (len(normalized) == 13 and normalized.isdigit())):
            raise ValueError("Invalid ISBN identifier")
    else:
        normalized = raw.casefold()
    return normalized, source


def encode_cursor(created_at: datetime, resource_id: UUID) -> str:
    payload = json.dumps({"v": 1, "created_at": created_at.isoformat(), "id": str(resource_id)}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def decode_cursor(value: str) -> tuple[datetime, UUID]:
    try:
        padded = value + "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        if payload.get("v") != 1:
            raise ValueError
        return datetime.fromisoformat(payload["created_at"]), UUID(payload["id"])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid catalog cursor") from exc

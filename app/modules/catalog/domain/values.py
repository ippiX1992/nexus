import base64
import hashlib
import json
import re
import unicodedata
from datetime import datetime
from uuid import UUID

from app.modules.platform.domain.values import normalize_code, validate_locale

IDENTIFIER_TYPES = frozenset({"ean", "upc", "isbn", "mpn", "external"})
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_SLUG_SEPARATOR = re.compile(r"[\s_]+")
_SLUG_HYPHENS = re.compile(r"-+")
_SKU_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def normalized_code(value: str) -> str:
    return normalize_code(value)


def normalize_sku(value: str) -> tuple[str, str]:
    display = unicodedata.normalize("NFKC", value).strip()
    if not display or len(display) > 160 or _SKU_CONTROL.search(display):
        raise ValueError("SKU must contain 1 to 160 printable characters")
    return display, display.casefold()


def normalize_slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    normalized = _SLUG_SEPARATOR.sub("-", normalized)
    normalized = _SLUG_HYPHENS.sub("-", normalized).strip("-")
    if not normalized or len(normalized) > 200:
        raise ValueError("Slug must contain 1 to 200 characters")
    if any(not (character.isalnum() or character == "-") for character in normalized):
        raise ValueError("Slug must be alphanumeric with hyphens")
    return normalized


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


def normalize_swatch_hex(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not _HEX_COLOR.match(normalized):
        raise ValueError("swatch_hex must be a #RRGGBB hex color")
    return normalized.upper()


def derive_variant_sku(base: str, value_codes: list[str]) -> tuple[str, str]:
    """Deterministic SKU for a generated combination: BASE-CODE1-CODE2 (sorted).

    Sorted so the same combination always derives the same candidate SKU
    regardless of the order values were selected in. Collisions (another
    Variant already owns this exact SKU) are the caller's responsibility to
    detect and disambiguate -- this function is pure and does not touch the
    database.
    """
    suffix = "-".join(sorted(code.strip().upper() for code in value_codes))
    candidate = f"{base.strip().upper()}-{suffix}" if suffix else base.strip().upper()
    return normalize_sku(candidate)


def combination_fingerprint(pairs: list[tuple[UUID, UUID]]) -> str | None:
    """SHA-256 over `option_id:value_id` pairs sorted by option_id, `|`-joined.

    Never fed names, slugs, or positions -- only stable UUIDs. Returns None
    (not the hash of an empty string) when there are no pairs, so a simple
    product without Options never collides with another one at the unique
    index level (NULL is excluded from the partial unique index by design).
    """
    if not pairs:
        return None
    ordered = sorted(pairs, key=lambda pair: str(pair[0]))
    canonical = "|".join(f"{option_id}:{value_id}" for option_id, value_id in ordered)
    return hashlib.sha256(canonical.encode()).hexdigest()

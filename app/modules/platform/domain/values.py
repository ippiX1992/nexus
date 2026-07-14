from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from babel import Locale, UnknownLocaleError
from babel.numbers import get_currency_precision, get_territory_currencies


class StoreStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


class ResourceStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class SiteType(StrEnum):
    COMMERCE = "commerce"
    CONTENT = "content"
    LANDING = "landing"
    PORTAL = "portal"


class ChannelType(StrEnum):
    WEB = "web"
    MOBILE = "mobile"
    MARKETPLACE = "marketplace"
    B2B = "b2b"
    SOCIAL = "social"
    POS = "pos"
    API = "api"


class EnvironmentType(StrEnum):
    DEVELOPMENT = "development"
    PREVIEW = "preview"
    STAGING = "staging"
    PRODUCTION = "production"


class ScopeType(StrEnum):
    TENANT = "tenant"
    STORE = "store"
    SITE = "site"
    CHANNEL = "channel"
    ENVIRONMENT = "environment"
    MARKET = "market"


def normalize_code(value: str) -> str:
    normalized = value.strip().casefold().replace("_", "-")
    if not normalized or len(normalized) > 64 or not normalized[0].isalnum():
        raise ValueError("Invalid resource code")
    if any(not (char.isalnum() or char == "-") for char in normalized):
        raise ValueError("Resource code must be alphanumeric with hyphens")
    return normalized


def validate_locale(value: str) -> str:
    candidate = value.strip().replace("_", "-")
    try:
        parsed = Locale.parse(candidate, sep="-")
    except (UnknownLocaleError, ValueError) as exc:
        raise ValueError("Locale must be a registered BCP 47 language tag") from exc
    language = parsed.language.lower()
    territory = f"-{parsed.territory.upper()}" if parsed.territory else ""
    script = f"-{parsed.script.title()}" if parsed.script else ""
    return f"{language}{script}{territory}"


def validate_country(value: str) -> str:
    code = value.strip().upper()
    if len(code) != 2 or not get_territory_currencies(code, tender=True):
        raise ValueError("Country must be an ISO 3166-1 alpha-2 code")
    return code


def validate_currency(value: str) -> tuple[str, int]:
    code = value.strip().upper()
    try:
        precision = get_currency_precision(code)
    except (KeyError, ValueError) as exc:
        raise ValueError("Currency must be an ISO 4217 code") from exc
    if len(code) != 3 or precision < 0:
        raise ValueError("Currency must be an ISO 4217 code")
    return code, precision


def validate_timezone(value: str) -> str:
    candidate = value.strip()
    try:
        ZoneInfo(candidate)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Timezone must be an IANA identifier") from exc
    return candidate


@dataclass(frozen=True, slots=True)
class MoneyConfiguration:
    currency_code: str
    minor_unit: int
    rounding_mode: str = "ROUND_HALF_EVEN"

    @classmethod
    def from_currency(cls, value: str) -> "MoneyConfiguration":
        code, precision = validate_currency(value)
        return cls(code, precision)

    def quantizer(self) -> Decimal:
        return Decimal(1).scaleb(-self.minor_unit)

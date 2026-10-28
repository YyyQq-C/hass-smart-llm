"""Cursor user-API-key lifetime stored on the config entry.

``CreateUserApiKey`` takes an optional ``expires_at`` (proto field 3, JSON
``expiresAt``). The Cursor SDK's mint step omits that field for a key that
never expires. The response only returns the key, so the expiry (or
``never``) is stored here from the lifetime the user chose.

A stored key with neither ``api_key_ttl=never`` nor ``api_key_expires_at``
is unknown. Older entries are not treated as expired.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .const import (
    API_KEY_EXPIRY_LEAD_MS,
    API_KEY_TTL_CHOICES,
    API_KEY_TTL_DAYS,
    API_KEY_TTL_NEVER,
    CONF_API_KEY_ENCRYPTED,
    CONF_API_KEY_EXPIRES_AT,
    CONF_API_KEY_TTL,
)

EXPIRY_ABSENT = "absent"
EXPIRY_UNKNOWN = "unknown"
EXPIRY_NEVER = "never"
EXPIRY_VALID = "valid"
EXPIRY_SOON = "soon"
EXPIRY_EXPIRED = "expired"

_NOTICE_STATES = frozenset({EXPIRY_SOON, EXPIRY_EXPIRED})


@dataclass(frozen=True, slots=True)
class KeyExpiry:
    """Classification of one config entry's stored Cursor key."""

    state: str
    expires_at_ms: int | None


def ttl_to_milliseconds(ttl: str) -> int | None:
    """Return a lifetime in milliseconds, or None when the key never expires."""
    if ttl == API_KEY_TTL_NEVER:
        return None
    try:
        days = API_KEY_TTL_DAYS[ttl]
    except KeyError as err:
        raise ValueError(f"Unsupported API key lifetime: {ttl}") from err
    return days * 24 * 60 * 60 * 1000


def normalize_ttl(value: object) -> str | None:
    """Return a supported lifetime choice, or None."""
    if isinstance(value, str) and value in API_KEY_TTL_CHOICES:
        return value
    return None


def classify_key_expiry(data: Mapping[str, Any], now_ms: int) -> KeyExpiry:
    """Classify a config-entry data dict. ``now_ms`` is epoch milliseconds."""
    if not data.get(CONF_API_KEY_ENCRYPTED):
        return KeyExpiry(EXPIRY_ABSENT, None)
    if data.get(CONF_API_KEY_TTL) == API_KEY_TTL_NEVER:
        return KeyExpiry(EXPIRY_NEVER, None)
    expires = _expires_at_ms(data.get(CONF_API_KEY_EXPIRES_AT))
    if expires is None:
        return KeyExpiry(EXPIRY_UNKNOWN, None)
    if now_ms >= expires:
        return KeyExpiry(EXPIRY_EXPIRED, expires)
    if expires - now_ms <= API_KEY_EXPIRY_LEAD_MS:
        return KeyExpiry(EXPIRY_SOON, expires)
    return KeyExpiry(EXPIRY_VALID, expires)


def notice_action(previous: str | None, state: str) -> str:
    """Decide whether to publish, replace, or dismiss the expiry notice.

    ``soon`` and ``expired`` publish that stage. The same stage again is
    ``keep``, so a usage poll does not create another notification.
    ``clear`` dismisses a notice. The first check after startup
    (``previous is None``) still clears, which drops a stale issue when the
    key is no longer in a warning stage.
    """
    if state in _NOTICE_STATES:
        if previous == state:
            return "keep"
        return state
    if previous is None or previous != "clear":
        return "clear"
    return "keep"


def stored_expiry_fields(
    ttl: str | None, expires_at_ms: int | None
) -> dict[str, Any]:
    """Entry fields for a mint. Permanent keys omit ``api_key_expires_at``."""
    fields: dict[str, Any] = {}
    if ttl in API_KEY_TTL_CHOICES:
        fields[CONF_API_KEY_TTL] = ttl
    if ttl == API_KEY_TTL_NEVER:
        return fields
    expires = _expires_at_ms(expires_at_ms)
    if expires is not None:
        fields[CONF_API_KEY_EXPIRES_AT] = expires
    return fields


def format_expiry_clock(expires_at_ms: int, *, time_zone: str | None = None) -> str:
    """Format an epoch-ms expiry for notices. UTC is labeled when the zone is UTC."""
    moment = datetime.fromtimestamp(expires_at_ms / 1000, tz=timezone.utc)
    if time_zone:
        try:
            moment = moment.astimezone(ZoneInfo(time_zone))
        except (ZoneInfoNotFoundError, ValueError, OSError):
            pass
    offset = moment.utcoffset()
    if offset is None or offset.total_seconds() == 0:
        return moment.strftime("%Y-%m-%d %H:%M UTC")
    return moment.strftime("%Y-%m-%d %H:%M")


def expiry_label(status: KeyExpiry, when_text: str | None, *, language: str) -> str:
    """Short options-flow label. ``when_text`` is a formatted expiry."""
    lang = "zh" if language.lower().startswith("zh") else "en"
    labels = {
        "en": {
            EXPIRY_NEVER: "Permanent",
            EXPIRY_UNKNOWN: "Unknown",
            EXPIRY_ABSENT: "—",
            EXPIRY_EXPIRED: "Expired {when}",
            EXPIRY_SOON: "Expires {when}",
            EXPIRY_VALID: "{when}",
        },
        "zh": {
            EXPIRY_NEVER: "永久",
            EXPIRY_UNKNOWN: "未知",
            EXPIRY_ABSENT: "—",
            EXPIRY_EXPIRED: "已过期 {when}",
            EXPIRY_SOON: "即将到期 {when}",
            EXPIRY_VALID: "{when}",
        },
    }[lang]
    template = labels[status.state]
    if "{when}" not in template:
        return template
    if not when_text:
        return labels[EXPIRY_UNKNOWN]
    return template.format(when=when_text)


def expired_hint(language: str) -> str:
    """Unavailable-state hint for allowance sensors and Assist."""
    if language.lower().startswith("zh"):
        return "Cursor API 密钥已过期。请在 Smart LLM 选项里重新授权。"
    return "Cursor API key expired. Re-authorize in the Smart LLM options."


def _expires_at_ms(raw: object) -> int | None:
    """Return a positive epoch-ms timestamp, or None when it is not one."""
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    expires = int(raw)
    if expires <= 0:
        return None
    return expires

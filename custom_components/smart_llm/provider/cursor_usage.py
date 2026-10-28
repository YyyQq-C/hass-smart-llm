"""Cursor billing-period usage.

Cursor Bridge does not expose subscription quota. Its routes are chat,
messages, and models. The dashboard pages on cursor.com need a browser
session cookie, which this integration does not store.

The stored user API key can be exchanged for a short-lived access token
(``POST /auth/exchange_user_api_key``). That token calls
``DashboardService/GetCurrentPeriodUsage``, the same unofficial Connect API
the login flow already uses to mint a key. The access token stays in memory.
It is not written to the config entry and is not logged.

``planUsage`` amounts are US cents, as returned by Cursor (7000 cents is
70.00 USD). Percent fields are copied unchanged. Missing fields stay
``None``; this module does not fill them in.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from ..const import (
    CURSOR_API_BASE_URL,
    CURSOR_EXCHANGE_API_KEY_PATH,
    CURSOR_PERIOD_USAGE_PATH,
)
from .errors import ProviderAPIError, ProviderAuthError
from .http_util import error_message, read_body, redact_secret

_TIMEOUT = ClientTimeout(total=30)
# Observed access tokens last about an hour. Refresh five minutes early.
# When the token has no ``exp`` claim, keep it for 50 minutes.
_TOKEN_SKEW_SECONDS = 300
_TOKEN_FALLBACK_TTL_SECONDS = 50 * 60
# Unix milliseconds from 2000-01-01 through 2100-01-01.
_MIN_UNIX_MS = 946684800000
_MAX_UNIX_MS = 4102444800000


@dataclass(slots=True)
class AccessTokenCache:
    """In-memory access token. ``repr`` does not include the token."""

    token: str | None = None
    expires_at: float = 0.0
    key_id: str = ""

    def clear(self) -> None:
        """Drop the cached token after Cursor rejects it."""
        self.token = None
        self.expires_at = 0.0

    def __repr__(self) -> str:
        return f"AccessTokenCache(present={bool(self.token)})"


@dataclass(frozen=True, slots=True)
class CursorPeriodUsage:
    """Fields copied from ``GetCurrentPeriodUsage``. Absent fields are ``None``."""

    remaining_cents: float | None
    limit_cents: float | None
    total_spend_cents: float | None
    included_spend_cents: float | None
    total_percent_used: float | None
    auto_percent_used: float | None
    api_percent_used: float | None
    billing_cycle_start: datetime | None
    billing_cycle_end: datetime | None
    display_message: str | None

    @property
    def remaining_usd(self) -> float | None:
        """Included allowance still left, in USD. Cursor reports cents."""
        if self.remaining_cents is None:
            return None
        return self.remaining_cents / 100.0

    @property
    def limit_usd(self) -> float | None:
        """Included allowance for the period, in USD."""
        if self.limit_cents is None:
            return None
        return self.limit_cents / 100.0


def usage_diagnostics(usage: CursorPeriodUsage | None) -> dict[str, Any] | None:
    """Public usage fields for diagnostics. No tokens and no API key."""
    if usage is None:
        return None
    return {
        "remaining_cents": usage.remaining_cents,
        "limit_cents": usage.limit_cents,
        "total_spend_cents": usage.total_spend_cents,
        "included_spend_cents": usage.included_spend_cents,
        "total_percent_used": usage.total_percent_used,
        "auto_percent_used": usage.auto_percent_used,
        "api_percent_used": usage.api_percent_used,
        "billing_cycle_start": _iso(usage.billing_cycle_start),
        "billing_cycle_end": _iso(usage.billing_cycle_end),
        "display_message": usage.display_message,
    }


def parse_period_usage(payload: Any) -> CursorPeriodUsage:
    """Copy known fields. Unknown or malformed values become ``None``."""
    if not isinstance(payload, dict):
        raise ProviderAPIError("Cursor usage response was unreadable")
    plan = _mapping(_first(payload, "planUsage", "plan_usage"))
    return CursorPeriodUsage(
        remaining_cents=_number(_first(plan, "remaining")),
        limit_cents=_number(_first(plan, "limit")),
        total_spend_cents=_number(_first(plan, "totalSpend", "total_spend")),
        included_spend_cents=_number(
            _first(plan, "includedSpend", "included_spend")
        ),
        total_percent_used=_number(
            _first(plan, "totalPercentUsed", "total_percent_used")
        ),
        auto_percent_used=_number(
            _first(plan, "autoPercentUsed", "auto_percent_used")
        ),
        api_percent_used=_number(_first(plan, "apiPercentUsed", "api_percent_used")),
        billing_cycle_start=_millis(
            _first(payload, "billingCycleStart", "billing_cycle_start")
        ),
        billing_cycle_end=_millis(
            _first(payload, "billingCycleEnd", "billing_cycle_end")
        ),
        display_message=_text(_first(payload, "displayMessage", "display_message")),
    )


async def async_fetch_cursor_period_usage(
    session: ClientSession,
    api_key: str,
    *,
    cache: AccessTokenCache | None = None,
    api_base_url: str = CURSOR_API_BASE_URL,
) -> CursorPeriodUsage:
    """Exchange the user API key, then read the current billing period.

    A rejected token is exchanged once more. The key and the token are
    removed from any error text.
    """
    key = api_key.strip() if isinstance(api_key, str) else ""
    if not key:
        raise ProviderAuthError("Cursor API key is empty", status=None)
    token = await _access_token(session, key, cache, api_base_url, force=False)
    try:
        return await _period_usage(session, token, key, api_base_url)
    except ProviderAuthError:
        if cache is not None:
            cache.clear()
        token = await _access_token(session, key, cache, api_base_url, force=True)
        return await _period_usage(session, token, key, api_base_url)


async def _access_token(
    session: ClientSession,
    api_key: str,
    cache: AccessTokenCache | None,
    api_base_url: str,
    *,
    force: bool,
) -> str:
    key_id = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]
    now = time.time()
    if (
        not force
        and cache is not None
        and cache.token
        and cache.key_id == key_id
        and cache.expires_at - _TOKEN_SKEW_SECONDS > now
    ):
        return cache.token
    payload = await _post_json(
        session,
        f"{api_base_url.rstrip('/')}{CURSOR_EXCHANGE_API_KEY_PATH}",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        secrets=(api_key,),
        service="Cursor",
    )
    token = payload.get("accessToken")
    if not isinstance(token, str) or not token.strip():
        token = payload.get("access_token")
    if not isinstance(token, str) or not token.strip():
        raise ProviderAuthError("Cursor did not return an access token", status=None)
    token = token.strip()
    if cache is not None:
        expires = _jwt_expiry(token)
        cache.token = token
        cache.key_id = key_id
        cache.expires_at = (
            expires if expires is not None else now + _TOKEN_FALLBACK_TTL_SECONDS
        )
    return token


async def _period_usage(
    session: ClientSession,
    access_token: str,
    api_key: str,
    api_base_url: str,
) -> CursorPeriodUsage:
    payload = await _post_json(
        session,
        f"{api_base_url.rstrip('/')}{CURSOR_PERIOD_USAGE_PATH}",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Connect-Protocol-Version": "1",
        },
        secrets=(api_key, access_token),
        service="Cursor usage",
    )
    return parse_period_usage(payload)


async def _post_json(
    session: ClientSession,
    url: str,
    *,
    headers: dict[str, str],
    secrets: tuple[str, ...],
    service: str,
) -> dict[str, Any]:
    try:
        async with session.post(
            url,
            json={},
            headers=headers,
            timeout=_TIMEOUT,
        ) as response:
            payload = await read_body(response)
            status = response.status
    except TimeoutError as err:
        raise ProviderAPIError(f"{service} timed out", status=None) from err
    except ClientError as err:
        raise ProviderAPIError(f"Could not reach {service}", status=None) from err

    if status in {401, 403}:
        raise ProviderAuthError(f"{service} rejected the API key", status=status)
    if status >= 400:
        raise ProviderAPIError(
            _redact(error_message(payload, status), secrets),
            status=status,
        )
    if not isinstance(payload, dict):
        raise ProviderAPIError(f"{service} returned an unreadable response")
    # A 200 body can still be an error envelope. Do not treat that as a
    # period with every field missing.
    code = payload.get("code")
    if (
        service == "Cursor usage"
        and isinstance(code, str)
        and code
        and "planUsage" not in payload
        and "plan_usage" not in payload
    ):
        raise ProviderAPIError(
            _redact(f"{service} was rejected", secrets),
            status=status,
        )
    return payload


def _redact(message: str, secrets: tuple[str, ...]) -> str:
    cleaned = message
    for secret in secrets:
        cleaned = redact_secret(cleaned, secret)
    return cleaned


def _jwt_expiry(token: str) -> float | None:
    """Read ``exp`` from the token payload. The signature is not checked."""
    parts = token.split(".")
    if len(parts) < 2:
        return None
    try:
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(raw)
    except (ValueError, json.JSONDecodeError, UnicodeError):
        return None
    if not isinstance(payload, dict):
        return None
    exp = payload.get("exp")
    if isinstance(exp, bool) or not isinstance(exp, (int, float)):
        return None
    return float(exp)


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _first(data: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in data:
            return data[name]
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number):
            return None
        return number
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _millis(value: Any) -> datetime | None:
    if isinstance(value, str) and "T" in value:
        text = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    number = _number(value)
    if number is None or number < _MIN_UNIX_MS or number > _MAX_UNIX_MS:
        return None
    return datetime.fromtimestamp(number / 1000.0, tz=timezone.utc)


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    return text[:500]


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()

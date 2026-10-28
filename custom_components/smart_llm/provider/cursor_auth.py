"""Cursor browser login, matching the TypeScript SDK handshake.

Flow (``@cursor/sdk`` ``login-flow.ts`` / ``Cursor.auth.login``):

1. Generate a PKCE verifier and ``challenge = base64url(sha256(verifier))``.
2. Send the browser to ``{website}/loginDeepControl`` with the challenge, a
   one-time uuid, ``mode=login`` and ``redirectTarget=sdk``. The verifier is
   not part of that URL.
3. Poll ``POST /auth/poll`` with ``{uuid, verifier}`` in the JSON body. A 404
   whose body is exactly ``Not found`` means the user has not finished yet.
   A route-not-found 404 falls back once to ``GET /auth/poll``, which is the
   older endpoint and does put the verifier in the query string.
4. Use the short-lived access token once, to call
   ``DashboardService/CreateUserApiKey``, then discard it. Optionally read the
   account email from ``GetMe``. The minted user API key is the only
   credential the integration stores.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import secrets
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from aiohttp import ClientError, ClientSession, ClientTimeout

from ..const import (
    API_KEY_NAME,
    API_KEY_TTL_MS,
    CURSOR_API_BASE_URL,
    CURSOR_CREATE_API_KEY_PATH,
    CURSOR_GET_ME_PATH,
    CURSOR_LOGIN_PATH,
    CURSOR_POLL_PATH,
    CURSOR_WEBSITE_URL,
    POLL_BACKOFF,
    POLL_BASE_DELAY_MS,
    POLL_MAX_ATTEMPTS,
    POLL_MAX_DELAY_MS,
)
from .errors import CursorLoginError
from .http_util import read_body

_POLL_TIMEOUT = ClientTimeout(total=20)
_MINT_TIMEOUT = ClientTimeout(total=30)
_PENDING_BODY = "Not found"


@dataclass(frozen=True, slots=True)
class LoginHandshake:
    """One browser login. Only this process can redeem ``verifier``."""

    uuid: str
    verifier: str
    login_url: str


@dataclass(frozen=True, slots=True)
class LoginTokens:
    """Session tokens released by ``/auth/poll``. Not persisted."""

    access_token: str
    refresh_token: str


@dataclass(frozen=True, slots=True)
class LoginResult:
    """Minted user API key plus optional account email."""

    api_key: str
    email: str | None
    expires_at_ms: int


def strip_trailing_slashes(url: str) -> str:
    """Drop trailing slashes without touching the scheme."""
    return url.rstrip("/")


def create_login_handshake(website_url: str = CURSOR_WEBSITE_URL) -> LoginHandshake:
    """Build a PKCE handshake and the portal URL the user should open."""
    verifier = _base64url(secrets.token_bytes(32))
    challenge = _base64url(hashlib.sha256(verifier.encode("ascii")).digest())
    login_id = str(uuid.uuid4())
    query = urlencode(
        {
            "challenge": challenge,
            "uuid": login_id,
            "mode": "login",
            "redirectTarget": "sdk",
        }
    )
    login_url = f"{strip_trailing_slashes(website_url)}{CURSOR_LOGIN_PATH}?{query}"
    return LoginHandshake(uuid=login_id, verifier=verifier, login_url=login_url)


async def async_login_and_mint(
    session: ClientSession,
    handshake: LoginHandshake,
    *,
    api_base_url: str = CURSOR_API_BASE_URL,
    key_name: str = API_KEY_NAME,
    ttl_ms: int = API_KEY_TTL_MS,
    max_attempts: int = POLL_MAX_ATTEMPTS,
    base_delay_ms: int = POLL_BASE_DELAY_MS,
    max_delay_ms: int = POLL_MAX_DELAY_MS,
    on_get_fallback: Callable[[str], None] | None = None,
) -> LoginResult:
    """Poll until the browser login completes, then mint a user API key."""
    if ttl_ms <= 0:
        raise CursorLoginError(
            "unknown", "API key lifetime must be a positive number of milliseconds"
        )
    tokens = await poll_for_tokens(
        session,
        api_base_url=api_base_url,
        login_id=handshake.uuid,
        verifier=handshake.verifier,
        max_attempts=max_attempts,
        base_delay_ms=base_delay_ms,
        max_delay_ms=max_delay_ms,
        on_get_fallback=on_get_fallback,
    )
    expires_at_ms = int(time.time() * 1000) + ttl_ms
    return await mint_user_api_key(
        session,
        api_base_url=api_base_url,
        access_token=tokens.access_token,
        name=key_name,
        expires_at_ms=expires_at_ms,
    )


async def poll_for_tokens(
    session: ClientSession,
    *,
    api_base_url: str,
    login_id: str,
    verifier: str,
    max_attempts: int = POLL_MAX_ATTEMPTS,
    base_delay_ms: int = POLL_BASE_DELAY_MS,
    max_delay_ms: int = POLL_MAX_DELAY_MS,
    on_get_fallback: Callable[[str], None] | None = None,
) -> LoginTokens:
    """Poll ``/auth/poll`` until the backend releases session tokens."""
    api_base = strip_trailing_slashes(api_base_url)
    use_get = False
    classified_pending = False
    consecutive_errors = 0
    saw_pending = False

    for attempt in range(max_attempts):
        try:
            if use_get:
                url = (
                    f"{api_base}{CURSOR_POLL_PATH}?uuid={_quote(login_id)}"
                    f"&verifier={_quote(verifier)}"
                )
                response_cm = session.get(
                    url,
                    headers={"Accept": "application/json"},
                    timeout=_POLL_TIMEOUT,
                )
            else:
                response_cm = session.post(
                    f"{api_base}{CURSOR_POLL_PATH}",
                    json={"uuid": login_id, "verifier": verifier},
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                    timeout=_POLL_TIMEOUT,
                )
            async with response_cm as response:
                if response.status == 404:
                    if not classified_pending:
                        body = (await response.text()).strip()
                        if not use_get and body != _PENDING_BODY:
                            use_get = True
                            if on_get_fallback is not None:
                                on_get_fallback(
                                    f"{api_base} has no POST /auth/poll; "
                                    "falling back to GET"
                                )
                            continue
                        if use_get and _is_route_not_found(body):
                            raise CursorLoginError(
                                "cannot_connect",
                                "Cursor auth poll endpoint is not available",
                            )
                        classified_pending = True
                    consecutive_errors = 0
                    saw_pending = True
                elif response.status >= 400:
                    consecutive_errors += 1
                    if consecutive_errors >= 3:
                        raise CursorLoginError(
                            "cannot_connect",
                            f"Cursor auth poll failed with HTTP {response.status}",
                        )
                else:
                    payload = await read_body(response)
                    tokens = _tokens_from_payload(payload)
                    if tokens is None:
                        raise CursorLoginError(
                            "invalid_auth",
                            "Cursor login response did not include session tokens",
                        )
                    return tokens
        except asyncio.CancelledError:
            raise
        except CursorLoginError:
            raise
        except (ClientError, TimeoutError):
            consecutive_errors += 1
            if consecutive_errors >= 3:
                raise CursorLoginError(
                    "cannot_connect",
                    "Could not reach Cursor to finish login",
                ) from None

        await _sleep_backoff(attempt, base_delay_ms, max_delay_ms)

    if saw_pending:
        raise CursorLoginError(
            "timeout",
            "Timed out waiting for the browser login to finish",
        )
    raise CursorLoginError(
        "cannot_connect",
        "Could not reach Cursor to finish login",
    )


async def mint_user_api_key(
    session: ClientSession,
    *,
    api_base_url: str,
    access_token: str,
    name: str,
    expires_at_ms: int,
) -> LoginResult:
    """Exchange a browser-login access token for a named user API key."""
    api_base = strip_trailing_slashes(api_base_url)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Connect-Protocol-Version": "1",
    }
    # proto3 JSON encodes int64 as a string.
    body = {"name": name, "expiresAt": str(int(expires_at_ms))}
    try:
        async with session.post(
            f"{api_base}{CURSOR_CREATE_API_KEY_PATH}",
            json=body,
            headers=headers,
            timeout=_MINT_TIMEOUT,
        ) as response:
            payload = await read_body(response)
            status = response.status
    except asyncio.CancelledError:
        raise
    except (ClientError, TimeoutError) as err:
        raise CursorLoginError(
            "cannot_connect",
            "Could not reach Cursor to create an API key",
        ) from err

    if status in {401, 403}:
        raise CursorLoginError(
            "invalid_auth",
            "Cursor rejected the login session before an API key was created",
        )
    api_key = _api_key_from_payload(payload)
    if status >= 400 or not api_key:
        raise CursorLoginError(
            "mint_failed",
            "Login succeeded, but creating a Cursor API key failed. "
            "Team settings may restrict user API keys.",
        )

    email = await _get_me(session, api_base, headers)
    return LoginResult(api_key=api_key, email=email, expires_at_ms=int(expires_at_ms))


async def _get_me(
    session: ClientSession, api_base: str, headers: dict[str, str]
) -> str | None:
    """Best-effort account email. A failure here does not fail login."""
    try:
        async with session.post(
            f"{api_base}{CURSOR_GET_ME_PATH}",
            json={},
            headers=headers,
            timeout=_MINT_TIMEOUT,
        ) as response:
            if response.status >= 400:
                return None
            payload = await read_body(response)
    except asyncio.CancelledError:
        raise
    except (ClientError, TimeoutError):
        return None
    if not isinstance(payload, dict):
        return None
    email = payload.get("email")
    if isinstance(email, str) and email.strip():
        return email.strip()
    return None


def _tokens_from_payload(payload: Any) -> LoginTokens | None:
    if not isinstance(payload, dict):
        return None
    access = payload.get("accessToken")
    refresh = payload.get("refreshToken")
    if not isinstance(access, str) or not isinstance(refresh, str):
        return None
    if not access or not refresh:
        return None
    return LoginTokens(access_token=access, refresh_token=refresh)


def _api_key_from_payload(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    api_key = payload.get("apiKey")
    if not isinstance(api_key, str):
        api_key = payload.get("api_key")
    if isinstance(api_key, str) and api_key:
        return api_key
    return None


def _is_route_not_found(body: str) -> bool:
    if not body.startswith("{"):
        return False
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return False
    message = payload.get("message") if isinstance(payload, dict) else None
    return (
        isinstance(message, str)
        and message.startswith("Route ")
        and "not found" in message
    )


def _base64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _quote(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")


async def _sleep_backoff(attempt: int, base_delay_ms: int, max_delay_ms: int) -> None:
    delay_ms = min(base_delay_ms * (POLL_BACKOFF**attempt), max_delay_ms)
    if delay_ms > 0:
        await asyncio.sleep(delay_ms / 1000)

"""Cursor browser-login client, against a local mock of the SDK endpoints."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import time
from urllib.parse import parse_qs, urlsplit

from aiohttp import ClientSession, web
from aiohttp.test_utils import TestServer

from custom_components.smart_llm.const import API_KEY_NAME
from custom_components.smart_llm.provider.cursor_auth import (
    async_login_and_mint,
    create_login_handshake,
    mint_user_api_key,
    poll_for_tokens,
)
from custom_components.smart_llm.provider.errors import CursorLoginError


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def test_handshake_matches_sdk_pkce() -> None:
    """The portal URL carries the challenge, never the verifier."""
    handshake = create_login_handshake("https://cursor.com/")
    parts = urlsplit(handshake.login_url)
    query = parse_qs(parts.query)

    assert parts.scheme == "https"
    assert parts.netloc == "cursor.com"
    assert parts.path == "/loginDeepControl"
    assert query["uuid"] == [handshake.uuid]
    assert query["mode"] == ["login"]
    assert query["redirectTarget"] == ["sdk"]
    assert query["challenge"] == [_challenge(handshake.verifier)]
    assert handshake.verifier not in handshake.login_url
    assert "verifier" not in handshake.login_url


def test_poll_posts_verifier_and_treats_not_found_as_pending() -> None:
    """Pending login is POST /auth/poll. The verifier stays out of the URL."""

    async def scenario() -> None:
        seen: list[tuple[str, str, dict | None]] = []

        async def poll(request: web.Request) -> web.Response:
            body = await request.json() if request.method == "POST" else None
            seen.append((request.method, request.path_qs, body))
            if len(seen) < 3:
                return web.Response(status=404, text="Not found")
            return web.json_response(
                {"accessToken": "access-token", "refreshToken": "refresh-token"}
            )

        app = web.Application()
        app.router.add_post("/auth/poll", poll)
        app.router.add_get("/auth/poll", poll)
        async with _server(app) as base:
            async with ClientSession() as session:
                tokens = await poll_for_tokens(
                    session,
                    api_base_url=base,
                    login_id="login-id",
                    verifier="verifier-secret",
                    max_attempts=5,
                    base_delay_ms=0,
                    max_delay_ms=0,
                )

        assert tokens.access_token == "access-token"
        assert tokens.refresh_token == "refresh-token"
        assert [item[0] for item in seen] == ["POST", "POST", "POST"]
        for method, path, body in seen:
            assert method == "POST"
            assert path == "/auth/poll"
            assert "verifier-secret" not in path
            assert body == {"uuid": "login-id", "verifier": "verifier-secret"}

    asyncio.run(scenario())


def test_poll_falls_back_to_get_when_post_route_is_missing() -> None:
    """A route-not-found 404 switches to GET once, matching the SDK."""

    async def scenario() -> None:
        warnings: list[str] = []
        seen: list[str] = []

        async def poll(request: web.Request) -> web.Response:
            seen.append(f"{request.method} {request.path_qs}")
            if request.method == "POST":
                return web.Response(
                    status=404,
                    text=json.dumps(
                        {"message": "Route POST:/auth/poll not found"}
                    ),
                    content_type="application/json",
                )
            return web.json_response(
                {"accessToken": "access-token", "refreshToken": "refresh-token"}
            )

        app = web.Application()
        app.router.add_post("/auth/poll", poll)
        app.router.add_get("/auth/poll", poll)
        async with _server(app) as base:
            async with ClientSession() as session:
                tokens = await poll_for_tokens(
                    session,
                    api_base_url=base,
                    login_id="login-id",
                    verifier="verifier-secret",
                    max_attempts=4,
                    base_delay_ms=0,
                    max_delay_ms=0,
                    on_get_fallback=warnings.append,
                )

        assert tokens.access_token == "access-token"
        assert seen[0].startswith("POST ")
        assert seen[1].startswith("GET ")
        assert "verifier-secret" in seen[1]
        assert warnings
        assert "verifier-secret" not in warnings[0]

    asyncio.run(scenario())


def test_poll_gives_up_after_repeated_http_errors() -> None:
    async def scenario() -> None:
        async def poll(_request: web.Request) -> web.Response:
            return web.Response(status=500, text="nope")

        app = web.Application()
        app.router.add_post("/auth/poll", poll)
        async with _server(app) as base:
            async with ClientSession() as session:
                try:
                    await poll_for_tokens(
                        session,
                        api_base_url=base,
                        login_id="login-id",
                        verifier="verifier-secret",
                        max_attempts=5,
                        base_delay_ms=0,
                        max_delay_ms=0,
                    )
                except CursorLoginError as err:
                    assert err.code == "cannot_connect"
                else:
                    raise AssertionError("expected login error")

    asyncio.run(scenario())


def test_poll_timeout_while_login_is_pending() -> None:
    async def scenario() -> None:
        async def poll(_request: web.Request) -> web.Response:
            return web.Response(status=404, text="Not found")

        app = web.Application()
        app.router.add_post("/auth/poll", poll)
        async with _server(app) as base:
            async with ClientSession() as session:
                try:
                    await poll_for_tokens(
                        session,
                        api_base_url=base,
                        login_id="login-id",
                        verifier="verifier-secret",
                        max_attempts=2,
                        base_delay_ms=0,
                        max_delay_ms=0,
                    )
                except CursorLoginError as err:
                    assert err.code == "timeout"
                else:
                    raise AssertionError("expected timeout")

    asyncio.run(scenario())


def test_mint_creates_user_api_key_and_discards_session_token() -> None:
    """CreateUserApiKey is a Connect JSON call. The access token is a header."""

    async def scenario() -> None:
        seen: list[dict] = []

        async def create_key(request: web.Request) -> web.Response:
            seen.append(
                {
                    "path": request.path_qs,
                    "authorization": request.headers["Authorization"],
                    "connect": request.headers["Connect-Protocol-Version"],
                    "body": await request.json(),
                }
            )
            return web.json_response({"apiKey": "crsr_minted_key_value_abcdef"})

        async def get_me(request: web.Request) -> web.Response:
            assert request.headers["Authorization"] == "Bearer access-token"
            assert "access-token" not in request.path_qs
            return web.json_response({"email": "Person@Example.com"})

        app = web.Application()
        app.router.add_post(
            "/aiserver.v1.DashboardService/CreateUserApiKey", create_key
        )
        app.router.add_post("/aiserver.v1.DashboardService/GetMe", get_me)
        async with _server(app) as base:
            async with ClientSession() as session:
                result = await mint_user_api_key(
                    session,
                    api_base_url=base,
                    access_token="access-token",
                    name=API_KEY_NAME,
                    expires_at_ms=1_700_000_000_000,
                )

        assert result.api_key == "crsr_minted_key_value_abcdef"
        assert result.email == "Person@Example.com"
        assert result.expires_at_ms == 1_700_000_000_000
        assert seen[0]["path"] == "/aiserver.v1.DashboardService/CreateUserApiKey"
        assert "access-token" not in seen[0]["path"]
        assert seen[0]["authorization"] == "Bearer access-token"
        assert seen[0]["connect"] == "1"
        assert seen[0]["body"]["name"] == API_KEY_NAME
        assert seen[0]["body"]["expiresAt"] == "1700000000000"

    asyncio.run(scenario())


def test_mint_still_returns_key_when_profile_lookup_fails() -> None:
    async def scenario() -> None:
        async def create_key(_request: web.Request) -> web.Response:
            return web.json_response({"api_key": "crsr_from_snake"})

        async def get_me(_request: web.Request) -> web.Response:
            return web.Response(status=500, text="later")

        app = web.Application()
        app.router.add_post(
            "/aiserver.v1.DashboardService/CreateUserApiKey", create_key
        )
        app.router.add_post("/aiserver.v1.DashboardService/GetMe", get_me)
        async with _server(app) as base:
            async with ClientSession() as session:
                result = await mint_user_api_key(
                    session,
                    api_base_url=base,
                    access_token="access-token",
                    name="Home Assistant Smart LLM",
                    expires_at_ms=10,
                )
        assert result.api_key == "crsr_from_snake"
        assert result.email is None

    asyncio.run(scenario())


def test_mint_reports_a_safe_error_when_the_key_is_empty() -> None:
    async def scenario() -> None:
        async def create_key(_request: web.Request) -> web.Response:
            return web.json_response({"apiKey": ""})

        app = web.Application()
        app.router.add_post(
            "/aiserver.v1.DashboardService/CreateUserApiKey", create_key
        )
        async with _server(app) as base:
            async with ClientSession() as session:
                try:
                    await mint_user_api_key(
                        session,
                        api_base_url=base,
                        access_token="access-token",
                        name="Home Assistant Smart LLM",
                        expires_at_ms=10,
                    )
                except CursorLoginError as err:
                    assert err.code == "mint_failed"
                    assert "access-token" not in str(err)
                else:
                    raise AssertionError("expected mint failure")

    asyncio.run(scenario())


def test_mint_omits_expires_at_for_a_permanent_key() -> None:
    """CreateUserApiKey treats a missing expiresAt as a key that never expires."""

    async def scenario() -> None:
        seen: list[dict] = []

        async def create_key(request: web.Request) -> web.Response:
            seen.append(await request.json())
            return web.json_response({"apiKey": "crsr_permanent_key_value"})

        async def get_me(_request: web.Request) -> web.Response:
            return web.json_response({"email": "ada@example.com"})

        app = web.Application()
        app.router.add_post(
            "/aiserver.v1.DashboardService/CreateUserApiKey", create_key
        )
        app.router.add_post("/aiserver.v1.DashboardService/GetMe", get_me)
        async with _server(app) as base:
            async with ClientSession() as session:
                result = await mint_user_api_key(
                    session,
                    api_base_url=base,
                    access_token="access-token",
                    name=API_KEY_NAME,
                    expires_at_ms=None,
                    ttl="never",
                )

        assert result.api_key == "crsr_permanent_key_value"
        assert result.expires_at_ms is None
        assert result.ttl == "never"
        assert seen[0] == {"name": API_KEY_NAME}
        assert "expiresAt" not in seen[0]

    asyncio.run(scenario())


def test_login_and_mint_permanent_choice_omits_expiry() -> None:
    async def scenario() -> None:
        seen: list[dict] = []

        async def poll(_request: web.Request) -> web.Response:
            return web.json_response(
                {"accessToken": "access-token", "refreshToken": "refresh-token"}
            )

        async def create_key(request: web.Request) -> web.Response:
            seen.append(await request.json())
            return web.json_response({"apiKey": "crsr_permanent_key_value"})

        async def get_me(_request: web.Request) -> web.Response:
            return web.json_response({})

        app = web.Application()
        app.router.add_post("/auth/poll", poll)
        app.router.add_post(
            "/aiserver.v1.DashboardService/CreateUserApiKey", create_key
        )
        app.router.add_post("/aiserver.v1.DashboardService/GetMe", get_me)
        handshake = create_login_handshake()
        async with _server(app) as base:
            async with ClientSession() as session:
                result = await async_login_and_mint(
                    session,
                    handshake,
                    api_base_url=base,
                    ttl="never",
                    max_attempts=2,
                    base_delay_ms=0,
                    max_delay_ms=0,
                )
        assert result.ttl == "never"
        assert result.expires_at_ms is None
        assert "expiresAt" not in seen[0]

    asyncio.run(scenario())


def test_login_and_mint_named_lifetime_sends_expires_at() -> None:
    async def scenario() -> None:
        seen: list[dict] = []

        async def poll(_request: web.Request) -> web.Response:
            return web.json_response(
                {"accessToken": "access-token", "refreshToken": "refresh-token"}
            )

        async def create_key(request: web.Request) -> web.Response:
            seen.append(await request.json())
            return web.json_response({"apiKey": "crsr_thirty_day_key"})

        async def get_me(_request: web.Request) -> web.Response:
            return web.Response(status=404, text="no")

        app = web.Application()
        app.router.add_post("/auth/poll", poll)
        app.router.add_post(
            "/aiserver.v1.DashboardService/CreateUserApiKey", create_key
        )
        app.router.add_post("/aiserver.v1.DashboardService/GetMe", get_me)
        handshake = create_login_handshake()
        before = int(time.time() * 1000)
        async with _server(app) as base:
            async with ClientSession() as session:
                result = await async_login_and_mint(
                    session,
                    handshake,
                    api_base_url=base,
                    ttl="30",
                    max_attempts=2,
                    base_delay_ms=0,
                    max_delay_ms=0,
                )
        after = int(time.time() * 1000)
        thirty_days = 30 * 24 * 60 * 60 * 1000
        assert result.ttl == "30"
        assert result.expires_at_ms is not None
        assert before + thirty_days <= result.expires_at_ms <= after + thirty_days
        assert seen[0]["expiresAt"] == str(result.expires_at_ms)

    asyncio.run(scenario())


def test_login_and_mint_rejects_a_non_positive_or_unknown_lifetime() -> None:
    async def scenario() -> None:
        handshake = create_login_handshake()
        async with ClientSession() as session:
            for kwargs in ({"ttl_ms": 0}, {"ttl_ms": -1}, {"ttl": "forever"}):
                try:
                    await async_login_and_mint(
                        session,
                        handshake,
                        api_base_url="http://127.0.0.1:9",
                        max_attempts=1,
                        base_delay_ms=0,
                        max_delay_ms=0,
                        **kwargs,
                    )
                except CursorLoginError as err:
                    assert err.code == "unknown"
                else:
                    raise AssertionError(f"expected login error for {kwargs}")

    asyncio.run(scenario())


def test_login_and_mint_does_not_return_session_tokens() -> None:
    async def scenario() -> None:
        async def poll(_request: web.Request) -> web.Response:
            return web.json_response(
                {"accessToken": "access-token", "refreshToken": "refresh-token"}
            )

        async def create_key(_request: web.Request) -> web.Response:
            return web.json_response({"apiKey": "crsr_minted_key_value_abcdef"})

        async def get_me(_request: web.Request) -> web.Response:
            return web.json_response({"email": "ada@example.com"})

        app = web.Application()
        app.router.add_post("/auth/poll", poll)
        app.router.add_post(
            "/aiserver.v1.DashboardService/CreateUserApiKey", create_key
        )
        app.router.add_post("/aiserver.v1.DashboardService/GetMe", get_me)
        handshake = create_login_handshake()
        async with _server(app) as base:
            async with ClientSession() as session:
                result = await async_login_and_mint(
                    session,
                    handshake,
                    api_base_url=base,
                    ttl_ms=1000,
                    max_attempts=2,
                    base_delay_ms=0,
                    max_delay_ms=0,
                )
        assert result.api_key.startswith("crsr_")
        assert result.email == "ada@example.com"
        assert not hasattr(result, "access_token")
        assert "refresh-token" not in result.api_key

    asyncio.run(scenario())


class _server:
    """Start an aiohttp app and yield its base URL."""

    def __init__(self, app: web.Application) -> None:
        self._server = TestServer(app)
        self.base = ""

    async def __aenter__(self) -> str:
        await self._server.start_server()
        self.base = str(self._server.make_url("/")).rstrip("/")
        return self.base

    async def __aexit__(self, *_exc: object) -> None:
        await self._server.close()

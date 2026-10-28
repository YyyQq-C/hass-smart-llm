"""Cursor period usage. Numbers come only from the mocked API payload."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import time

from aiohttp import ClientSession, web
from aiohttp.test_utils import TestServer

from custom_components.smart_llm.provider.cursor_usage import (
    AccessTokenCache,
    async_fetch_cursor_period_usage,
    parse_period_usage,
    usage_diagnostics,
)
from custom_components.smart_llm.provider.errors import ProviderAPIError, ProviderAuthError

API_KEY = "crsr_test_key_value_1234567890abcd"
ACCESS = "access-token-not-the-api-key"


def _jwt(exp: int) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
    payload = base64.urlsafe_b64encode(
        json.dumps({"exp": exp}).encode()
    ).decode().rstrip("=")
    return f"{header}.{payload}.sig"


def test_parse_period_usage_keeps_cents_and_ignores_missing_fields() -> None:
    usage = parse_period_usage(
        {
            "billingCycleStart": "1780000000000",
            "billingCycleEnd": "1782592000000",
            "planUsage": {
                "totalSpend": 1200,
                "includedSpend": "1200",
                "remaining": 5800,
                "limit": 7000,
                "autoPercentUsed": 10,
                "apiPercentUsed": 7.1,
                "totalPercentUsed": 17.1,
            },
            "displayMessage": "You've used 17% of your included usage",
        }
    )
    assert usage.remaining_cents == 5800
    assert usage.remaining_usd == 58.0
    assert usage.limit_usd == 70.0
    assert usage.total_percent_used == 17.1
    assert usage.billing_cycle_end is not None
    assert usage.billing_cycle_end.year >= 2026
    assert usage.display_message.startswith("You've used")
    empty = parse_period_usage({})
    assert empty.remaining_cents is None
    assert empty.remaining_usd is None
    assert empty.billing_cycle_end is None
    assert usage_diagnostics(empty)["remaining_cents"] is None
    snake = parse_period_usage(
        {
            "billing_cycle_end": "2026-12-01T00:00:00Z",
            "plan_usage": {"remaining": "0", "total_percent_used": 100},
        }
    )
    assert snake.remaining_cents == 0
    assert snake.remaining_usd == 0
    assert snake.total_percent_used == 100
    assert snake.billing_cycle_end is not None
    assert snake.billing_cycle_end.year == 2026
    assert parse_period_usage({"planUsage": {"remaining": True}}).remaining_cents is None


def test_fetch_exchanges_the_user_key_and_does_not_send_it_as_the_usage_token() -> None:
    async def scenario() -> None:
        seen: list[dict] = []
        token = _jwt(int(time.time()) + 3600)

        async def exchange(request: web.Request) -> web.Response:
            seen.append(
                {
                    "path": request.path,
                    "auth": request.headers.get("Authorization"),
                    "connect": request.headers.get("Connect-Protocol-Version"),
                    "body": await request.json(),
                }
            )
            return web.json_response({"accessToken": token, "refreshToken": "do-not-keep"})

        async def usage(request: web.Request) -> web.Response:
            seen.append(
                {
                    "path": request.path,
                    "auth": request.headers.get("Authorization"),
                    "connect": request.headers.get("Connect-Protocol-Version"),
                }
            )
            return web.json_response(
                {
                    "billingCycleEnd": "1782592000000",
                    "planUsage": {"remaining": 2500, "limit": 7000, "totalPercentUsed": 64},
                    "displayMessage": "You've used 64% of your included usage",
                }
            )

        app = web.Application()
        app.router.add_post("/auth/exchange_user_api_key", exchange)
        app.router.add_post(
            "/aiserver.v1.DashboardService/GetCurrentPeriodUsage", usage
        )
        server = TestServer(app)
        await server.start_server()
        try:
            root = str(server.make_url("/")).rstrip("/")
            cache = AccessTokenCache()
            async with ClientSession() as session:
                first = await async_fetch_cursor_period_usage(
                    session, API_KEY, cache=cache, api_base_url=root
                )
                second = await async_fetch_cursor_period_usage(
                    session, API_KEY, cache=cache, api_base_url=root
                )
        finally:
            await server.close()

        assert first.remaining_usd == 25.0
        assert first.limit_cents == 7000
        assert first.total_percent_used == 64
        assert second.remaining_cents == first.remaining_cents
        assert [item["path"] for item in seen] == [
            "/auth/exchange_user_api_key",
            "/aiserver.v1.DashboardService/GetCurrentPeriodUsage",
            "/aiserver.v1.DashboardService/GetCurrentPeriodUsage",
        ]
        assert seen[0]["auth"] == f"Bearer {API_KEY}"
        assert seen[0]["body"] == {}
        assert seen[0]["connect"] is None
        assert seen[1]["auth"] == f"Bearer {token}"
        assert seen[1]["connect"] == "1"
        assert API_KEY not in seen[1]["auth"]
        assert "refreshToken" not in repr(cache)
        assert token not in repr(cache)
        public = usage_diagnostics(first)
        assert public is not None
        assert API_KEY not in json.dumps(public)
        assert token not in json.dumps(public)

    asyncio.run(scenario())


def test_usage_auth_error_hides_the_key_and_retries_once_after_a_rejected_token() -> None:
    async def scenario() -> None:
        calls = {"exchange": 0, "usage": 0}
        token = _jwt(int(time.time()) + 3600)

        async def exchange(request: web.Request) -> web.Response:
            calls["exchange"] += 1
            if calls["exchange"] == 1:
                return web.json_response(
                    {"message": f"nope {API_KEY}"},
                    status=401,
                )
            return web.json_response({"accessToken": token})

        async def usage(request: web.Request) -> web.Response:
            calls["usage"] += 1
            if calls["usage"] == 1:
                return web.json_response(
                    {"message": f"expired {token} {API_KEY}"},
                    status=401,
                )
            return web.json_response({"planUsage": {"remaining": 1}})

        app = web.Application()
        app.router.add_post("/auth/exchange_user_api_key", exchange)
        app.router.add_post(
            "/aiserver.v1.DashboardService/GetCurrentPeriodUsage", usage
        )
        server = TestServer(app)
        await server.start_server()
        try:
            root = str(server.make_url("/")).rstrip("/")
            async with ClientSession() as session:
                try:
                    await async_fetch_cursor_period_usage(
                        session, f"  {API_KEY}  ", api_base_url=root
                    )
                except ProviderAuthError as err:
                    assert err.status == 401
                    assert API_KEY not in str(err)
                    assert token not in str(err)
                else:
                    raise AssertionError("first exchange should fail")

                cache = AccessTokenCache()
                # Prime the cache with a token Cursor will reject once.
                cache.token = "stale-token"
                cache.key_id = hashlib.sha256(API_KEY.encode()).hexdigest()[:16]
                cache.expires_at = time.time() + 3600
                usage_result = await async_fetch_cursor_period_usage(
                    session, API_KEY, cache=cache, api_base_url=root
                )
        finally:
            await server.close()

        assert usage_result.remaining_cents == 1
        assert calls["usage"] == 2
        assert calls["exchange"] == 2
        assert cache.token == token

    asyncio.run(scenario())


def test_usage_error_envelope_is_not_an_empty_period() -> None:
    async def scenario() -> None:
        async def exchange(request: web.Request) -> web.Response:
            return web.json_response({"accessToken": ACCESS})

        async def usage(request: web.Request) -> web.Response:
            return web.json_response({"code": "error", "message": f"no {API_KEY}"})

        app = web.Application()
        app.router.add_post("/auth/exchange_user_api_key", exchange)
        app.router.add_post(
            "/aiserver.v1.DashboardService/GetCurrentPeriodUsage", usage
        )
        server = TestServer(app)
        await server.start_server()
        try:
            root = str(server.make_url("/")).rstrip("/")
            async with ClientSession() as session:
                try:
                    await async_fetch_cursor_period_usage(
                        session, API_KEY, api_base_url=root
                    )
                except ProviderAPIError as err:
                    assert API_KEY not in str(err)
                else:
                    raise AssertionError("error envelope was treated as usage")
        finally:
            await server.close()

    asyncio.run(scenario())


def test_usage_error_body_does_not_keep_the_key() -> None:
    async def scenario() -> None:
        async def exchange(request: web.Request) -> web.Response:
            return web.json_response({"accessToken": ACCESS})

        async def usage(request: web.Request) -> web.Response:
            return web.json_response(
                {"error": {"message": f"overloaded {API_KEY} {ACCESS}"}},
                status=429,
            )

        app = web.Application()
        app.router.add_post("/auth/exchange_user_api_key", exchange)
        app.router.add_post(
            "/aiserver.v1.DashboardService/GetCurrentPeriodUsage", usage
        )
        server = TestServer(app)
        await server.start_server()
        try:
            root = str(server.make_url("/")).rstrip("/")
            async with ClientSession() as session:
                try:
                    await async_fetch_cursor_period_usage(
                        session, API_KEY, api_base_url=root
                    )
                except ProviderAPIError as err:
                    assert not isinstance(err, ProviderAuthError)
                    assert err.status == 429
                    assert API_KEY not in str(err)
                    assert ACCESS not in str(err)
                    assert "••••" in str(err)
                else:
                    raise AssertionError("usage error was not raised")
        finally:
            await server.close()

    asyncio.run(scenario())

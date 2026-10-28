"""Cursor Bridge client."""

from __future__ import annotations

import asyncio
import json

from aiohttp import ClientSession, web
from aiohttp.test_utils import TestServer

from custom_components.smart_llm.provider.cursor_bridge import (
    CursorBridgeClient,
    normalize_bridge_base_url,
)
from custom_components.smart_llm.provider.errors import CursorAPIError, CursorAuthError
from custom_components.smart_llm.provider.registry import create_chat_provider

API_KEY = "crsr_test_key_value_1234567890"


def test_normalize_bridge_base_url() -> None:
    assert (
        normalize_bridge_base_url("https://cursorbridge.dev")
        == "https://cursorbridge.dev/v1"
    )
    assert (
        normalize_bridge_base_url("https://cursorbridge.dev/v1/")
        == "https://cursorbridge.dev/v1"
    )
    assert (
        normalize_bridge_base_url("https://cursorbridge.dev/v1/models")
        == "https://cursorbridge.dev/v1"
    )
    assert (
        normalize_bridge_base_url("https://example.test/proxy/v1/chat/completions")
        == "https://example.test/proxy/v1"
    )
    for bad in ("", "javascript:alert(1)", "https://user:secret@cursorbridge.dev/v1"):
        try:
            normalize_bridge_base_url(bad)
        except ValueError as err:
            assert "Cursor Bridge URL" in str(err)
            continue
        raise AssertionError(f"expected {bad!r} to be rejected")


def test_client_repr_does_not_include_the_api_key() -> None:
    client = CursorBridgeClient(
        None,  # type: ignore[arg-type]
        api_key=API_KEY,
        base_url="https://cursorbridge.dev",
    )
    assert API_KEY not in repr(client)
    assert client.base_url == "https://cursorbridge.dev/v1"


def test_list_models_and_chat_use_bearer_auth_on_the_v1_paths() -> None:
    async def scenario() -> None:
        seen: list[dict] = []

        async def models(request: web.Request) -> web.Response:
            seen.append({"path": request.path, "auth": request.headers["Authorization"]})
            return web.json_response(
                {
                    "object": "list",
                    "data": [
                        {"id": "default"},
                        {"id": "composer-2"},
                        {"id": "default"},
                        {"name": "skipped-no-id"},
                    ],
                }
            )

        async def chat(request: web.Request) -> web.Response:
            body = await request.json()
            seen.append(
                {
                    "path": request.path,
                    "auth": request.headers["Authorization"],
                    "body": body,
                }
            )
            assert API_KEY not in request.path_qs
            return web.json_response(
                {
                    "choices": [
                        {
                            "finish_reason": "tool_calls",
                            "message": {
                                "role": "assistant",
                                "content": [
                                    {"type": "text", "text": "Turning "},
                                    {"type": "text", "text": "the light on."},
                                ],
                                "tool_calls": [
                                    {
                                        "id": "call_1",
                                        "type": "function",
                                        "function": {
                                            "name": "HassTurnOn",
                                            "arguments": json.dumps(
                                                {"name": "Kitchen"}
                                            ),
                                        },
                                    }
                                ],
                            },
                        }
                    ]
                }
            )

        app = web.Application()
        app.router.add_get("/v1/models", models)
        app.router.add_post("/v1/chat/completions", chat)
        server = TestServer(app)
        await server.start_server()
        try:
            base = str(server.make_url("/")).rstrip("/")
            async with ClientSession() as session:
                client = create_chat_provider(
                    "cursor",
                    session=session,
                    api_key=API_KEY,
                    base_url=base,
                )
                models_ids = await client.async_list_models()
                response = await client.async_chat(
                    model="default",
                    messages=[{"role": "user", "content": "turn on the kitchen"}],
                    tools=[
                        {
                            "type": "function",
                            "function": {
                                "name": "HassTurnOn",
                                "description": "Turn on",
                                "parameters": {"type": "object"},
                            },
                        }
                    ],
                )
        finally:
            await server.close()

        assert models_ids == ["default", "composer-2"]
        assert seen[0]["path"] == "/v1/models"
        assert seen[0]["auth"] == f"Bearer {API_KEY}"
        assert seen[1]["path"] == "/v1/chat/completions"
        assert seen[1]["body"]["model"] == "default"
        assert seen[1]["body"]["stream"] is False
        assert seen[1]["body"]["tool_choice"] == "auto"
        assert response.content == "Turning the light on."
        assert response.finish_reason == "tool_calls"
        assert response.tool_calls[0].name == "HassTurnOn"
        assert response.tool_calls[0].arguments == {"name": "Kitchen"}

    asyncio.run(scenario())


def test_bridge_auth_and_api_errors() -> None:
    async def scenario() -> None:
        async def reject(request: web.Request) -> web.Response:
            if request.path.endswith("/models"):
                return web.Response(status=401, text="nope")
            return web.json_response(
                {"error": {"message": "model is overloaded"}}, status=429
            )

        app = web.Application()
        app.router.add_get("/v1/models", reject)
        app.router.add_post("/v1/chat/completions", reject)
        server = TestServer(app)
        await server.start_server()
        try:
            base = str(server.make_url("/")).rstrip("/")
            async with ClientSession() as session:
                client = CursorBridgeClient(session, api_key=API_KEY, base_url=base)
                try:
                    await client.async_list_models()
                except CursorAuthError as err:
                    assert err.status == 401
                    assert API_KEY not in str(err)
                else:
                    raise AssertionError("expected auth error")
                try:
                    await client.async_chat(
                        model="default",
                        messages=[{"role": "user", "content": "hi"}],
                    )
                except CursorAPIError as err:
                    assert not isinstance(err, CursorAuthError)
                    assert "overloaded" in str(err)
                else:
                    raise AssertionError("expected api error")
        finally:
            await server.close()

    asyncio.run(scenario())


def test_unknown_provider_is_rejected() -> None:
    try:
        create_chat_provider(
            "unknown-provider",
            session=None,  # type: ignore[arg-type]
            api_key="sk-test",
            base_url="https://api.openai.com/v1",
        )
    except ValueError as err:
        assert "unknown-provider" in str(err)
    else:
        raise AssertionError("expected unknown provider")

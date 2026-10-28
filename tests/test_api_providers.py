"""OpenAI and Anthropic providers, plus the config-step field checks.

Home Assistant itself is not installed in unit tests. The config flow calls
``flow_input`` for the API-key step and the model step; those branches are
covered here. Chat calls are mocked with an aiohttp test server.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from aiohttp import ClientSession, web
from aiohttp.test_utils import TestServer

from custom_components.smart_llm.const import (
    ANTHROPIC_VERSION,
    CONNECTION_COMPATIBLE,
    CONNECTION_OFFICIAL,
    DEFAULT_ANTHROPIC_BASE_URL,
    DEFAULT_OPENAI_BASE_URL,
)
from custom_components.smart_llm.flow_input import (
    api_key_is_optional,
    parse_api_key,
    parse_connection,
    parse_model_id,
    suggested_model,
)
from custom_components.smart_llm.identity import api_provider_unique_id
from custom_components.smart_llm.provider.anthropic import AnthropicClient
from custom_components.smart_llm.provider.cursor_bridge import CursorBridgeClient
from custom_components.smart_llm.provider.errors import (
    CursorAPIError,
    CursorAuthError,
    ProviderAPIError,
    ProviderAuthError,
)
from custom_components.smart_llm.provider.messages import openai_messages_from_contents
from custom_components.smart_llm.provider.openai_client import OpenAIClient
from custom_components.smart_llm.provider.registry import (
    create_chat_provider,
    provider_menu_options,
)
from custom_components.smart_llm.provider.urls import (
    normalize_anthropic_base_url,
    normalize_openai_base_url,
    resolve_base_url,
)

OPENAI_KEY = "sk-test-openai-key-1234567890abcd"
ANTHROPIC_KEY = "sk-ant-test-key-1234567890wxyz"
ROOT = Path(__file__).resolve().parents[1]


def test_provider_menu_keeps_cursor_first() -> None:
    assert provider_menu_options() == ["cursor", "openai", "anthropic"]


def test_registry_builds_each_provider_and_hides_the_key() -> None:
    cursor = create_chat_provider(
        "cursor",
        session=None,  # type: ignore[arg-type]
        api_key="crsr_test_key_value_1234567890",
        base_url="https://cursorbridge.dev",
    )
    openai = create_chat_provider(
        "openai",
        session=None,  # type: ignore[arg-type]
        api_key=OPENAI_KEY,
        base_url=DEFAULT_OPENAI_BASE_URL,
    )
    anthropic = create_chat_provider(
        "anthropic",
        session=None,  # type: ignore[arg-type]
        api_key=ANTHROPIC_KEY,
        base_url=DEFAULT_ANTHROPIC_BASE_URL,
    )
    assert isinstance(cursor, CursorBridgeClient)
    assert isinstance(openai, OpenAIClient)
    assert isinstance(anthropic, AnthropicClient)
    assert openai.base_url == DEFAULT_OPENAI_BASE_URL
    assert anthropic.base_url == DEFAULT_ANTHROPIC_BASE_URL
    assert OPENAI_KEY not in repr(openai)
    assert ANTHROPIC_KEY not in repr(anthropic)
    for bad in ("", "   "):
        try:
            OpenAIClient(None, api_key=bad, base_url=DEFAULT_OPENAI_BASE_URL)  # type: ignore[arg-type]
        except ValueError:
            pass
        else:
            raise AssertionError("empty OpenAI key was accepted")
        try:
            AnthropicClient(None, api_key=bad, base_url=DEFAULT_ANTHROPIC_BASE_URL)  # type: ignore[arg-type]
        except ValueError:
            pass
        else:
            raise AssertionError("empty Anthropic key was accepted")


def test_cursor_auth_error_is_still_a_provider_auth_error() -> None:
    err = CursorAuthError("rejected", status=401)
    assert isinstance(err, CursorAPIError)
    assert isinstance(err, ProviderAuthError)
    assert isinstance(err, ProviderAPIError)
    assert err.status == 401


def test_base_urls_for_official_and_compatible_modes() -> None:
    assert normalize_openai_base_url("https://api.openai.com") == DEFAULT_OPENAI_BASE_URL
    assert (
        normalize_openai_base_url("https://openrouter.ai/api/v1/chat/completions")
        == "https://openrouter.ai/api/v1"
    )
    assert (
        normalize_openai_base_url("https://api.openai.com/v1?api_key=sk-secret")
        == DEFAULT_OPENAI_BASE_URL
    )
    assert (
        normalize_openai_base_url("http://127.0.0.1:11434/v1")
        == "http://127.0.0.1:11434/v1"
    )
    assert (
        normalize_openai_base_url("http://127.0.0.1:11434")
        == "http://127.0.0.1:11434/v1"
    )
    assert (
        normalize_openai_base_url("http://192.168.1.10:8000/v1/")
        == "http://192.168.1.10:8000/v1"
    )
    assert (
        normalize_openai_base_url("http://host.docker.internal:11434/v1/models")
        == "http://host.docker.internal:11434/v1"
    )
    assert normalize_anthropic_base_url("https://api.anthropic.com/v1") == (
        DEFAULT_ANTHROPIC_BASE_URL
    )
    assert (
        normalize_anthropic_base_url("https://gateway.example/anthropic/v1/messages")
        == "https://gateway.example/anthropic"
    )
    for bad in ("", "javascript:alert(1)", "https://user:secret@api.openai.com/v1"):
        try:
            normalize_openai_base_url(bad)
        except ValueError:
            continue
        raise AssertionError(f"expected {bad!r} to be rejected")

    official = resolve_base_url(
        "openai",
        {"connection_mode": CONNECTION_OFFICIAL, "base_url": "https://evil.test/v1"},
    )
    assert official == DEFAULT_OPENAI_BASE_URL
    custom = resolve_base_url(
        "openai",
        {
            "connection_mode": CONNECTION_COMPATIBLE,
            "base_url": "https://openrouter.ai/api/v1",
        },
    )
    assert custom == "https://openrouter.ai/api/v1"
    local = resolve_base_url(
        "openai",
        {
            "connection_mode": CONNECTION_COMPATIBLE,
            "base_url": "http://127.0.0.1:11434",
        },
    )
    assert local == "http://127.0.0.1:11434/v1"
    assert (
        resolve_base_url("anthropic", {"connection_mode": CONNECTION_OFFICIAL})
        == DEFAULT_ANTHROPIC_BASE_URL
    )
    assert (
        resolve_base_url(
            "anthropic",
            {
                "connection_mode": CONNECTION_COMPATIBLE,
                "base_url": "https://gateway.example/anthropic/v1",
            },
        )
        == "https://gateway.example/anthropic"
    )
    assert (
        resolve_base_url(
            "cursor",
            {"bridge_base_url": "https://cursorbridge.dev/v1/models"},
        )
        == "https://cursorbridge.dev/v1"
    )
    try:
        OpenAIClient(
            None,  # type: ignore[arg-type]
            api_key=OPENAI_KEY,
            base_url=f"https://example.test/{OPENAI_KEY}/v1",
        )
    except ValueError as err:
        assert "API key" in str(err)
    else:
        raise AssertionError("base URL containing the key was accepted")


def test_api_key_step_rejects_blank_and_spaced_keys() -> None:
    missing, errors = parse_api_key({})
    assert missing is None
    assert errors == {"api_key": "invalid_api_key"}
    spaced, errors = parse_api_key({"api_key": "sk-has space"})
    assert spaced is None
    assert errors["api_key"] == "invalid_api_key"
    key, errors = parse_api_key({"api_key": f"  {OPENAI_KEY}  "})
    assert errors == {}
    assert key == OPENAI_KEY
    assert OPENAI_KEY not in str(errors)
    blank, errors = parse_api_key({}, allow_empty=True)
    assert blank == ""
    assert errors == {}
    spaces, errors = parse_api_key({"api_key": "   "}, allow_empty=True)
    assert spaces == ""
    assert errors == {}
    spaced_local, errors = parse_api_key({"api_key": "has space"}, allow_empty=True)
    assert spaced_local is None
    assert errors["api_key"] == "invalid_api_key"
    assert api_key_is_optional("openai", "compatible")
    assert not api_key_is_optional("openai", "official")
    assert not api_key_is_optional("anthropic", "compatible")
    assert not api_key_is_optional("cursor", "compatible")


def test_official_and_compatible_connection_steps() -> None:
    official, errors = parse_connection(
        "openai",
        {"connection_mode": "official", "base_url": "javascript:alert(1)"},
    )
    assert errors == {}
    assert official is not None
    assert official.mode == CONNECTION_OFFICIAL
    assert official.base_url == DEFAULT_OPENAI_BASE_URL

    anthropic, errors = parse_connection("anthropic", {})
    assert errors == {}
    assert anthropic is not None
    assert anthropic.base_url == DEFAULT_ANTHROPIC_BASE_URL

    missing, errors = parse_connection("openai", {"connection_mode": "compatible"})
    assert missing is None
    assert errors == {"base_url": "invalid_url"}

    bad, errors = parse_connection(
        "anthropic",
        {
            "connection_mode": "compatible",
            "base_url": "https://user:secret@gateway.example",
        },
    )
    assert bad is None
    assert errors == {"base_url": "invalid_url"}

    custom, errors = parse_connection(
        "openai",
        {
            "connection_mode": "compatible",
            "base_url": "https://openrouter.ai/api/v1/chat/completions",
        },
    )
    assert errors == {}
    assert custom is not None
    assert custom.mode == CONNECTION_COMPATIBLE
    assert custom.base_url == "https://openrouter.ai/api/v1"

    gateway, errors = parse_connection(
        "anthropic",
        {
            "connection_mode": "compatible",
            "base_url": "https://gateway.example/anthropic/v1",
        },
    )
    assert errors == {}
    assert gateway is not None
    assert gateway.base_url == "https://gateway.example/anthropic"

    unknown, errors = parse_connection("cursor", {"connection_mode": "official"})
    assert unknown is None
    assert errors == {"connection_mode": "invalid_connection_mode"}


def test_model_step_accepts_ids_without_spaces() -> None:
    assert parse_model_id("gpt-4o-mini") == "gpt-4o-mini"
    assert parse_model_id("  claude-sonnet-4-5  ") == "claude-sonnet-4-5"
    assert parse_model_id("   ") is None
    assert parse_model_id("two words") is None
    assert suggested_model("openai", []) == "gpt-4o-mini"
    assert suggested_model("openai", ["gpt-4o", "gpt-4o-mini"]) == "gpt-4o-mini"
    assert suggested_model("anthropic", ["claude-haiku-next"]) == "claude-haiku-next"


def test_api_provider_unique_id_does_not_contain_the_key() -> None:
    openai_id = api_provider_unique_id("openai", OPENAI_KEY)
    assert openai_id.startswith("openai-")
    assert OPENAI_KEY not in openai_id
    assert openai_id == api_provider_unique_id("openai", OPENAI_KEY)
    assert openai_id != api_provider_unique_id("anthropic", OPENAI_KEY)
    assert openai_id != api_provider_unique_id("openai", ANTHROPIC_KEY)
    ollama = api_provider_unique_id(
        "openai", "", base_url="http://127.0.0.1:11434/v1"
    )
    vllm = api_provider_unique_id("openai", "", base_url="http://127.0.0.1:8000/v1")
    assert ollama.startswith("openai-")
    assert ollama != vllm
    assert "11434" not in ollama
    assert openai_id == api_provider_unique_id(
        "openai", OPENAI_KEY, base_url="http://127.0.0.1:11434/v1"
    )


def test_translation_strings_have_no_urls_and_match_keys() -> None:
    strings = json.loads((ROOT / "custom_components/smart_llm/strings.json").read_text())
    english = json.loads(
        (ROOT / "custom_components/smart_llm/translations/en.json").read_text()
    )
    chinese = json.loads(
        (ROOT / "custom_components/smart_llm/translations/zh-Hans.json").read_text()
    )
    assert strings == english

    def leaf_paths(value: object, prefix: str = "") -> set[str]:
        if isinstance(value, dict):
            found: set[str] = set()
            for key, item in value.items():
                path = f"{prefix}.{key}" if prefix else key
                found.add(path)
                found |= leaf_paths(item, path)
            return found
        return set()

    assert leaf_paths(strings) == leaf_paths(chinese)
    for path in (
        ROOT / "custom_components/smart_llm/strings.json",
        ROOT / "custom_components/smart_llm/translations/en.json",
        ROOT / "custom_components/smart_llm/translations/zh-Hans.json",
    ):
        assert re.search(r"https?://", path.read_text(encoding="utf-8")) is None


def test_openai_official_and_custom_base_chat() -> None:
    async def scenario() -> None:
        seen: list[dict] = []

        async def models(request: web.Request) -> web.Response:
            seen.append(
                {
                    "path": request.path,
                    "auth": request.headers["Authorization"],
                }
            )
            assert OPENAI_KEY not in request.path_qs
            return web.json_response(
                {"data": [{"id": "gpt-4o-mini"}, {"id": "gpt-4o"}, {"id": "gpt-4o-mini"}]}
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
            assert OPENAI_KEY not in request.path_qs
            return web.json_response(
                {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": "Lights on."},
                        }
                    ]
                }
            )

        app = web.Application()
        app.router.add_get("/v1/models", models)
        app.router.add_post("/v1/chat/completions", chat)
        app.router.add_get("/proxy/v1/models", models)
        app.router.add_post("/proxy/v1/chat/completions", chat)
        server = TestServer(app)
        await server.start_server()
        try:
            root = str(server.make_url("/")).rstrip("/")
            messages = openai_messages_from_contents(
                [
                    {"role": "system", "content": "You control the home."},
                    {"role": "user", "content": "Turn on the lamp"},
                ]
            )
            async with ClientSession() as session:
                official = create_chat_provider(
                    "openai",
                    session=session,
                    api_key=OPENAI_KEY,
                    base_url=root,
                )
                assert await official.async_list_models() == ["gpt-4o-mini", "gpt-4o"]
                reply = await official.async_chat(
                    model="gpt-4o-mini",
                    messages=messages,
                )
                custom = create_chat_provider(
                    "openai",
                    session=session,
                    api_key=OPENAI_KEY,
                    base_url=f"{root}/proxy/v1",
                )
                custom_reply = await custom.async_chat(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": "hi"}],
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

        assert reply.content == "Lights on."
        assert reply.finish_reason == "stop"
        assert seen[0]["path"] == "/v1/models"
        assert seen[0]["auth"] == f"Bearer {OPENAI_KEY}"
        assert seen[1]["path"] == "/v1/chat/completions"
        assert seen[1]["body"]["stream"] is False
        assert seen[1]["body"]["messages"][0]["role"] == "system"
        assert seen[1]["body"]["messages"][1]["content"] == "Turn on the lamp"
        assert seen[2]["path"] == "/proxy/v1/chat/completions"
        assert seen[2]["auth"] == f"Bearer {OPENAI_KEY}"
        assert seen[2]["body"]["tool_choice"] == "auto"
        assert custom_reply.content == "Lights on."

    asyncio.run(scenario())


def test_openai_local_server_omits_authorization_when_the_key_is_empty() -> None:
    """Ollama and vLLM accept an OpenAI-compatible base with no API key."""

    async def scenario() -> None:
        seen: list[dict] = []

        async def models(request: web.Request) -> web.Response:
            seen.append(
                {
                    "path": request.path,
                    "auth": request.headers.get("Authorization"),
                }
            )
            return web.json_response({"data": [{"id": "llama3.2"}, {"id": "qwen2.5"}]})

        async def chat(request: web.Request) -> web.Response:
            body = await request.json()
            seen.append(
                {
                    "path": request.path,
                    "auth": request.headers.get("Authorization"),
                    "body": body,
                }
            )
            return web.json_response(
                {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": "On."},
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
            root = str(server.make_url("/")).rstrip("/")
            async with ClientSession() as session:
                client = create_chat_provider(
                    "openai",
                    session=session,
                    api_key="",
                    base_url=f"{root}/v1",
                )
                assert client.base_url.startswith("http://")
                assert await client.async_list_models() == ["llama3.2", "qwen2.5"]
                reply = await client.async_chat(
                    model="llama3.2",
                    messages=[{"role": "user", "content": "hi"}],
                )
        finally:
            await server.close()

        assert reply.content == "On."
        assert seen[0]["path"] == "/v1/models"
        assert seen[0]["auth"] is None
        assert seen[1]["path"] == "/v1/chat/completions"
        assert seen[1]["auth"] is None
        assert seen[1]["body"]["model"] == "llama3.2"
        assert "Authorization" not in json.dumps(seen)

    asyncio.run(scenario())


def test_openai_redacts_a_key_echoed_by_the_api() -> None:
    async def scenario() -> None:
        async def reject(request: web.Request) -> web.Response:
            if request.path.endswith("/models"):
                return web.json_response(
                    {"error": {"message": f"invalid key {OPENAI_KEY}"}},
                    status=401,
                )
            return web.json_response(
                {"error": {"message": f"overloaded {OPENAI_KEY}"}},
                status=429,
            )

        app = web.Application()
        app.router.add_get("/v1/models", reject)
        app.router.add_post("/v1/chat/completions", reject)
        server = TestServer(app)
        await server.start_server()
        try:
            root = str(server.make_url("/")).rstrip("/")
            async with ClientSession() as session:
                client = OpenAIClient(session, api_key=OPENAI_KEY, base_url=root)
                try:
                    await client.async_list_models()
                except ProviderAuthError as err:
                    assert err.status == 401
                    assert OPENAI_KEY not in str(err)
                    assert not isinstance(err, CursorAuthError)
                else:
                    raise AssertionError("expected auth error")
                try:
                    await client.async_chat(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": "hi"}],
                    )
                except ProviderAPIError as err:
                    assert not isinstance(err, ProviderAuthError)
                    assert "overloaded" in str(err)
                    assert OPENAI_KEY not in str(err)
                    assert "••••" in str(err)
                else:
                    raise AssertionError("expected api error")
        finally:
            await server.close()

    asyncio.run(scenario())


def test_anthropic_official_headers_and_custom_gateway() -> None:
    async def scenario() -> None:
        seen: list[dict] = []

        async def models(request: web.Request) -> web.Response:
            seen.append(
                {
                    "path": request.path,
                    "api_key": request.headers["x-api-key"],
                    "version": request.headers["anthropic-version"],
                    "authorization": request.headers.get("Authorization"),
                }
            )
            assert ANTHROPIC_KEY not in request.path_qs
            return web.json_response(
                {
                    "data": [
                        {"id": "claude-sonnet-4-5", "type": "model"},
                        {"id": "claude-haiku-next", "type": "model"},
                    ],
                    "has_more": False,
                }
            )

        async def messages(request: web.Request) -> web.Response:
            body = await request.json()
            seen.append(
                {
                    "path": request.path,
                    "api_key": request.headers["x-api-key"],
                    "version": request.headers["anthropic-version"],
                    "authorization": request.headers.get("Authorization"),
                    "body": body,
                }
            )
            assert ANTHROPIC_KEY not in request.path_qs
            if body["messages"][-1]["role"] == "user" and isinstance(
                body["messages"][-1]["content"], list
            ):
                return web.json_response(
                    {
                        "stop_reason": "end_turn",
                        "content": [{"type": "text", "text": "Done."}],
                    }
                )
            return web.json_response(
                {
                    "stop_reason": "tool_use",
                    "content": [
                        {"type": "text", "text": "Turning the light on."},
                        {
                            "type": "tool_use",
                            "id": "toolu_1",
                            "name": "HassTurnOn",
                            "input": {"name": "Kitchen"},
                        },
                    ],
                }
            )

        app = web.Application()
        app.router.add_get("/v1/models", models)
        app.router.add_post("/v1/messages", messages)
        app.router.add_get("/gateway/v1/models", models)
        app.router.add_post("/gateway/v1/messages", messages)
        server = TestServer(app)
        await server.start_server()
        try:
            root = str(server.make_url("/")).rstrip("/")
            messages_in = openai_messages_from_contents(
                [
                    {"role": "system", "content": "You control the home."},
                    {"role": "user", "content": "Turn on the kitchen"},
                ]
            )
            tool = {
                "type": "function",
                "function": {
                    "name": "HassTurnOn",
                    "description": "Turn on",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
            async with ClientSession() as session:
                official = create_chat_provider(
                    "anthropic",
                    session=session,
                    api_key=ANTHROPIC_KEY,
                    base_url=f"{root}/v1",
                )
                assert official.base_url == root
                model_ids = await official.async_list_models()
                reply = await official.async_chat(
                    model="claude-sonnet-4-5",
                    messages=messages_in,
                    tools=[tool],
                )
                follow_up = openai_messages_from_contents(
                    [
                        {"role": "user", "content": "Turn on the kitchen"},
                        {
                            "role": "assistant",
                            "content": "Turning the light on.",
                            "tool_calls": [
                                {
                                    "id": "toolu_1",
                                    "type": "function",
                                    "function": {
                                        "name": "HassTurnOn",
                                        "arguments": json.dumps({"name": "Kitchen"}),
                                    },
                                }
                            ],
                        },
                        {
                            "role": "tool_result",
                            "tool_call_id": "toolu_1",
                            "result": {"data": {"success": True}, "error": False},
                        },
                    ]
                )
                done = await official.async_chat(
                    model="claude-sonnet-4-5",
                    messages=follow_up,
                )
                gateway = create_chat_provider(
                    "anthropic",
                    session=session,
                    api_key=ANTHROPIC_KEY,
                    base_url=f"{root}/gateway",
                )
                await gateway.async_list_models()
        finally:
            await server.close()

        assert model_ids == ["claude-sonnet-4-5", "claude-haiku-next"]
        assert reply.content == "Turning the light on."
        assert reply.finish_reason == "tool_calls"
        assert reply.tool_calls[0].name == "HassTurnOn"
        assert reply.tool_calls[0].arguments == {"name": "Kitchen"}
        assert done.content == "Done."
        assert seen[0]["path"] == "/v1/models"
        assert seen[0]["api_key"] == ANTHROPIC_KEY
        assert seen[0]["version"] == ANTHROPIC_VERSION
        assert seen[0]["authorization"] is None
        body = seen[1]["body"]
        assert seen[1]["path"] == "/v1/messages"
        assert body["model"] == "claude-sonnet-4-5"
        assert body["max_tokens"] == 4096
        assert body["system"] == "You control the home."
        assert body["messages"] == [
            {"role": "user", "content": "Turn on the kitchen"}
        ]
        assert body["tools"][0]["name"] == "HassTurnOn"
        assert body["tools"][0]["input_schema"]["type"] == "object"
        tool_turn = seen[2]["body"]["messages"]
        assert tool_turn[1]["role"] == "assistant"
        assert tool_turn[1]["content"][0]["type"] == "text"
        assert tool_turn[1]["content"][1]["type"] == "tool_use"
        assert tool_turn[1]["content"][1]["input"] == {"name": "Kitchen"}
        assert tool_turn[2]["role"] == "user"
        assert tool_turn[2]["content"][0]["type"] == "tool_result"
        assert tool_turn[2]["content"][0]["tool_use_id"] == "toolu_1"
        assert seen[3]["path"] == "/gateway/v1/models"
        assert seen[3]["api_key"] == ANTHROPIC_KEY
        assert ANTHROPIC_KEY not in json.dumps(
            {key: value for key, value in seen[1].items() if key != "api_key"}
        )

    asyncio.run(scenario())


def test_anthropic_auth_error_hides_the_key() -> None:
    async def scenario() -> None:
        async def reject(request: web.Request) -> web.Response:
            return web.json_response(
                {
                    "type": "error",
                    "error": {"type": "authentication_error", "message": ANTHROPIC_KEY},
                },
                status=403,
            )

        app = web.Application()
        app.router.add_get("/v1/models", reject)
        server = TestServer(app)
        await server.start_server()
        try:
            root = str(server.make_url("/")).rstrip("/")
            async with ClientSession() as session:
                client = AnthropicClient(session, api_key=ANTHROPIC_KEY, base_url=root)
                try:
                    await client.async_list_models()
                except ProviderAuthError as err:
                    assert err.status == 403
                    assert ANTHROPIC_KEY not in str(err)
                else:
                    raise AssertionError("expected auth error")
        finally:
            await server.close()

    asyncio.run(scenario())

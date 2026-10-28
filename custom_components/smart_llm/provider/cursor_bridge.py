"""Cursor Bridge OpenAI-compatible client.

Cursor Bridge (https://cursorbridge.dev) is an unofficial community service.
It accepts a Cursor user API key and exposes ``GET /v1/models`` and
``POST /v1/chat/completions``. Prompts and the API key are sent to whatever
base URL the user configured.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

from aiohttp import ClientError, ClientSession, ClientTimeout

from ..const import DEFAULT_BRIDGE_BASE_URL
from .base import ChatProvider, ChatResponse, ToolCallRequest
from .errors import CursorAPIError, CursorAuthError
from .http_util import error_message, read_body
from .messages import coerce_text

_MODELS_TIMEOUT = ClientTimeout(total=30)
_CHAT_TIMEOUT = ClientTimeout(total=180)


class CursorBridgeClient(ChatProvider):
    """Talk to an OpenAI-compatible Cursor Bridge deployment."""

    id = "cursor"

    def __init__(
        self,
        session: ClientSession,
        *,
        api_key: str,
        base_url: str = DEFAULT_BRIDGE_BASE_URL,
    ) -> None:
        if not api_key:
            raise ValueError("Cursor API key is empty")
        self._session = session
        self._api_key = api_key
        self.base_url = normalize_bridge_base_url(base_url)

    def __repr__(self) -> str:
        return f"CursorBridgeClient(base_url={self.base_url!r})"

    async def async_list_models(self) -> list[str]:
        """Return model ids from ``GET /v1/models``."""
        payload = await self._request("GET", "models", timeout=_MODELS_TIMEOUT)
        return _model_ids(payload)

    async def async_chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResponse:
        """Send ``POST /v1/chat/completions`` and normalize the first choice."""
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        payload = await self._request(
            "POST",
            "chat/completions",
            json_body=body,
            timeout=_CHAT_TIMEOUT,
        )
        return _chat_response(payload)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        timeout: ClientTimeout,
    ) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }
        try:
            async with self._session.request(
                method,
                url,
                headers=headers,
                json=json_body,
                timeout=timeout,
            ) as response:
                payload = await read_body(response)
                status = response.status
        except TimeoutError as err:
            raise CursorAPIError("Cursor Bridge timed out", status=None) from err
        except ClientError as err:
            raise CursorAPIError("Could not reach Cursor Bridge", status=None) from err

        if status in {401, 403}:
            raise CursorAuthError(
                "Cursor Bridge rejected the API key",
                status=status,
            )
        if status >= 400:
            raise CursorAPIError(error_message(payload, status), status=status)
        if not isinstance(payload, (dict, list)):
            raise CursorAPIError("Cursor Bridge returned an unreadable response")
        return payload


def normalize_bridge_base_url(url: str) -> str:
    """Canonicalize a Bridge base URL so it ends at the ``/v1`` prefix."""
    candidate = url.strip()
    if not candidate:
        raise ValueError("Cursor Bridge URL is empty")
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Cursor Bridge URL must be an http(s) URL")
    if parsed.username or parsed.password:
        raise ValueError("Cursor Bridge URL must not include credentials")
    path = parsed.path.rstrip("/")
    for suffix in ("/chat/completions", "/models"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            path = path.rstrip("/")
    if path in {"", "/"}:
        path = "/v1"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _model_ids(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        items = payload.get("data")
        if items is None and isinstance(payload.get("models"), list):
            items = payload["models"]
    elif isinstance(payload, list):
        items = payload
    else:
        items = None
    if not isinstance(items, list):
        raise CursorAPIError("Cursor Bridge model list had an unexpected shape")

    models: list[str] = []
    seen: set[str] = set()
    for item in items:
        model_id: str | None = None
        if isinstance(item, str):
            model_id = item
        elif isinstance(item, dict) and isinstance(item.get("id"), str):
            model_id = item["id"]
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        models.append(model_id)
    return models


def _chat_response(payload: Any) -> ChatResponse:
    if not isinstance(payload, dict):
        raise CursorAPIError("Cursor Bridge chat response had an unexpected shape")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise CursorAPIError("Cursor Bridge chat response did not include choices")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise CursorAPIError("Cursor Bridge chat response had an unexpected choice")
    message = choice.get("message")
    if not isinstance(message, dict):
        raise CursorAPIError("Cursor Bridge chat response did not include a message")
    finish = choice.get("finish_reason")
    return ChatResponse(
        content=coerce_text(message.get("content")),
        tool_calls=_tool_calls(message.get("tool_calls")),
        finish_reason=finish if isinstance(finish, str) else None,
    )


def _tool_calls(raw: Any) -> list[ToolCallRequest]:
    if not isinstance(raw, list):
        return []
    calls: list[ToolCallRequest] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        function = item.get("function")
        if not isinstance(function, dict):
            function = {}
        name = function.get("name") or item.get("name") or ""
        if not isinstance(name, str) or not name:
            continue
        call_id = item.get("id")
        if not isinstance(call_id, str) or not call_id:
            call_id = f"call_{index}"
        calls.append(
            ToolCallRequest(
                id=call_id,
                name=name,
                arguments=_arguments(function.get("arguments")),
            )
        )
    return calls


def _arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if raw is None or raw == "":
        return {}
    if isinstance(raw, str):
        try:
            parsed = json_loads(raw)
        except ValueError:
            return {"_raw": raw[:2000]}
        if isinstance(parsed, dict):
            return parsed
        return {"value": parsed}
    return {"value": raw}


def json_loads(raw: str) -> Any:
    """Parse JSON, raising ``ValueError`` for invalid input."""
    import json

    try:
        return json.loads(raw)
    except json.JSONDecodeError as err:
        raise ValueError("Invalid JSON") from err

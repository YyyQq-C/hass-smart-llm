"""Anthropic Messages provider.

Official mode calls ``https://api.anthropic.com`` with ``x-api-key`` and
``anthropic-version``. Compatible mode keeps those headers and uses the
configured base URL (an Anthropic-compatible gateway).
"""

from __future__ import annotations

from typing import Any

from aiohttp import ClientSession, ClientTimeout

from ..const import ANTHROPIC_VERSION, DEFAULT_ANTHROPIC_BASE_URL
from .anthropic_messages import build_anthropic_body
from .base import ChatProvider, ChatResponse, ToolCallRequest
from .errors import ProviderAPIError
from .http_util import async_request_json
from .openai_parse import parse_model_ids
from .urls import normalize_anthropic_base_url

_MODELS_TIMEOUT = ClientTimeout(total=30)
_CHAT_TIMEOUT = ClientTimeout(total=180)


class AnthropicClient(ChatProvider):
    """Talk to the Anthropic Messages API or a compatible base URL."""

    id = "anthropic"

    def __init__(
        self,
        session: ClientSession,
        *,
        api_key: str,
        base_url: str = DEFAULT_ANTHROPIC_BASE_URL,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("Anthropic API key is empty")
        self._session = session
        self._api_key = api_key
        self.base_url = normalize_anthropic_base_url(base_url)
        if api_key in self.base_url:
            raise ValueError("API base URL must not include the API key")

    def __repr__(self) -> str:
        return f"AnthropicClient(base_url={self.base_url!r})"

    async def async_list_models(self) -> list[str]:
        """Return model ids from ``GET /v1/models``."""
        payload = await self._request("GET", "/v1/models", timeout=_MODELS_TIMEOUT)
        return parse_model_ids(payload, service="Anthropic")

    async def async_chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResponse:
        """Send ``POST /v1/messages`` and normalize the assistant content."""
        try:
            body = build_anthropic_body(model, messages, tools)
        except ValueError as err:
            raise ProviderAPIError(str(err)) from err
        payload = await self._request(
            "POST",
            "/v1/messages",
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
            "x-api-key": self._api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "Accept": "application/json",
        }
        return await async_request_json(
            self._session,
            method,
            url,
            headers=headers,
            json_body=json_body,
            timeout=timeout,
            secret=self._api_key,
            service="Anthropic",
        )


def _chat_response(payload: Any) -> ChatResponse:
    if not isinstance(payload, dict) or "content" not in payload:
        raise ProviderAPIError("Anthropic response had an unexpected shape")
    content = payload.get("content")
    texts: list[str] = []
    calls: list[ToolCallRequest] = []
    if isinstance(content, str):
        texts.append(content)
    elif isinstance(content, list):
        for index, block in enumerate(content):
            if not isinstance(block, dict):
                continue
            kind = block.get("type")
            if kind == "text" and isinstance(block.get("text"), str):
                texts.append(block["text"])
            elif kind == "tool_use":
                name = block.get("name")
                if not isinstance(name, str) or not name:
                    continue
                call_id = block.get("id")
                if not isinstance(call_id, str) or not call_id:
                    call_id = f"toolu_{index}"
                arguments = block.get("input")
                if not isinstance(arguments, dict):
                    arguments = {}
                calls.append(
                    ToolCallRequest(id=call_id, name=name, arguments=arguments)
                )
    else:
        raise ProviderAPIError("Anthropic response did not include content")
    stop = payload.get("stop_reason")
    finish = stop if isinstance(stop, str) else None
    if finish == "tool_use":
        finish = "tool_calls"
    text = "".join(texts)
    return ChatResponse(
        content=text or None,
        tool_calls=calls,
        finish_reason=finish,
    )

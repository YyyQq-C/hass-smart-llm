"""OpenAI chat provider.

Official mode calls ``https://api.openai.com/v1`` with
``Authorization: Bearer <api_key>``. Compatible mode keeps that header and
uses the configured base URL (Azure OpenAI, OpenRouter, or another
OpenAI-compatible proxy).
"""

from __future__ import annotations

from typing import Any

from aiohttp import ClientSession, ClientTimeout

from ..const import DEFAULT_OPENAI_BASE_URL
from .base import ChatProvider, ChatResponse
from .http_util import async_request_json
from .openai_parse import parse_chat_response, parse_model_ids
from .urls import normalize_openai_base_url

_MODELS_TIMEOUT = ClientTimeout(total=30)
_CHAT_TIMEOUT = ClientTimeout(total=180)


class OpenAIClient(ChatProvider):
    """Talk to the OpenAI API or an OpenAI-compatible base URL."""

    id = "openai"

    def __init__(
        self,
        session: ClientSession,
        *,
        api_key: str,
        base_url: str = DEFAULT_OPENAI_BASE_URL,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("OpenAI API key is empty")
        self._session = session
        self._api_key = api_key
        self.base_url = normalize_openai_base_url(base_url)
        if api_key in self.base_url:
            raise ValueError("API base URL must not include the API key")

    def __repr__(self) -> str:
        return f"OpenAIClient(base_url={self.base_url!r})"

    async def async_list_models(self) -> list[str]:
        """Return model ids from ``GET /v1/models``."""
        payload = await self._request("GET", "models", timeout=_MODELS_TIMEOUT)
        return parse_model_ids(payload, service="OpenAI")

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
        return parse_chat_response(payload, service="OpenAI")

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
        return await async_request_json(
            self._session,
            method,
            url,
            headers=headers,
            json_body=json_body,
            timeout=timeout,
            secret=self._api_key,
            service="OpenAI",
        )

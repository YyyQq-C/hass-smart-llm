"""OpenAI chat provider.

Official mode calls ``https://api.openai.com/v1`` with
``Authorization: Bearer <api_key>`` and requires a key. Compatible mode uses
the configured base URL (Azure OpenAI, OpenRouter, Ollama, vLLM, or another
OpenAI-compatible server). When that key is empty, the client omits
``Authorization`` instead of sending an empty bearer token.
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
        key = api_key.strip() if isinstance(api_key, str) else ""
        self._session = session
        self.base_url = normalize_openai_base_url(base_url)
        # Official OpenAI always requires a key. A custom base URL may be a
        # local server (Ollama, vLLM) that does not check Authorization.
        if not key and self.base_url == DEFAULT_OPENAI_BASE_URL:
            raise ValueError("OpenAI API key is empty")
        if key and key in self.base_url:
            raise ValueError("API base URL must not include the API key")
        self._api_key = key

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
        headers = {"Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
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

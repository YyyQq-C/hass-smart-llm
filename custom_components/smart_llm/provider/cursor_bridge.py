"""Cursor Bridge OpenAI-compatible client.

Cursor Bridge (https://cursorbridge.dev) is an unofficial community service.
It accepts a Cursor user API key and exposes ``GET /v1/models`` and
``POST /v1/chat/completions``. Prompts and the API key are sent to whatever
base URL the user configured.
"""

from __future__ import annotations

from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from ..const import DEFAULT_BRIDGE_BASE_URL
from .base import ChatProvider, ChatResponse
from .errors import CursorAPIError, CursorAuthError
from .http_util import error_message, read_body, redact_secret
from .openai_parse import parse_chat_response, parse_model_ids
from .urls import normalize_openai_base_url

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
        return parse_model_ids(payload, service="Cursor Bridge")

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
        return parse_chat_response(payload, service="Cursor Bridge")

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
            raise CursorAPIError(
                redact_secret(error_message(payload, status), self._api_key),
                status=status,
            )
        if not isinstance(payload, (dict, list)):
            raise CursorAPIError("Cursor Bridge returned an unreadable response")
        return payload


def normalize_bridge_base_url(url: str) -> str:
    """Canonicalize a Bridge base URL so it ends at the ``/v1`` prefix."""
    try:
        return normalize_openai_base_url(url)
    except ValueError as err:
        message = str(err).replace("API base URL", "Cursor Bridge URL")
        raise ValueError(message) from err

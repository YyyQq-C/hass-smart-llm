"""Registry of chat providers.

Cursor signs in through the browser. OpenAI and Anthropic take an API key and
call either the official host or a custom base URL with the same header.
"""

from __future__ import annotations

from aiohttp import ClientSession

from ..const import PROVIDER_ANTHROPIC, PROVIDER_CURSOR, PROVIDER_OPENAI
from .anthropic import AnthropicClient
from .base import ChatProvider
from .cursor_bridge import CursorBridgeClient
from .openai_client import OpenAIClient

# Menu step id → label. Config flow translations supply the user-facing copy.
PROVIDER_STEPS: dict[str, str] = {
    PROVIDER_CURSOR: "Cursor",
    PROVIDER_OPENAI: "OpenAI",
    PROVIDER_ANTHROPIC: "Anthropic",
}


def provider_menu_options() -> list[str]:
    """Config-flow menu step ids, in display order."""
    return list(PROVIDER_STEPS)


def create_chat_provider(
    provider_id: str,
    *,
    session: ClientSession,
    api_key: str,
    base_url: str,
) -> ChatProvider:
    """Build the chat client for a stored config entry."""
    if provider_id == PROVIDER_CURSOR:
        return CursorBridgeClient(session, api_key=api_key, base_url=base_url)
    if provider_id == PROVIDER_OPENAI:
        return OpenAIClient(session, api_key=api_key, base_url=base_url)
    if provider_id == PROVIDER_ANTHROPIC:
        return AnthropicClient(session, api_key=api_key, base_url=base_url)
    raise ValueError(f"Unknown Smart LLM provider: {provider_id}")

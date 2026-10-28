"""Registry of chat providers.

Version 1 registers Cursor only. A later OpenAI or Claude provider implements
``ChatProvider`` and adds one branch here, plus a config-flow step that knows
how that provider authenticates.
"""

from __future__ import annotations

from aiohttp import ClientSession

from ..const import PROVIDER_CURSOR
from .base import ChatProvider
from .cursor_bridge import CursorBridgeClient

# Menu step id → label. Config flow translations supply the user-facing copy.
PROVIDER_STEPS: dict[str, str] = {
    PROVIDER_CURSOR: "Cursor",
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
    raise ValueError(f"Unknown Smart LLM provider: {provider_id}")

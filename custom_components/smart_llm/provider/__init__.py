"""Pluggable chat providers for Smart LLM."""

from .anthropic import AnthropicClient
from .base import ChatProvider, ChatResponse, ToolCallRequest
from .cursor_auth import (
    LoginHandshake,
    LoginResult,
    async_login_and_mint,
    create_login_handshake,
)
from .cursor_bridge import CursorBridgeClient, normalize_bridge_base_url
from .errors import (
    CursorAPIError,
    CursorAuthError,
    CursorLoginError,
    ProviderAPIError,
    ProviderAuthError,
)
from .openai_client import OpenAIClient
from .registry import create_chat_provider, provider_menu_options

__all__ = [
    "AnthropicClient",
    "ChatProvider",
    "ChatResponse",
    "CursorAPIError",
    "CursorAuthError",
    "CursorBridgeClient",
    "CursorLoginError",
    "LoginHandshake",
    "LoginResult",
    "OpenAIClient",
    "ProviderAPIError",
    "ProviderAuthError",
    "ToolCallRequest",
    "async_login_and_mint",
    "create_chat_provider",
    "create_login_handshake",
    "normalize_bridge_base_url",
    "provider_menu_options",
]

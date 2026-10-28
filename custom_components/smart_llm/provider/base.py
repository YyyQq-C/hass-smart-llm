"""Provider interface shared by Cursor today and later backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ToolCallRequest:
    """One tool call requested by the model."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ChatResponse:
    """Normalized chat completion."""

    content: str | None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    finish_reason: str | None = None


class ChatProvider(ABC):
    """OpenAI-style chat provider used by the conversation agent.

    Add a provider by subclassing this and registering it in
    ``provider.registry``. Authentication stays with the provider: Cursor uses
    the browser handshake, while a future OpenAI or Claude provider can collect
    an API key directly.
    """

    id: str

    @abstractmethod
    async def async_list_models(self) -> list[str]:
        """Return model ids the account can select."""

    @abstractmethod
    async def async_chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResponse:
        """Send one non-streaming chat completion."""

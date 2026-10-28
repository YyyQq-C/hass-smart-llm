"""Parse OpenAI-compatible ``/v1/models`` and chat-completion payloads."""

from __future__ import annotations

import json
from typing import Any

from .base import ChatResponse, ToolCallRequest
from .errors import ProviderAPIError
from .messages import coerce_text


def parse_model_ids(payload: Any, *, service: str) -> list[str]:
    """Return model ids from an OpenAI-style list payload."""
    if isinstance(payload, dict):
        items = payload.get("data")
        if items is None and isinstance(payload.get("models"), list):
            items = payload["models"]
    elif isinstance(payload, list):
        items = payload
    else:
        items = None
    if not isinstance(items, list):
        raise ProviderAPIError(f"{service} model list had an unexpected shape")

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


def parse_chat_response(payload: Any, *, service: str) -> ChatResponse:
    """Normalize the first choice of a chat-completion response."""
    if not isinstance(payload, dict):
        raise ProviderAPIError(f"{service} chat response had an unexpected shape")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderAPIError(f"{service} chat response did not include choices")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise ProviderAPIError(f"{service} chat response had an unexpected choice")
    message = choice.get("message")
    if not isinstance(message, dict):
        raise ProviderAPIError(f"{service} chat response did not include a message")
    finish = choice.get("finish_reason")
    return ChatResponse(
        content=coerce_text(message.get("content")),
        tool_calls=tool_calls_from_openai(message.get("tool_calls")),
        finish_reason=finish if isinstance(finish, str) else None,
    )


def tool_calls_from_openai(raw: Any) -> list[ToolCallRequest]:
    """Convert OpenAI ``tool_calls`` into :class:`ToolCallRequest` values."""
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
                arguments=arguments_from_openai(function.get("arguments")),
            )
        )
    return calls


def arguments_from_openai(raw: Any) -> dict[str, Any]:
    """Parse a tool-call ``arguments`` string or object."""
    if isinstance(raw, dict):
        return raw
    if raw is None or raw == "":
        return {}
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {"_raw": raw[:2000]}
        if isinstance(parsed, dict):
            return parsed
        return {"value": parsed}
    return {"value": raw}

"""Convert conversation content into OpenAI chat-completion messages.

This module does not import Home Assistant. It duck-types chat-log objects
(``role``, ``content``, ``tool_calls``, ``tool_call_id``, ``result``) and also
accepts plain dictionaries, so the conversion can be unit-tested on its own.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any


def openai_messages_from_contents(contents: Sequence[Any]) -> list[dict[str, Any]]:
    """Convert a chat log into OpenAI ``messages``."""
    messages: list[dict[str, Any]] = []
    for item in contents:
        role = _get(item, "role")
        if role == "system":
            messages.append(
                {"role": "system", "content": _text(_get(item, "content")) or ""}
            )
        elif role == "user":
            messages.append(
                {"role": "user", "content": _text(_get(item, "content")) or ""}
            )
        elif role == "assistant":
            messages.append(_assistant_message(item))
        elif role in {"tool_result", "tool"}:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": str(_get(item, "tool_call_id") or ""),
                    "content": _result_text(_get(item, "result")),
                }
            )
    return messages


def function_tool(
    name: str, description: str | None, parameters: Mapping[str, Any]
) -> dict[str, Any]:
    """Build one OpenAI function-tool definition."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description or name,
            "parameters": dict(parameters),
        },
    }


def coerce_text(content: Any) -> str | None:
    """Flatten a string or a list of text parts into one string."""
    return _text(content)


def _assistant_message(item: Any) -> dict[str, Any]:
    tool_calls = _get(item, "tool_calls") or []
    message: dict[str, Any] = {
        "role": "assistant",
        "content": _text(_get(item, "content")),
    }
    if tool_calls:
        message["tool_calls"] = [_tool_call(call) for call in tool_calls]
    elif message["content"] is None:
        message["content"] = ""
    return message


def _tool_call(call: Any) -> dict[str, Any]:
    if isinstance(call, Mapping):
        name = call.get("tool_name") or call.get("name") or ""
        arguments = call.get("tool_args")
        if arguments is None and isinstance(call.get("function"), Mapping):
            function = call["function"]
            name = function.get("name") or name
            arguments = function.get("arguments")
        call_id = call.get("id") or "call"
    else:
        name = getattr(call, "tool_name", "") or ""
        arguments = getattr(call, "tool_args", {})
        call_id = getattr(call, "id", None) or "call"
    if not isinstance(arguments, str):
        payload = arguments if isinstance(arguments, Mapping) else {}
        arguments = json.dumps(dict(payload), ensure_ascii=False, default=str)
    return {
        "id": str(call_id),
        "type": "function",
        "function": {"name": str(name), "arguments": arguments},
    }


def _result_text(result: Any) -> str:
    if isinstance(result, Mapping) and "data" in result:
        payload = {
            "data": result.get("data"),
            "error": bool(result.get("error", False)),
        }
    elif result is None:
        payload = {"data": None, "error": True}
    else:
        payload = {
            "data": _get(result, "data"),
            "error": bool(_get(result, "error")),
        }
    return json.dumps(payload, ensure_ascii=False, default=str)


def _text(content: Any) -> str | None:
    if content is None:
        return None
    if isinstance(content, str):
        return content
    if isinstance(content, Sequence) and not isinstance(content, (bytes, bytearray)):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, Mapping):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        joined = "".join(parts)
        return joined or None
    return str(content)


def _get(item: Any, key: str) -> Any:
    if isinstance(item, Mapping):
        return item.get(key)
    return getattr(item, key, None)

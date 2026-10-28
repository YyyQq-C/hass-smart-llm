"""Convert OpenAI chat messages into an Anthropic Messages request."""

from __future__ import annotations

import json
from typing import Any

from ..const import ANTHROPIC_MAX_TOKENS


def build_anthropic_body(
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    *,
    max_tokens: int = ANTHROPIC_MAX_TOKENS,
) -> dict[str, Any]:
    """Build a ``POST /v1/messages`` body from OpenAI-style messages."""
    system_parts: list[str] = []
    converted: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role == "system":
            text = _plain_text(message.get("content"))
            if text:
                system_parts.append(text)
            continue
        block = _message_block(message)
        if block is None:
            continue
        if converted and converted[-1]["role"] == block["role"]:
            converted[-1] = _merge(converted[-1], block)
        else:
            converted.append(block)

    if not converted or converted[0]["role"] != "user":
        raise ValueError("Anthropic conversations must start with a user message")

    body: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": converted,
    }
    if system_parts:
        body["system"] = "\n\n".join(system_parts)
    anthropic_tools = _tools(tools)
    if anthropic_tools:
        body["tools"] = anthropic_tools
    return body


def _message_block(message: dict[str, Any]) -> dict[str, Any] | None:
    role = message.get("role")
    if role == "user":
        text = _plain_text(message.get("content")) or ""
        return {"role": "user", "content": text}
    if role == "assistant":
        blocks: list[dict[str, Any]] = []
        text = _plain_text(message.get("content"))
        if text:
            blocks.append({"type": "text", "text": text})
        for call in message.get("tool_calls") or []:
            tool_use = _tool_use(call)
            if tool_use is not None:
                blocks.append(tool_use)
        if not blocks:
            return None
        return {"role": "assistant", "content": blocks}
    if role in {"tool", "tool_result"}:
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": str(message.get("tool_call_id") or ""),
                    "content": _plain_text(message.get("content")) or "",
                }
            ],
        }
    return None


def _tool_use(call: Any) -> dict[str, Any] | None:
    if not isinstance(call, dict):
        return None
    function = call.get("function")
    if not isinstance(function, dict):
        function = {}
    name = function.get("name") or call.get("name") or ""
    if not isinstance(name, str) or not name:
        return None
    call_id = call.get("id")
    if not isinstance(call_id, str) or not call_id:
        call_id = "toolu_0"
    return {
        "type": "tool_use",
        "id": call_id,
        "name": name,
        "input": _input(function.get("arguments")),
    }


def _input(raw: Any) -> dict[str, Any]:
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


def _tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not tools:
        return []
    converted: list[dict[str, Any]] = []
    for tool in tools:
        function = tool.get("function") if isinstance(tool, dict) else None
        if not isinstance(function, dict):
            function = tool if isinstance(tool, dict) else None
        if not isinstance(function, dict):
            continue
        name = function.get("name")
        if not isinstance(name, str) or not name:
            continue
        parameters = function.get("parameters") or function.get("input_schema")
        if not isinstance(parameters, dict):
            parameters = {"type": "object", "properties": {}}
        description = function.get("description")
        converted.append(
            {
                "name": name,
                "description": description if isinstance(description, str) else name,
                "input_schema": parameters,
            }
        )
    return converted


def _merge(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": left["role"],
        "content": _as_blocks(left["content"]) + _as_blocks(right["content"]),
    }


def _as_blocks(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, list):
        return [item for item in content if isinstance(item, dict)]
    text = _plain_text(content)
    if not text:
        return []
    return [{"type": "text", "text": text}]


def _plain_text(content: Any) -> str | None:
    if content is None:
        return None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts) or None
    return str(content)

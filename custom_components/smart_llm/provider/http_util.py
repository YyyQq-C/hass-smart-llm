"""Small HTTP helpers shared by the Cursor clients."""

from __future__ import annotations

import json
from typing import Any

from aiohttp import ClientResponse


async def read_body(response: ClientResponse) -> Any:
    """Return parsed JSON, or a truncated raw wrapper when the body is not JSON."""
    text = await response.text()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"_raw": text[:500]}


def error_message(payload: Any, status: int) -> str:
    """Pull a short, log-safe message out of an API error body."""
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])[:500]
        if isinstance(error, str) and error:
            return error[:500]
        message = payload.get("message")
        if isinstance(message, str) and message:
            return message[:500]
    return f"HTTP {status}"

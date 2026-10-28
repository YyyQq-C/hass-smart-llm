"""Small HTTP helpers shared by provider clients."""

from __future__ import annotations

import json
from typing import Any

from aiohttp import ClientError, ClientResponse, ClientSession, ClientTimeout

from .errors import ProviderAPIError, ProviderAuthError


async def read_body(response: ClientResponse) -> Any:
    """Return parsed JSON, or a truncated raw wrapper when the body is not JSON."""
    text = await response.text()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"_raw": text[:500]}


async def async_request_json(
    session: ClientSession,
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    json_body: dict[str, Any] | None,
    timeout: ClientTimeout,
    secret: str,
    service: str,
) -> Any:
    """Perform one JSON request. Exception text never includes ``secret``."""
    try:
        async with session.request(
            method,
            url,
            headers=headers,
            json=json_body,
            timeout=timeout,
        ) as response:
            payload = await read_body(response)
            status = response.status
    except TimeoutError as err:
        raise ProviderAPIError(f"{service} timed out", status=None) from err
    except ClientError as err:
        raise ProviderAPIError(f"Could not reach {service}", status=None) from err

    if status in {401, 403}:
        raise ProviderAuthError(f"{service} rejected the API key", status=status)
    if status >= 400:
        raise ProviderAPIError(
            redact_secret(error_message(payload, status), secret),
            status=status,
        )
    if not isinstance(payload, (dict, list)):
        raise ProviderAPIError(f"{service} returned an unreadable response")
    return payload


def redact_secret(message: str, secret: str) -> str:
    """Remove a credential if an error body echoed it. Never log the secret."""
    if not message or not secret:
        return message
    return message.replace(secret, "••••")


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

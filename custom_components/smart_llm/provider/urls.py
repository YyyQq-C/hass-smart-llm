"""Base URL normalization for OpenAI-compatible and Anthropic endpoints.

Official mode ignores a custom URL and uses the provider default. Compatible
mode keeps the same request style and only changes the host. An
OpenAI-compatible custom base URL may omit the API key; the client then
omits the Authorization header. ``http`` and ``https`` are both accepted, so
a local ``/v1`` base keeps its scheme.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from ..const import (
    CONF_BASE_URL,
    CONF_BRIDGE_BASE_URL,
    CONF_CONNECTION_MODE,
    CONNECTION_COMPATIBLE,
    DEFAULT_ANTHROPIC_BASE_URL,
    DEFAULT_BRIDGE_BASE_URL,
    DEFAULT_OPENAI_BASE_URL,
    PROVIDER_ANTHROPIC,
    PROVIDER_CURSOR,
    PROVIDER_OPENAI,
)


def normalize_openai_base_url(url: str) -> str:
    """Canonicalize an OpenAI-compatible base URL so it ends at ``/v1``.

    A host with no path gets ``/v1``. A path that already ends in ``/v1`` is
    kept, so proxies such as ``https://example.test/api/v1`` still work.
    """
    parsed, path = _split_base(url)
    for suffix in ("/chat/completions", "/models"):
        if path.endswith(suffix):
            path = path[: -len(suffix)].rstrip("/")
    if path in {"", "/"}:
        path = "/v1"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def normalize_anthropic_base_url(url: str) -> str:
    """Canonicalize an Anthropic host. Paths are ``/v1/messages`` and ``/v1/models``.

    A trailing ``/v1`` is removed so either the bare host or a ``/v1`` paste
    reaches the same routes.
    """
    parsed, path = _split_base(url)
    for suffix in ("/v1/messages", "/v1/models"):
        if path.endswith(suffix):
            path = path[: -len(suffix)].rstrip("/")
    if path.endswith("/v1"):
        path = path[: -len("/v1")].rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def resolve_base_url(provider: str, options: Mapping[str, Any]) -> str:
    """Return the base URL a stored config entry should call."""
    if provider == PROVIDER_CURSOR:
        raw = str(options.get(CONF_BRIDGE_BASE_URL) or DEFAULT_BRIDGE_BASE_URL)
        try:
            return normalize_openai_base_url(raw)
        except ValueError as err:
            raise ValueError(str(err).replace("API base URL", "Cursor Bridge URL")) from err

    mode = str(options.get(CONF_CONNECTION_MODE) or "")
    custom = str(options.get(CONF_BASE_URL) or "").strip()
    if provider == PROVIDER_ANTHROPIC:
        if mode == CONNECTION_COMPATIBLE:
            return normalize_anthropic_base_url(custom)
        return DEFAULT_ANTHROPIC_BASE_URL
    if provider == PROVIDER_OPENAI:
        if mode == CONNECTION_COMPATIBLE:
            return normalize_openai_base_url(custom)
        return DEFAULT_OPENAI_BASE_URL
    raise ValueError(f"Unknown Smart LLM provider: {provider}")


def _split_base(url: str) -> tuple[Any, str]:
    candidate = url.strip()
    if not candidate:
        raise ValueError("API base URL is empty")
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("API base URL must be an http(s) URL")
    if parsed.username or parsed.password:
        raise ValueError("API base URL must not include credentials")
    return parsed, parsed.path.rstrip("/")

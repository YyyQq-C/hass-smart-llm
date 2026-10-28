"""Validate config-flow fields that do not need Home Assistant.

The config and options flows call these helpers. Tests cover the same
branches the forms submit: API key, official vs custom base URL, and model id.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_CONNECTION_MODE,
    CONNECTION_COMPATIBLE,
    CONNECTION_OFFICIAL,
    DEFAULT_ANTHROPIC_BASE_URL,
    DEFAULT_OPENAI_BASE_URL,
    PROVIDER_ANTHROPIC,
    PROVIDER_OPENAI,
    default_model_for,
)
from .provider.urls import normalize_anthropic_base_url, normalize_openai_base_url


@dataclass(frozen=True, slots=True)
class ParsedConnection:
    """Request style plus the base URL the client should call."""

    mode: str
    base_url: str


def parse_api_key(user_input: Mapping[str, Any]) -> tuple[str | None, dict[str, str]]:
    """Return the pasted key, or a field error. The key is not logged."""
    key = str(user_input.get(CONF_API_KEY) or "").strip()
    if not key or any(char.isspace() for char in key):
        return None, {CONF_API_KEY: "invalid_api_key"}
    return key, {}


def suggested_model(provider: str, models: list[str]) -> str:
    """Prefer the provider default when the list contains it."""
    preferred = default_model_for(provider)
    if preferred in models:
        return preferred
    if models:
        return models[0]
    return preferred


def parse_model_id(raw: Any) -> str | None:
    """Return a model id, or None when it is blank or contains whitespace."""
    text = str(raw or "").strip()
    if not text or any(char.isspace() for char in text):
        return None
    return text


def parse_connection(
    provider: str, user_input: Mapping[str, Any]
) -> tuple[ParsedConnection | None, dict[str, str]]:
    """Validate official vs custom base URL for OpenAI or Anthropic.

    Official mode uses the provider cloud endpoint and ignores a typed URL.
    Compatible mode requires an http(s) base URL and keeps the standard header.
    """
    if provider not in {PROVIDER_OPENAI, PROVIDER_ANTHROPIC}:
        return None, {CONF_CONNECTION_MODE: "invalid_connection_mode"}

    mode = str(user_input.get(CONF_CONNECTION_MODE) or CONNECTION_OFFICIAL).strip()
    if mode not in {CONNECTION_OFFICIAL, CONNECTION_COMPATIBLE}:
        return None, {CONF_CONNECTION_MODE: "invalid_connection_mode"}

    if mode == CONNECTION_OFFICIAL:
        base = (
            DEFAULT_ANTHROPIC_BASE_URL
            if provider == PROVIDER_ANTHROPIC
            else DEFAULT_OPENAI_BASE_URL
        )
        return ParsedConnection(mode=mode, base_url=base), {}

    raw = str(user_input.get(CONF_BASE_URL) or "").strip()
    if not raw:
        return None, {CONF_BASE_URL: "invalid_url"}
    try:
        if provider == PROVIDER_ANTHROPIC:
            base = normalize_anthropic_base_url(raw)
        else:
            base = normalize_openai_base_url(raw)
    except ValueError:
        return None, {CONF_BASE_URL: "invalid_url"}
    return ParsedConnection(mode=mode, base_url=base), {}

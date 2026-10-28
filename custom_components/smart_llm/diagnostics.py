"""Diagnostics that never include the Cursor API key."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .const import (
    CONF_API_KEY_ENCRYPTED,
    CONF_API_KEY_EXPIRES_AT,
    CONF_AVAILABLE_MODELS,
    CONF_BRIDGE_BASE_URL,
    CONF_CONNECTION_MODE,
    CONF_EMAIL,
    CONF_MODEL,
    CONF_PROVIDER,
    PROVIDER_CURSOR,
)
from .identity import mask_email
from .provider.cursor_usage import usage_diagnostics
from .provider.urls import resolve_base_url


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: Any
) -> dict[str, Any]:
    """Return redacted diagnostics for a config entry."""
    runtime = getattr(entry, "runtime_data", None)
    masked = getattr(runtime, "masked_key", None) if runtime is not None else None
    provider = entry.data.get(CONF_PROVIDER)
    try:
        base_url = resolve_base_url(provider or PROVIDER_CURSOR, entry.options)
    except ValueError:
        base_url = None
    return {
        "provider": provider,
        "email": mask_email(entry.data.get(CONF_EMAIL)),
        "api_key_stored": bool(entry.data.get(CONF_API_KEY_ENCRYPTED)),
        "api_key_masked": masked,
        "api_key_expires_at": entry.data.get(CONF_API_KEY_EXPIRES_AT),
        "connection_mode": entry.options.get(CONF_CONNECTION_MODE),
        "base_url": base_url,
        "bridge_base_url": entry.options.get(CONF_BRIDGE_BASE_URL),
        "model": entry.options.get(CONF_MODEL),
        "available_models": entry.options.get(CONF_AVAILABLE_MODELS),
        "cursor_usage": usage_diagnostics(
            getattr(runtime, "usage", None) if runtime is not None else None
        ),
    }

"""Diagnostics that never include the Cursor API key."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .const import (
    CONF_API_KEY_ENCRYPTED,
    CONF_API_KEY_EXPIRES_AT,
    CONF_AVAILABLE_MODELS,
    CONF_BRIDGE_BASE_URL,
    CONF_EMAIL,
    CONF_MODEL,
    CONF_PROVIDER,
)
from .identity import mask_email


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: Any
) -> dict[str, Any]:
    """Return redacted diagnostics for a config entry."""
    runtime = getattr(entry, "runtime_data", None)
    masked = getattr(runtime, "masked_key", None) if runtime is not None else None
    return {
        "provider": entry.data.get(CONF_PROVIDER),
        "email": mask_email(entry.data.get(CONF_EMAIL)),
        "api_key_stored": bool(entry.data.get(CONF_API_KEY_ENCRYPTED)),
        "api_key_masked": masked,
        "api_key_expires_at": entry.data.get(CONF_API_KEY_EXPIRES_AT),
        "bridge_base_url": entry.options.get(CONF_BRIDGE_BASE_URL),
        "model": entry.options.get(CONF_MODEL),
        "available_models": entry.options.get(CONF_AVAILABLE_MODELS),
    }

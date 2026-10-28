"""Smart LLM integration: a pluggable conversation agent for Assist."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .const import (
    CONF_API_KEY_ENCRYPTED,
    CONF_BRIDGE_BASE_URL,
    CONF_EMAIL,
    CONF_PROVIDER,
    DEFAULT_BRIDGE_BASE_URL,
    PROVIDER_CURSOR,
)
from .crypto import DecryptionError, mask_secret
from .provider.base import ChatProvider
from .provider.registry import create_chat_provider
from .secrets import async_decrypt

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class SmartLLMRuntime:
    """In-memory data for one config entry. The API key stays inside the provider."""

    provider: ChatProvider
    masked_key: str
    email: str | None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Smart LLM from a config entry."""
    from homeassistant.const import Platform
    from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryError
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    provider_id = entry.data.get(CONF_PROVIDER, PROVIDER_CURSOR)
    encrypted = entry.data.get(CONF_API_KEY_ENCRYPTED)
    if not encrypted:
        raise ConfigEntryAuthFailed("Cursor authorization required")

    try:
        api_key = await async_decrypt(hass, encrypted)
    except DecryptionError as err:
        raise ConfigEntryAuthFailed(
            "Stored Cursor API key could not be decrypted"
        ) from err

    base_url = entry.options.get(CONF_BRIDGE_BASE_URL, DEFAULT_BRIDGE_BASE_URL)
    try:
        provider = create_chat_provider(
            provider_id,
            session=async_get_clientsession(hass),
            api_key=api_key,
            base_url=base_url,
        )
    except ValueError as err:
        raise ConfigEntryError("Invalid Cursor Bridge URL") from err

    entry.runtime_data = SmartLLMRuntime(
        provider=provider,
        masked_key=mask_secret(api_key),
        email=entry.data.get(CONF_EMAIL),
    )
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(
        entry, [Platform.CONVERSATION]
    )
    _LOGGER.info("Smart LLM is ready (provider=%s)", provider_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    from homeassistant.const import Platform

    return await hass.config_entries.async_unload_platforms(
        entry, [Platform.CONVERSATION]
    )


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload after options or credentials change."""
    await hass.config_entries.async_reload(entry.entry_id)

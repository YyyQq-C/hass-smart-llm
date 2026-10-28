"""Smart LLM integration: a pluggable conversation agent for Assist."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .const import (
    CONF_API_KEY_ENCRYPTED,
    CONF_EMAIL,
    CONF_PROVIDER,
    PROVIDER_CURSOR,
)
from .crypto import DecryptionError, mask_secret
from .identity import account_switch_in_progress, display_account, public_title
from .provider.base import ChatProvider
from .provider.registry import create_chat_provider
from .provider.urls import resolve_base_url
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
    email: str | None  # masked for display; never the full address
    base_url: str


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Smart LLM from a config entry."""
    from homeassistant.const import Platform
    from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryError
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    provider_id = entry.data.get(CONF_PROVIDER, PROVIDER_CURSOR)
    visible_title = public_title(entry.title)
    if entry.title != visible_title:
        hass.config_entries.async_update_entry(entry, title=visible_title)

    encrypted = entry.data.get(CONF_API_KEY_ENCRYPTED)
    if not encrypted:
        if account_switch_in_progress(hass.data, entry.entry_id):
            _LOGGER.info("Smart LLM is waiting for another Cursor account")
            return False
        if provider_id == PROVIDER_CURSOR:
            raise ConfigEntryAuthFailed("Cursor authorization required")
        raise ConfigEntryAuthFailed("API key required")

    try:
        api_key = await async_decrypt(hass, encrypted)
    except DecryptionError as err:
        if provider_id == PROVIDER_CURSOR:
            raise ConfigEntryAuthFailed(
                "Stored Cursor API key could not be decrypted"
            ) from err
        raise ConfigEntryAuthFailed("Stored API key could not be decrypted") from err

    try:
        base_url = resolve_base_url(provider_id, entry.options)
        provider = create_chat_provider(
            provider_id,
            session=async_get_clientsession(hass),
            api_key=api_key,
            base_url=base_url,
        )
    except ValueError as err:
        if provider_id == PROVIDER_CURSOR:
            raise ConfigEntryError("Invalid Cursor Bridge URL") from err
        raise ConfigEntryError("Invalid API base URL") from err

    stored_email = entry.data.get(CONF_EMAIL)
    entry.runtime_data = SmartLLMRuntime(
        provider=provider,
        masked_key=mask_secret(api_key),
        email=display_account(stored_email) if stored_email else None,
        base_url=base_url,
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

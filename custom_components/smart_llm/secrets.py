"""Home Assistant wrappers around the install-bound secret encryption."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .const import DATA_KEY_MATERIAL, STORAGE_DIR
from .crypto import decrypt_secret, encrypt_secret, load_key_material

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

__all__ = ["async_decrypt", "async_encrypt", "async_key_material"]


async def async_key_material(hass: HomeAssistant) -> bytes:
    """Return cached key material for this Home Assistant instance."""
    cached = hass.data.get(DATA_KEY_MATERIAL)
    if isinstance(cached, bytes) and cached:
        return cached
    storage_dir = hass.config.path(STORAGE_DIR)
    material = await hass.async_add_executor_job(load_key_material, storage_dir)
    hass.data[DATA_KEY_MATERIAL] = material
    return material


async def async_encrypt(hass: HomeAssistant, plaintext: str) -> str:
    """Encrypt a secret for storage in the config entry."""
    material = await async_key_material(hass)
    return await hass.async_add_executor_job(encrypt_secret, plaintext, material)


async def async_decrypt(hass: HomeAssistant, token: str) -> str:
    """Decrypt a secret stored in the config entry."""
    material = await async_key_material(hass)
    return await hass.async_add_executor_job(decrypt_secret, token, material)

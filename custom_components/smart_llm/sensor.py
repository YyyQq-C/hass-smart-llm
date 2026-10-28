"""Cursor allowance sensors.

These entities exist only for a Cursor config entry that has a stored user
API key. They read ``GetCurrentPeriodUsage``. OpenAI, Anthropic, and local
servers are not given allowance sensors: those APIs do not return a
subscription balance to this integration.

A failed refresh leaves the sensors unavailable. It does not start reauth.
Chat can still work when the usage call does not.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    AGENT_NAME,
    CONF_API_KEY_ENCRYPTED,
    CURSOR_USAGE_INTERVAL_MINUTES,
    DOMAIN,
    PROVIDER_CONFIG_URL,
    PROVIDER_CURSOR,
)
from .crypto import DecryptionError
from .provider.cursor_usage import (
    AccessTokenCache,
    CursorPeriodUsage,
    async_fetch_cursor_period_usage,
)
from .provider.errors import ProviderAPIError
from .secrets import async_decrypt

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add allowance sensors for one Cursor entry."""
    if not entry.data.get(CONF_API_KEY_ENCRYPTED):
        return
    cache = AccessTokenCache()

    async def _async_update() -> CursorPeriodUsage:
        try:
            api_key = await async_decrypt(hass, entry.data[CONF_API_KEY_ENCRYPTED])
        except DecryptionError as err:
            raise UpdateFailed("Stored Cursor API key could not be decrypted") from err
        try:
            usage = await async_fetch_cursor_period_usage(
                async_get_clientsession(hass),
                api_key,
                cache=cache,
            )
        except ProviderAPIError as err:
            raise UpdateFailed(str(err)) from err
        runtime = getattr(entry, "runtime_data", None)
        if runtime is not None:
            runtime.usage = usage
        return usage

    coordinator: DataUpdateCoordinator[CursorPeriodUsage] = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="Smart LLM Cursor usage",
        update_method=_async_update,
        update_interval=timedelta(minutes=CURSOR_USAGE_INTERVAL_MINUTES),
    )
    async_add_entities(
        [
            CursorRemainingSensor(coordinator, entry),
            CursorPercentSensor(coordinator, entry),
            CursorResetSensor(coordinator, entry),
        ]
    )
    task = hass.async_create_task(coordinator.async_refresh())
    entry.async_on_unload(task.cancel)


class _CursorUsageEntity(CoordinatorEntity[DataUpdateCoordinator[CursorPeriodUsage]], SensorEntity):
    """One field from the latest billing period."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[CursorPeriodUsage],
        entry: ConfigEntry,
        unique_suffix: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}-{unique_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=AGENT_NAME,
            manufacturer="Smart LLM",
            model="Cursor",
            configuration_url=PROVIDER_CONFIG_URL.get(PROVIDER_CURSOR),
        )

    @property
    def _usage(self) -> CursorPeriodUsage | None:
        data = self.coordinator.data
        if isinstance(data, CursorPeriodUsage):
            return data
        return None


class CursorRemainingSensor(_CursorUsageEntity):
    """Included allowance still left, in USD."""

    _attr_translation_key = "included_usage_remaining"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "USD"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:cash"

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[CursorPeriodUsage],
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry, "included-usage-remaining")

    @property
    def native_value(self) -> float | None:
        usage = self._usage
        if usage is None:
            return None
        return usage.remaining_usd

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        usage = self._usage
        if usage is None:
            return {}
        return {
            "remaining_cents": usage.remaining_cents,
            "limit_cents": usage.limit_cents,
            "limit_usd": usage.limit_usd,
            "total_spend_cents": usage.total_spend_cents,
            "included_spend_cents": usage.included_spend_cents,
            "display_message": usage.display_message,
        }


class CursorPercentSensor(_CursorUsageEntity):
    """``totalPercentUsed`` as Cursor returned it."""

    _attr_translation_key = "included_usage_used"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:percent"

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[CursorPeriodUsage],
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry, "included-usage-used")

    @property
    def native_value(self) -> float | None:
        usage = self._usage
        if usage is None:
            return None
        return usage.total_percent_used

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        usage = self._usage
        if usage is None:
            return {}
        return {
            "auto_percent_used": usage.auto_percent_used,
            "api_percent_used": usage.api_percent_used,
            "display_message": usage.display_message,
        }


class CursorResetSensor(_CursorUsageEntity):
    """When the current billing period ends."""

    _attr_translation_key = "allowance_resets"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:calendar-clock"

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[CursorPeriodUsage],
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry, "allowance-resets")

    @property
    def native_value(self) -> Any:
        usage = self._usage
        if usage is None:
            return None
        return usage.billing_cycle_end

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        usage = self._usage
        if usage is None or usage.billing_cycle_start is None:
            return {}
        return {"billing_cycle_start": usage.billing_cycle_start.isoformat()}

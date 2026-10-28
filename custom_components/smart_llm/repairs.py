"""Repair flow that starts Cursor re-authorization."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .expiry_notice import start_reauth_once


class CursorKeyRepairFlow(RepairsFlow):
    """Ask the user to mint a new Cursor API key."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm, then open the existing re-authorize flow."""
        data = self.data or {}
        account = str(data.get("account") or "Cursor")
        expires = str(data.get("expires") or "")
        if user_input is not None:
            entry_id = data.get("entry_id")
            if isinstance(entry_id, str):
                entry = self.hass.config_entries.async_get_entry(entry_id)
                if entry is not None:
                    start_reauth_once(self.hass, entry)
            # Abort leaves the repair in place. Home Assistant deletes the
            # issue when a fix flow creates an entry, which would hide it
            # before the new key is actually saved.
            return self.async_abort(reason="reauth_started")
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({}),
            description_placeholders={"account": account, "expires": expires},
        )


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create the fix flow for a Cursor API key expiry issue."""
    return CursorKeyRepairFlow()

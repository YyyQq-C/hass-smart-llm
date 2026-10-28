"""Repair issue and persistent notification for a Cursor API key expiry.

The same notice id is updated when the key moves from "expires soon" to
"expired". A poll that sees the same stage does not create another one.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import CONF_EMAIL, CONF_PROVIDER, DOMAIN, PROVIDER_CURSOR
from .identity import display_account
from .key_expiry import (
    EXPIRY_EXPIRED,
    classify_key_expiry,
    format_expiry_clock,
    notice_action,
)

_LOGGER = logging.getLogger(__name__)

DATA_KEY_EXPIRY_NOTICE = "smart_llm_key_expiry_notice"

_NOTICE = {
    "en": {
        "title": "Smart LLM",
        "soon": (
            "The Cursor API key for {account} expires on {expires}. "
            "Open the Smart LLM options and choose Re-authorize to mint a new key."
        ),
        "expired": (
            "The Cursor API key for {account} expired on {expires}. "
            "Assist will not use it until you re-authorize in the Smart LLM options."
        ),
    },
    "zh": {
        "title": "Smart LLM",
        "soon": (
            "{account} 的 Cursor API 密钥将于 {expires} 到期。"
            "请打开 Smart LLM 选项并选择重新授权，以签发新密钥。"
        ),
        "expired": (
            "{account} 的 Cursor API 密钥已于 {expires} 到期。"
            "在 Smart LLM 选项里重新授权之前，Assist 不会再使用它。"
        ),
    },
}


def issue_id_for(entry_id: str) -> str:
    """Stable repairs issue id for one config entry."""
    return f"cursor_api_key_{entry_id}"


def notification_id_for(entry_id: str) -> str:
    """Stable persistent-notification id for one config entry."""
    return f"smart_llm_cursor_key_{entry_id}"


def start_reauth_once(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Start a reauth flow unless one is already in progress for this entry."""
    for flow in hass.config_entries.flow.async_progress():
        context = flow.get("context") or {}
        if (
            context.get("source") == SOURCE_REAUTH
            and context.get("entry_id") == entry.entry_id
        ):
            return
    entry.async_start_reauth(hass)


async def async_sync_cursor_key_notice(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Publish, update, or dismiss the expiry notice for this entry."""
    try:
        _sync_cursor_key_notice(hass, entry)
    except Exception:
        _LOGGER.exception("Could not update the Cursor API key expiry notice")


async def async_clear_cursor_key_notice(hass: HomeAssistant, entry_id: str) -> None:
    """Drop the notice when the config entry is removed."""
    try:
        _dismiss(hass, entry_id)
    except Exception:
        _LOGGER.exception("Could not clear the Cursor API key expiry notice")
    _states(hass).pop(entry_id, None)


def _sync_cursor_key_notice(hass: HomeAssistant, entry: ConfigEntry) -> None:
    if entry.data.get(CONF_PROVIDER, PROVIDER_CURSOR) != PROVIDER_CURSOR:
        _dismiss(hass, entry.entry_id)
        _states(hass)[entry.entry_id] = "clear"
        return

    status = classify_key_expiry(entry.data, _now_ms())
    states = _states(hass)
    action = notice_action(states.get(entry.entry_id), status.state)
    if action == "keep":
        return
    if action == "clear":
        _dismiss(hass, entry.entry_id)
        states[entry.entry_id] = "clear"
        return

    account = display_account(entry.data.get(CONF_EMAIL))
    when = format_expiry_clock(
        status.expires_at_ms or 0,
        time_zone=getattr(hass.config, "time_zone", None),
    )
    language = _language(hass)
    message = _NOTICE[language][action].format(account=account, expires=when)
    _persistent_notification().async_create(
        hass,
        message,
        title=_NOTICE[language]["title"],
        notification_id=notification_id_for(entry.entry_id),
    )
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id_for(entry.entry_id),
        data={
            "entry_id": entry.entry_id,
            "account": account,
            "expires": when,
        },
        is_fixable=True,
        is_persistent=False,
        severity=(
            ir.IssueSeverity.ERROR
            if action == EXPIRY_EXPIRED
            else ir.IssueSeverity.WARNING
        ),
        translation_key=(
            "cursor_api_key_expired"
            if action == EXPIRY_EXPIRED
            else "cursor_api_key_expiring"
        ),
        translation_placeholders={"account": account, "expires": when},
    )
    states[entry.entry_id] = action


def _dismiss(hass: HomeAssistant, entry_id: str) -> None:
    ir.async_delete_issue(hass, DOMAIN, issue_id_for(entry_id))
    _persistent_notification().async_dismiss(hass, notification_id_for(entry_id))


def _states(hass: HomeAssistant) -> dict[str, str]:
    states = hass.data.get(DATA_KEY_EXPIRY_NOTICE)
    if not isinstance(states, dict):
        states = {}
        hass.data[DATA_KEY_EXPIRY_NOTICE] = states
    return states


def _language(hass: HomeAssistant) -> str:
    language = getattr(hass.config, "language", None) or "en"
    if str(language).lower().startswith("zh"):
        return "zh"
    return "en"


def _now_ms() -> int:
    import time

    return int(time.time() * 1000)


def _persistent_notification() -> Any:
    """Load the helper lazily so a missing component fails inside the guard."""
    from homeassistant.components import persistent_notification

    return persistent_notification

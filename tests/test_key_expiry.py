"""Stored Cursor key lifetime: permanent, finite, and legacy entries."""

from __future__ import annotations

from custom_components.smart_llm.const import (
    API_KEY_EXPIRY_LEAD_MS,
    CONF_API_KEY_ENCRYPTED,
    CONF_API_KEY_EXPIRES_AT,
    CONF_API_KEY_TTL,
)
from custom_components.smart_llm.key_expiry import (
    EXPIRY_ABSENT,
    EXPIRY_EXPIRED,
    EXPIRY_NEVER,
    EXPIRY_SOON,
    EXPIRY_UNKNOWN,
    EXPIRY_VALID,
    classify_key_expiry,
    expiry_label,
    format_expiry_clock,
    notice_action,
    stored_expiry_fields,
    ttl_to_milliseconds,
)

_NOW = 1_700_000_000_000
_KEY = {CONF_API_KEY_ENCRYPTED: "fernet-token"}


def test_named_lifetimes_match_the_mint_choices() -> None:
    assert ttl_to_milliseconds("never") is None
    assert ttl_to_milliseconds("30") == 30 * 24 * 60 * 60 * 1000
    assert ttl_to_milliseconds("90") == 90 * 24 * 60 * 60 * 1000
    assert ttl_to_milliseconds("180") == 180 * 24 * 60 * 60 * 1000
    assert ttl_to_milliseconds("365") == 365 * 24 * 60 * 60 * 1000


def test_permanent_storage_omits_the_timestamp() -> None:
    fields = stored_expiry_fields("never", 1_700_000_000_000)
    assert fields == {CONF_API_KEY_TTL: "never"}
    assert CONF_API_KEY_EXPIRES_AT not in fields

    finite = stored_expiry_fields("90", 1_700_000_000_000)
    assert finite[CONF_API_KEY_TTL] == "90"
    assert finite[CONF_API_KEY_EXPIRES_AT] == 1_700_000_000_000


def test_legacy_entries_without_an_expiry_are_not_expired() -> None:
    """A key from before this field existed must not be called expired."""
    assert classify_key_expiry(_KEY, _NOW).state == EXPIRY_UNKNOWN
    assert classify_key_expiry({}, _NOW).state == EXPIRY_ABSENT
    assert classify_key_expiry({**_KEY, CONF_API_KEY_EXPIRES_AT: True}, _NOW).state == (
        EXPIRY_UNKNOWN
    )
    assert classify_key_expiry({**_KEY, CONF_API_KEY_EXPIRES_AT: "90"}, _NOW).state == (
        EXPIRY_UNKNOWN
    )


def test_a_stored_timestamp_is_used_even_without_the_named_choice() -> None:
    """Entries minted before the selector still have api_key_expires_at."""
    soon = _NOW + API_KEY_EXPIRY_LEAD_MS
    assert classify_key_expiry(
        {**_KEY, CONF_API_KEY_EXPIRES_AT: soon}, _NOW
    ).state == EXPIRY_SOON
    assert classify_key_expiry(
        {**_KEY, CONF_API_KEY_EXPIRES_AT: soon + 1}, _NOW
    ).state == EXPIRY_VALID
    expired = classify_key_expiry(
        {**_KEY, CONF_API_KEY_EXPIRES_AT: _NOW}, _NOW
    )
    assert expired.state == EXPIRY_EXPIRED
    assert expired.expires_at_ms == _NOW


def test_permanent_wins_over_a_stale_timestamp() -> None:
    status = classify_key_expiry(
        {**_KEY, CONF_API_KEY_TTL: "never", CONF_API_KEY_EXPIRES_AT: _NOW - 1},
        _NOW,
    )
    assert status.state == EXPIRY_NEVER
    assert status.expires_at_ms is None


def test_notices_fire_once_per_stage_and_not_on_every_poll() -> None:
    assert notice_action(None, EXPIRY_VALID) == "clear"
    assert notice_action("clear", EXPIRY_VALID) == "keep"
    assert notice_action(None, EXPIRY_UNKNOWN) == "clear"
    assert notice_action(None, EXPIRY_NEVER) == "clear"
    assert notice_action(None, EXPIRY_SOON) == EXPIRY_SOON
    assert notice_action(EXPIRY_SOON, EXPIRY_SOON) == "keep"
    assert notice_action(EXPIRY_SOON, EXPIRY_EXPIRED) == EXPIRY_EXPIRED
    assert notice_action(EXPIRY_EXPIRED, EXPIRY_EXPIRED) == "keep"
    assert notice_action(EXPIRY_EXPIRED, EXPIRY_VALID) == "clear"
    assert notice_action("clear", EXPIRY_ABSENT) == "keep"


def test_expiry_labels_follow_the_ui_language() -> None:
    from custom_components.smart_llm.key_expiry import KeyExpiry

    never = KeyExpiry(EXPIRY_NEVER, None)
    unknown = KeyExpiry(EXPIRY_UNKNOWN, None)
    soon = KeyExpiry(EXPIRY_SOON, _NOW)
    expired = KeyExpiry(EXPIRY_EXPIRED, _NOW)
    assert expiry_label(never, None, language="en") == "Permanent"
    assert expiry_label(never, None, language="zh-Hans") == "永久"
    assert expiry_label(unknown, None, language="en") == "Unknown"
    assert expiry_label(soon, "2023-11-14 22:13", language="en") == (
        "Expires 2023-11-14 22:13"
    )
    assert expiry_label(expired, "2023-11-14 22:13", language="zh") == (
        "已过期 2023-11-14 22:13"
    )
    assert "UTC" in format_expiry_clock(_NOW, time_zone="UTC")
    local = format_expiry_clock(_NOW, time_zone="Asia/Shanghai")
    assert local != format_expiry_clock(_NOW, time_zone="UTC")
    assert "UTC" not in local

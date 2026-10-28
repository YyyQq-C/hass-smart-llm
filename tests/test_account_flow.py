"""Logout, switch-account, and email masking.

These tests stay free of Home Assistant, matching the rest of the suite.
They cover the decisions the options flow and Assist card rely on.
"""

from __future__ import annotations

import json
from pathlib import Path

from custom_components.smart_llm.const import (
    AGENT_NAME,
    CONF_API_KEY_ENCRYPTED,
    CONF_API_KEY_EXPIRES_AT,
    CONF_EMAIL,
    CONF_MODEL,
    CONF_PROVIDER,
    PROVIDER_CURSOR,
)
from custom_components.smart_llm.identity import (
    account_switch_in_progress,
    clear_account_switch,
    credential_update_block,
    display_account,
    mark_account_switch,
    mask_email,
    options_with_refreshed_models,
    public_title,
    unique_id_for_login,
    without_stored_credentials,
)

_ROOT = Path(__file__).resolve().parents[1]
_COMPONENT = _ROOT / "custom_components" / "smart_llm"
_EMAIL = "yongqc@gmail.com"
_MASKED = "y**@g**.com"


def _stored_entry() -> dict[str, object]:
    return {
        CONF_PROVIDER: PROVIDER_CURSOR,
        CONF_API_KEY_ENCRYPTED: "fernet-token",
        CONF_API_KEY_EXPIRES_AT: 1_700_000_000_000,
        CONF_EMAIL: _EMAIL,
        "unrelated": "kept",
    }


def test_mask_email_hides_the_local_part_and_domain() -> None:
    """The UI mask keeps one character, the TLD, and nothing else."""
    assert mask_email(_EMAIL) == _MASKED
    assert mask_email(" Ada@Example.com ") == "A**@E**.com"
    assert mask_email("a@b.co.uk") == "a**@b**.uk"
    assert mask_email("solo@localhost") == "s**@l**"
    assert mask_email(None) is None
    assert mask_email("not-an-email") is None
    assert mask_email("@gmail.com") is None
    assert mask_email("user@") is None

    masked = mask_email(_EMAIL)
    assert masked is not None
    assert _EMAIL not in masked
    assert "yongqc" not in masked
    assert "gmail" not in masked


def test_display_account_never_returns_the_full_address() -> None:
    assert display_account(_EMAIL) == _MASKED
    assert display_account(None) == AGENT_NAME
    assert display_account("   ") == AGENT_NAME
    assert "@" not in AGENT_NAME


def test_public_title_drops_titles_that_embed_an_email() -> None:
    """Existing entries were titled `Cursor (name@domain)`."""
    assert public_title(f"Cursor ({_EMAIL})") == AGENT_NAME
    assert public_title(AGENT_NAME) == AGENT_NAME
    assert public_title(None) == AGENT_NAME
    assert public_title("Kitchen assistant") == "Kitchen assistant"


def test_logout_removes_key_expiry_and_email() -> None:
    cleared = without_stored_credentials(_stored_entry())
    assert CONF_API_KEY_ENCRYPTED not in cleared
    assert CONF_API_KEY_EXPIRES_AT not in cleared
    assert CONF_EMAIL not in cleared
    assert cleared[CONF_PROVIDER] == PROVIDER_CURSOR
    assert cleared["unrelated"] == "kept"


def test_reauth_can_keep_email_when_the_new_login_has_none() -> None:
    kept = without_stored_credentials(_stored_entry(), keep_email=True)
    assert kept[CONF_EMAIL] == _EMAIL
    assert CONF_API_KEY_ENCRYPTED not in kept
    assert CONF_API_KEY_EXPIRES_AT not in kept


def test_reauth_rejects_a_different_account_and_switch_allows_it() -> None:
    """Re-authorize stays on this entry. Switch account may replace it."""
    assert (
        credential_update_block(
            "ada@example.com",
            "other@example.com",
            allow_different_account=False,
        )
        == "wrong_account"
    )
    assert (
        credential_update_block(
            "ada@example.com",
            "Ada@Example.com",
            allow_different_account=False,
        )
        is None
    )
    assert (
        credential_update_block(
            "ada@example.com",
            "other@example.com",
            allow_different_account=True,
        )
        is None
    )

    switched = unique_id_for_login(
        "ada@example.com",
        "other@example.com",
        "crsr_new",
        allow_different_account=True,
    )
    assert switched == "other@example.com"
    same = unique_id_for_login(
        "ada@example.com",
        None,
        "crsr_new",
        allow_different_account=False,
    )
    assert same == "ada@example.com"


def test_switch_refreshes_models_and_keeps_a_model_that_is_still_offered() -> None:
    options = {
        CONF_MODEL: "composer",
        "bridge_base_url": "https://cursorbridge.dev/v1",
    }
    refreshed = options_with_refreshed_models(options, ["composer", "default"])
    assert refreshed is not None
    assert refreshed[CONF_MODEL] == "composer"
    assert "composer" in refreshed["available_models"]

    replaced = options_with_refreshed_models(options, ["default", "gpt"])
    assert replaced is not None
    assert replaced[CONF_MODEL] == "default"
    assert options_with_refreshed_models(options, None) is None
    assert options_with_refreshed_models(options, []) is None


def test_switch_flag_is_set_only_while_a_replacement_login_is_open() -> None:
    store: dict[str, object] = {}
    assert not account_switch_in_progress(store, "entry-1")
    mark_account_switch(store, "entry-1")
    assert account_switch_in_progress(store, "entry-1")
    assert not account_switch_in_progress(store, "entry-2")
    clear_account_switch(store, "entry-1")
    assert not account_switch_in_progress(store, "entry-1")


def test_assist_name_and_flow_steps_do_not_embed_the_email() -> None:
    """The conversation entity and entry title must not be built from an address."""
    conversation = (_COMPONENT / "conversation.py").read_text(encoding="utf-8")
    config_flow = (_COMPONENT / "config_flow.py").read_text(encoding="utf-8")
    assert "self._attr_name = AGENT_NAME" in conversation
    assert "entry.title" not in conversation
    assert "_entry_title" not in config_flow
    assert "Cursor ({" not in config_flow
    assert "async_step_logout" in config_flow
    assert "async_step_switch_account" in config_flow
    assert "async_step_switch_link" in config_flow
    assert "allow_different_account=True" in config_flow
    assert '"account": result.email' not in config_flow
    assert "display_account(result.email)" in config_flow


def test_translation_catalogs_offer_logout_and_switch_without_a_raw_email() -> None:
    catalogs = [
        _COMPONENT / "strings.json",
        _COMPONENT / "translations" / "en.json",
        _COMPONENT / "translations" / "zh-Hans.json",
    ]
    parsed = [json.loads(path.read_text(encoding="utf-8")) for path in catalogs]
    menu = parsed[0]["options"]["step"]["init"]["menu_options"]
    assert list(menu) == [
        "settings",
        "refresh_models",
        "reauth",
        "switch_account",
        "logout",
    ]
    for key in ("logout", "switch_account", "switch_link"):
        assert key in parsed[0]["options"]["step"]
    assert "switch_successful" in parsed[0]["options"]["abort"]
    assert "logged_out" in parsed[0]["options"]["abort"]

    def keys(value: object) -> list[str]:
        if isinstance(value, dict):
            found: list[str] = []
            for name, child in value.items():
                found.append(name)
                found.extend(keys(child))
            return found
        return []

    english_keys = keys(parsed[0])
    assert keys(parsed[1]) == english_keys
    assert keys(parsed[2]) == english_keys
    for blob in parsed:
        encoded = json.dumps(blob)
        assert _EMAIL not in encoded
        assert "@gmail.com" not in encoded
        assert "https://" not in encoded
        assert "http://" not in encoded

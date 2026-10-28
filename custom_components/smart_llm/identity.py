"""Account identity helpers that do not import Home Assistant."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, MutableMapping
from typing import Any

from .const import (
    AGENT_NAME,
    CONF_API_KEY_ENCRYPTED,
    CONF_API_KEY_EXPIRES_AT,
    CONF_API_KEY_TTL,
    CONF_AVAILABLE_MODELS,
    CONF_EMAIL,
    CONF_MODEL,
    DATA_SWITCH_IN_PROGRESS,
    DEFAULT_MODEL,
)

# Removed on logout and at the start of a switch-account login.
_CREDENTIAL_FIELDS = (
    CONF_API_KEY_ENCRYPTED,
    CONF_API_KEY_EXPIRES_AT,
    CONF_API_KEY_TTL,
    CONF_EMAIL,
)


def api_provider_unique_id(
    provider: str, api_key: str, *, base_url: str = ""
) -> str:
    """Stable id for one pasted API key. The raw key is not part of the result.

    A non-empty key ignores ``base_url``, so existing entries keep their id.
    An empty key (a local OpenAI-compatible server) includes the base URL so
    two hosts without a key are not treated as the same account.
    """
    material = api_key if api_key else f"\0{base_url}"
    digest = hashlib.sha256(f"{provider}\0{material}".encode("utf-8")).hexdigest()
    return f"{provider}-{digest[:16]}"


def account_unique_id(email: str | None, api_key: str) -> str:
    """Stable id for one Cursor account. Email wins over a key fingerprint."""
    if email and "@" in email:
        return email.strip().lower()
    return "cursor-" + hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:12]


def same_cursor_account(existing: str | None, email: str | None) -> bool:
    """Whether a reauth may update this entry.

    Placeholder ids (no email yet) can be upgraded. Two different emails cannot
    share one entry. Switch-account does not use this check.
    """
    if not existing or not email or "@" not in existing:
        return True
    return existing == email.strip().lower()


def mask_email(email: str | None) -> str | None:
    """Mask an address for the UI.

    ``yongqc@gmail.com`` becomes ``y**@g**.com``: first character of the local
    part, ``**``, ``@``, first character of the domain, ``**``, then the TLD.
    The full local part and the full domain name are never returned.
    """
    if not isinstance(email, str):
        return None
    text = email.strip()
    if text.count("@") != 1:
        return None
    local, domain = text.split("@")
    local = local.strip()
    domain = domain.strip().rstrip(".")
    if not local or not domain:
        return None
    if any(char.isspace() for char in local + domain):
        return None
    local_mask = f"{local[0]}**"
    if "." not in domain:
        return f"{local_mask}@{domain[0]}**"
    host, tld = domain.rsplit(".", 1)
    if not host or not tld:
        return None
    return f"{local_mask}@{host[0]}**.{tld}"


def display_account(email: str | None) -> str:
    """UI label for an account. A missing address stays the generic agent name."""
    return mask_email(email) or AGENT_NAME


def public_title(title: str | None) -> str:
    """Config-entry title safe to show in Home Assistant.

    Titles that contain ``@`` were built from a Cursor email (``Cursor (a@b.c)``).
    Those become the generic agent name. Any other custom title is kept.
    """
    if title and "@" not in title:
        return title
    return AGENT_NAME


def without_stored_credentials(
    data: Mapping[str, Any], *, keep_email: bool = False
) -> dict[str, Any]:
    """Copy entry data with the API key and expiry removed.

    The email is removed too, unless ``keep_email`` is set. Re-authorization
    keeps a previously stored email when the new login did not return one.
    """
    cleaned = dict(data)
    for key in _CREDENTIAL_FIELDS:
        if keep_email and key == CONF_EMAIL:
            continue
        cleaned.pop(key, None)
    return cleaned


def credential_update_block(
    existing_unique_id: str | None,
    email: str | None,
    *,
    allow_different_account: bool,
) -> str | None:
    """Abort reason when a login must not replace this entry, else None.

    Re-authorization keeps the same Cursor account. Switch-account may replace it.
    """
    if allow_different_account or same_cursor_account(existing_unique_id, email):
        return None
    return "wrong_account"


def unique_id_for_login(
    existing_unique_id: str | None,
    email: str | None,
    api_key: str,
    *,
    allow_different_account: bool,
) -> str | None:
    """Unique id to store after a successful login."""
    if email or allow_different_account:
        return account_unique_id(email, api_key)
    return existing_unique_id


def options_with_refreshed_models(
    options: Mapping[str, Any],
    listed: list[str] | None,
) -> dict[str, Any] | None:
    """Options after a model refresh.

    Returns None when the list could not be loaded, so the previous selection
    stays in place. The current model is kept when it is still offered.
    """
    if not listed:
        return None
    models = list(listed)
    if DEFAULT_MODEL not in models:
        models = [DEFAULT_MODEL, *models]
    updated = dict(options)
    current = updated.get(CONF_MODEL, DEFAULT_MODEL)
    if not isinstance(current, str) or current not in models:
        current = DEFAULT_MODEL
    updated[CONF_MODEL] = current
    updated[CONF_AVAILABLE_MODELS] = models
    return updated


def mark_account_switch(store: MutableMapping[str, Any], entry_id: str) -> None:
    """Remember that this entry is inside the switch-account login."""
    ids = store.get(DATA_SWITCH_IN_PROGRESS)
    if not isinstance(ids, set):
        ids = set()
        store[DATA_SWITCH_IN_PROGRESS] = ids
    ids.add(entry_id)


def account_switch_in_progress(store: Mapping[str, Any], entry_id: str) -> bool:
    """Whether setup should wait instead of opening a second login flow."""
    ids = store.get(DATA_SWITCH_IN_PROGRESS)
    return isinstance(ids, set) and entry_id in ids


def clear_account_switch(store: MutableMapping[str, Any], entry_id: str) -> None:
    """Drop the switch-account marker for one entry."""
    ids = store.get(DATA_SWITCH_IN_PROGRESS)
    if isinstance(ids, set):
        ids.discard(entry_id)

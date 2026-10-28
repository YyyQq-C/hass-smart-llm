"""Account identity helpers that do not import Home Assistant."""

from __future__ import annotations

import hashlib


def account_unique_id(email: str | None, api_key: str) -> str:
    """Stable id for one Cursor account. Email wins over a key fingerprint."""
    if email and "@" in email:
        return email.strip().lower()
    return "cursor-" + hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:12]


def same_cursor_account(existing: str | None, email: str | None) -> bool:
    """Whether a reauth may update this entry.

    Placeholder ids (no email yet) can be upgraded. Two different emails cannot
    share one entry.
    """
    if not existing or not email or "@" not in existing:
        return True
    return existing == email.strip().lower()

"""Errors raised by Smart LLM providers."""

from __future__ import annotations


class SmartLLMError(Exception):
    """Base class for provider failures."""


class ProviderAPIError(SmartLLMError):
    """The remote API rejected the request or could not be reached."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class ProviderAuthError(ProviderAPIError):
    """The API key was rejected."""


class CursorAPIError(ProviderAPIError):
    """Cursor Bridge or the Cursor login API rejected the request."""


class CursorAuthError(ProviderAuthError, CursorAPIError):
    """The Cursor API key or login session was rejected."""


class CursorLoginError(SmartLLMError):
    """Browser login did not produce a usable API key.

    ``code`` is a translation key. The message is safe to log: it never
    includes the verifier, the session token, or the minted API key.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code

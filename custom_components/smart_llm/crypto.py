"""Encrypt API keys so they are not stored as plaintext.

The Fernet key is derived from this Home Assistant install's instance id
(``.storage/core.uuid``). A copy of the config entry alone does not reveal the
API key. A full configuration-directory backup includes the instance id, so
it can decrypt the key — the same boundary as the rest of Home Assistant.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets

from cryptography.fernet import Fernet, InvalidToken

from .const import INSTANCE_UUID_FILENAME, KEK_FILENAME

_SALT = b"smart_llm.api_key.v1\0"
_MIN_ID_LENGTH = 8


class DecryptionError(Exception):
    """The stored ciphertext cannot be opened with this install's key."""


def fernet_for_material(material: bytes) -> Fernet:
    """Build a Fernet instance from install-specific key material."""
    digest = hashlib.sha256(_SALT + material).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plaintext: str, material: bytes) -> str:
    """Encrypt a secret. The plaintext is not present in the returned token."""
    if not plaintext:
        raise ValueError("Cannot encrypt an empty secret")
    token = fernet_for_material(material).encrypt(plaintext.encode("utf-8"))
    return token.decode("ascii")


def decrypt_secret(token: str, material: bytes) -> str:
    """Decrypt a secret produced by :func:`encrypt_secret`."""
    try:
        plaintext = fernet_for_material(material).decrypt(token.encode("ascii"))
    except (InvalidToken, ValueError, TypeError) as err:
        raise DecryptionError("Stored secret could not be decrypted") from err
    return plaintext.decode("utf-8")


def mask_secret(secret: str) -> str:
    """Return a display mask. The result never equals the original secret."""
    value = secret.strip()
    if not value:
        return "—"
    if len(value) <= 12:
        return "•" * 8
    tail = value[-4:]
    if value.startswith("crsr_"):
        return f"crsr_{'•' * 8}{tail}"
    return f"{value[:2]}{'•' * 8}{tail}"


def load_key_material(storage_dir: str) -> bytes:
    """Return stable key material for this Home Assistant configuration dir."""
    instance_id = _read_instance_id(os.path.join(storage_dir, INSTANCE_UUID_FILENAME))
    if instance_id:
        return instance_id.encode("utf-8")

    kek_path = os.path.join(storage_dir, KEK_FILENAME)
    existing = _read_text(kek_path)
    if existing:
        return existing.encode("utf-8")

    os.makedirs(storage_dir, exist_ok=True)
    generated = secrets.token_hex(32)
    try:
        fd = os.open(kek_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raced = _read_text(kek_path)
        if not raced:
            raise DecryptionError("Key encryption file is empty") from None
        return raced.encode("utf-8")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(generated)
    return generated.encode("utf-8")


def _read_instance_id(path: str) -> str | None:
    raw = _read_text(path)
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw if _looks_like_id(raw) else None
    if not isinstance(parsed, dict):
        return None
    data = parsed.get("data")
    if isinstance(data, dict):
        uuid = data.get("uuid")
        if isinstance(uuid, str) and uuid.strip():
            return uuid.strip()
    uuid = parsed.get("uuid")
    if isinstance(uuid, str) and uuid.strip():
        return uuid.strip()
    return None


def _read_text(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as handle:
            raw = handle.read().strip()
    except OSError:
        return None
    return raw or None


def _looks_like_id(value: str) -> bool:
    return len(value) >= _MIN_ID_LENGTH and not any(char.isspace() for char in value)

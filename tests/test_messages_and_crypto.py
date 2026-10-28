"""Chat-log conversion, key masking, and install-bound encryption."""

from __future__ import annotations

import json
import os
import stat

from custom_components.smart_llm.crypto import (
    DecryptionError,
    decrypt_secret,
    encrypt_secret,
    load_key_material,
    mask_secret,
)
from custom_components.smart_llm.identity import account_unique_id, same_cursor_account
from custom_components.smart_llm.provider.messages import (
    function_tool,
    openai_messages_from_contents,
)


class _ToolCall:
    def __init__(self, call_id: str, name: str, arguments: dict) -> None:
        self.id = call_id
        self.tool_name = name
        self.tool_args = arguments


class _Result:
    def __init__(self, data: dict, error: bool = False) -> None:
        self.data = data
        self.error = error


def test_openai_messages_cover_a_tool_round() -> None:
    messages = openai_messages_from_contents(
        [
            {"role": "system", "content": "You control the home."},
            {"role": "user", "content": [{"type": "text", "text": "Turn on the lamp"}]},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    _ToolCall("call_1", "HassTurnOn", {"name": "Lamp"})
                ],
            },
            {
                "role": "tool_result",
                "tool_call_id": "call_1",
                "tool_name": "HassTurnOn",
                "result": _Result({"success": True}),
            },
        ]
    )
    assert messages[0] == {"role": "system", "content": "You control the home."}
    assert messages[1] == {"role": "user", "content": "Turn on the lamp"}
    assert messages[2]["role"] == "assistant"
    assert messages[2]["content"] is None
    assert messages[2]["tool_calls"] == [
        {
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "HassTurnOn",
                "arguments": json.dumps({"name": "Lamp"}, ensure_ascii=False),
            },
        }
    ]
    assert messages[3]["role"] == "tool"
    assert messages[3]["tool_call_id"] == "call_1"
    assert json.loads(messages[3]["content"]) == {
        "data": {"success": True},
        "error": False,
    }
    tool = function_tool("HassTurnOn", None, {"type": "object"})
    assert tool["function"]["description"] == "HassTurnOn"


def test_mask_secret_hides_the_middle_of_a_cursor_key() -> None:
    secret = "crsr_" + ("a" * 40) + "wxyz"
    masked = mask_secret(secret)
    assert masked.startswith("crsr_")
    assert masked.endswith("wxyz")
    assert "aaaa" not in masked
    assert secret not in masked
    assert mask_secret("short") == "•" * 8
    assert mask_secret("") == "—"
    other = mask_secret("sk-1234567890abcd")
    assert other.startswith("sk")
    assert other.endswith("abcd")
    assert "1234567890" not in other


def test_encrypt_secret_round_trip_is_bound_to_the_install() -> None:
    material = b"instance-uuid"
    other = b"another-install"
    secret = "crsr_super_secret_value_123456"
    token = encrypt_secret(secret, material)
    again = encrypt_secret(secret, material)
    assert token != again
    assert secret not in token
    assert "crsr_" not in token
    assert decrypt_secret(token, material) == secret
    try:
        decrypt_secret(token, other)
    except DecryptionError:
        return
    raise AssertionError("other install decrypted the key")


def test_load_key_material_prefers_core_uuid_and_creates_a_private_kek(tmp_path) -> None:
    storage = tmp_path / "storage"
    storage.mkdir()
    uuid_file = storage / "core.uuid"
    uuid_file.write_text(
        json.dumps({"data": {"uuid": "install-uuid-value"}}),
        encoding="utf-8",
    )
    assert load_key_material(str(storage)) == b"install-uuid-value"
    assert not (storage / "smart_llm.kek").exists()

    bare = tmp_path / "bare"
    bare.mkdir()
    material = load_key_material(str(bare))
    kek = bare / "smart_llm.kek"
    assert kek.read_text(encoding="utf-8").encode("utf-8") == material
    mode = stat.S_IMODE(os.stat(kek).st_mode)
    assert mode == 0o600
    assert load_key_material(str(bare)) == material


def test_account_identity() -> None:
    assert account_unique_id("Ada@Example.com", "crsr_x") == "ada@example.com"
    fingerprint = account_unique_id(None, "crsr_same")
    assert fingerprint == account_unique_id("   ", "crsr_same")
    assert fingerprint != account_unique_id(None, "crsr_other")
    assert same_cursor_account("ada@example.com", "Ada@Example.com")
    assert not same_cursor_account("ada@example.com", "other@example.com")
    assert same_cursor_account(fingerprint, "ada@example.com")
    assert same_cursor_account(None, "ada@example.com")

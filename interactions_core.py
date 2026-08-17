"""Ядро /interactions вебхука: подпись Ed25519 + раскладка команд.

Отделено от modal_app, чтобы крыть тестами без инфраструктуры Modal.
"""

from __future__ import annotations

import json

from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey


def verify_signature(public_key_hex: str, timestamp: str, body: bytes, signature_hex: str) -> bool:
    try:
        VerifyKey(bytes.fromhex(public_key_hex)).verify(
            (timestamp + body.decode()).encode(), bytes.fromhex(signature_hex)
        )
        return True
    except (BadSignatureError, ValueError):
        return False


def parse_interaction(payload: dict) -> dict | None:
    """application command -> внутренняя команда для очереди; None, если не та."""
    if payload.get("type") != 2:
        return None
    data = payload["data"]
    command = {
        "command": data["name"],
        "guild_id": payload["guild_id"],
        "channel_id": payload["channel_id"],
        "user_id": payload["member"]["user"]["id"],
    }
    options = data.get("options") or []
    if options:
        command["value"] = options[0].get("value")
    return command


def parse_raw_body(body: bytes) -> dict:
    return json.loads(body)

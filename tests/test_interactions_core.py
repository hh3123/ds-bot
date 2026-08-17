from nacl.signing import SigningKey

from interactions_core import parse_interaction, verify_signature

SK = SigningKey.generate()
PK_HEX = SK.verify_key.encode().hex()


def sign(timestamp: str, body: bytes) -> str:
    return SK.sign((timestamp + body.decode()).encode()).signature.hex()


def test_valid_signature_passes():
    ts, body = "1700000000", b'{"type":1}'
    assert verify_signature(PK_HEX, ts, body, sign(ts, body)) is True


def test_garbage_signature_rejected():
    ts, body = "1700000000", b'{"type":1}'
    assert verify_signature(PK_HEX, ts, body, "00") is False


def test_tampered_body_rejected():
    ts, body = "1700000000", b'{"type":1}'
    sig = sign(ts, body)
    assert verify_signature(PK_HEX, ts, b'{"type":2}', sig) is False


def test_parse_slash_join():
    payload = {
        "type": 2,
        "guild_id": "795",
        "channel_id": "927",
        "member": {"user": {"id": "632"}},
        "data": {"name": "join", "options": []},
    }
    assert parse_interaction(payload) == {
        "command": "join", "guild_id": "795", "channel_id": "927", "user_id": "632",
    }


def test_parse_voice_with_option():
    payload = {
        "type": 2,
        "guild_id": "795",
        "channel_id": "927",
        "member": {"user": {"id": "632"}},
        "data": {"name": "voice", "options": [{"value": 5}]},
    }
    assert parse_interaction(payload)["value"] == 5


def test_ping_and_message_return_none():
    assert parse_interaction({"type": 1}) is None
    assert parse_interaction({"type": 3}) is None

import json

from bindings import load_bindings, save_bindings


def test_roundtrip_with_voice_and_text(tmp_path):
    path = tmp_path / "b.json"
    data = {1: {"text": 10, "voice": 20}, 2: {"text": 30, "voice": None}}
    save_bindings(path, data)
    assert load_bindings(path) == data


def test_migrates_legacy_int_format(tmp_path):
    """Старый формат {guild: text_id} читается как text, без голоса."""
    path = tmp_path / "b.json"
    path.write_text(json.dumps({"1": 10}), encoding="utf-8")
    assert load_bindings(path) == {1: {"text": 10, "voice": None}}


def test_missing_and_garbage_still_safe(tmp_path):
    assert load_bindings(tmp_path / "none.json") == {}
    p = tmp_path / "b.json"
    p.write_text("хлам", encoding="utf-8")
    assert load_bindings(p) == {}

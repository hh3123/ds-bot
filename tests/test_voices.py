import json
from pathlib import Path

from voices import PIPER_POOL, VOICE_POOL, Voice, assign, load_overrides, save_overrides, set_override


def test_pool_has_at_least_6_distinct_variants():
    assert len(VOICE_POOL) >= 6
    pairs = {(v.voice, v.pitch) for v in VOICE_POOL}
    assert len(pairs) == len(VOICE_POOL)  # без повторов


def test_pool_contains_both_genders():
    names = {v.voice for v in VOICE_POOL}
    assert "ru-RU-SvetlanaNeural" in names
    assert "ru-RU-DmitryNeural" in names


def test_assignment_is_stable_for_user():
    assert assign(12345, {}) == assign(12345, {})
    assert isinstance(assign(12345, {}), Voice)


def test_different_users_may_get_different_voices():
    assigned = {assign(uid, {}) for uid in range(100, 110)}
    assert len(assigned) > 1  # не все под одним голосом


def test_override_wins_over_assignment(tmp_path: Path):
    path = tmp_path / "voices.json"
    overrides = load_overrides(path)
    target = VOICE_POOL[-1]

    set_override(overrides, 42, target)
    save_overrides(path, overrides)

    loaded = load_overrides(path)
    assert assign(42, loaded) == target
    # на диске — имя, а не номер: смена пула не ломает выбор
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(raw["42"], str)


def test_unknown_override_falls_back(tmp_path: Path):
    path = tmp_path / "voices.json"
    overrides = load_overrides(path)
    overrides[7] = "не-голос|+99Hz"
    assert assign(7, overrides).voice in {v.voice for v in VOICE_POOL}


def test_name_override_survives_pool_change():
    """Та же строка-оверрайд в СИЛЕРО-пуле находит нужный голос и не дрейфует."""
    silero_overrides = {42: "xenia|+0Hz"}
    from voices import SILERO_POOL

    assert assign(42, silero_overrides, pool=SILERO_POOL).voice == "xenia"
    # в piper-пуле такого голоса нет — легальный фолбэк, без глитча на "другой" индекс
    assert assign(42, silero_overrides, pool=PIPER_POOL).voice in {"ruslan", "dmitri", "denis", "irina"}


def test_legacy_int_override_migrates_via_pool():
    from voices import SILERO_POOL

    migrated = assign(42, {42: 5}, pool=SILERO_POOL)
    assert migrated == SILERO_POOL[5]  # старый номер трактуем раз и навсегда через известный пул

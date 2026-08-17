"""Пул голосов для разных участников войса.

Rusских нейроголосов в Edge-TTS всего два, поэтому вариативность
разгоняем сдвигом тона (pitch): голос × тон = звучит другим человеком.

Голос выдаётся детерминированно по Discord-ID (один и тот же у человека
всегда), `/voice` сохраняет личный выбор поверх автоназначения.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("tts-voices")


@dataclass(frozen=True)
class Voice:
    """Один говорящий вариант: id для /voice, голос Edge, сдвиг тона."""

    idx: int
    voice: str
    pitch: str

    @property
    def key(self) -> str:
        """Стабильный ключ, не зависящий от состава пула."""
        return f"{self.voice}|{self.pitch}"

    @property
    def label(self) -> str:
        _CYRILLIC = {
            "ruslan": "Руслан", "dmitri": "Дмитрий", "denis": "Денис", "irina": "Ирина",
            "aidar": "Айдар", "eugene": "Евгений", "baya": "Бая", "kseniya": "Ксения",
            "xenia": "Ксюша",
            "anime": "Аниме (Ксюша, высокий тон)",
            "loli": "Лоли",
            "angel": "Ангел",
            "witch": "Ведьмочка",
            "demon": "Демон",
            "goblin": "Гоблин",
        }
        if "-" not in self.voice:  # piper/silero-голос: одно слово
            return _CYRILLIC.get(self.voice, self.voice.capitalize())
        base = "Светлана" if "Svetlana" in self.voice else "Дмитрий"
        modifiers = {
            "-10Hz": "очень низкий",
            "-5Hz": "низкий",
            "+0Hz": "обычный",
            "+5Hz": "высокий",
            "+10Hz": "очень высокий",
        }
        return f"{base} ({modifiers.get(self.pitch, self.pitch)})"


POOL_TONES = {
    "ru-RU-DmitryNeural": ["-10Hz", "-5Hz", "+0Hz", "+5Hz"],
    "ru-RU-SvetlanaNeural": ["-5Hz", "+0Hz", "+5Hz", "+10Hz"],
}

VOICE_POOL: list[Voice] = [
    Voice(idx, voice, pitch)
    for idx, (voice, pitch) in enumerate(
        (v, p) for v, tones in POOL_TONES.items() for p in tones
    )
]

PIPER_POOL: list[Voice] = [
    Voice(idx, name, "+0Hz")
    for idx, name in enumerate(["ruslan", "dmitri", "denis", "irina"])
]

SILERO_POOL: list[Voice] = [
    Voice(idx, name, "+0Hz")
    for idx, name in enumerate(
        ["aidar", "eugene", "baya", "kseniya", "xenia", "anime", "loli", "angel", "witch", "demon", "goblin"]
    )
]

_POOLS = {"edge": VOICE_POOL, "piper": PIPER_POOL, "silero": SILERO_POOL}


def pool_for(engine: str) -> list[Voice]:
    return _POOLS.get(engine, VOICE_POOL)


def assign(user_id: int, overrides: dict[int, object], pool: list[Voice] | None = None) -> Voice:
    """Стабильный голос для пользователя. Override (имя) побеждает.

    Старый формат (int) трактуем как индекс ТЕКУЩЕГО пула один раз —
    новые записи хранятся именем и больше не дрейфуют при смене пула.
    """
    active = pool if pool is not None else VOICE_POOL
    override = overrides.get(user_id)
    if isinstance(override, str):
        for v in active:
            if v.key == override or v.voice == override:
                return v
    elif isinstance(override, int) and 0 <= override < len(active):
        return active[override]
    return active[user_id % len(active)]


def set_override(overrides: dict[int, object], user_id: int, voice: Voice) -> None:
    overrides[user_id] = voice.key


def load_overrides(path: Path) -> dict[int, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {int(u): i for u, i in raw.items()}


def save_overrides(path: Path, overrides: dict[int, object]) -> None:
    try:
        path.write_text(json.dumps(overrides), encoding="utf-8")
    except OSError:
        log.exception("Не смог сохранить голоса в %s", path)

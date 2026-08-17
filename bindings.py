"""Постоянная привязка текстовых каналов (переживает перезапуск бота).

Формат на диске: {guild_id: {"text": id | None, "voice": id | None}}.
"text" — какой чат озвучиваем; "voice" — последний войс, куда заходили
(нужен, чтобы после перезапуска вернуться туда же самим, без /join).
Старый формат {guild_id: int} читается как text-привязка без войса.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger("tts-bindings")

Binding = dict  # {"text": int | None, "voice": int | None}


def _normalize(raw: dict) -> dict[int, Binding]:
    out: dict[int, Binding] = {}
    for g, v in raw.items():
        if isinstance(v, int):  # старый формат
            out[int(g)] = {"text": v, "voice": None}
        else:
            out[int(g)] = {"text": v.get("text"), "voice": v.get("voice")}
    return out


def load_bindings(path: Path) -> dict[int, Binding]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return _normalize(raw)


def save_bindings(path: Path, bindings: dict[int, Binding]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(bindings), encoding="utf-8")
        tmp.replace(path)  # атомарно: либо старое целое, либо новое целое
    except OSError:
        log.exception("Не смог сохранить привязки в %s", path)

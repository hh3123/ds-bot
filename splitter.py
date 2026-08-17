"""Резка длинного текста на куски для быстрого старта озвучки.

Сервер Edge-TTS начинает отдавать звук, только переварив весь вход,
поэтому длинную реплику выгодно резать на предложения: первое часть
озвучится и зазвучит за ~0.6с, остальные подъедут упреждающим синтезом.
"""

from __future__ import annotations

import re

_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?…])\s+")


def _hard_split(sentence: str, max_len: int) -> list[str]:
    """Предложение-переросток: пилим по словам, влезающим в max_len."""
    parts: list[str] = []
    cur = ""
    for word in sentence.split(" "):
        cand = f"{cur} {word}" if cur else word
        if len(cand) <= max_len:
            cur = cand
        else:
            if cur:
                parts.append(cur)
            cur = word
    if cur:
        parts.append(cur)
    return parts


def split_text(text: str, max_len: int = 120) -> list[str]:
    sentences = [s for s in _SENTENCE_BOUNDARY_RE.split(text) if s.strip()]
    parts: list[str] = []
    cur = ""
    for sentence in sentences:
        cand = f"{cur} {sentence}" if cur else sentence
        if len(cand) <= max_len:
            cur = cand
            continue
        if cur:
            parts.append(cur)
        if len(sentence) > max_len:
            parts.extend(_hard_split(sentence, max_len))
            cur = ""
        else:
            cur = sentence
    if cur:
        parts.append(cur)
    return parts or [text]

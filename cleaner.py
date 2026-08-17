"""Очистка текста сообщения перед синтезом речи.

Убирает всё, что TTS озвучил бы мусором: ссылки, разметку Discord,
эмодзи, упоминания. Возвращает готовую к озвучке строку или "" —
тогда говорить нечего.
"""

from __future__ import annotations

import re

import emoji as emoji_lib

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_CUSTOM_EMOJI_RE = re.compile(r"<a?:(\w+):\d+>")
_CHANNEL_RE = re.compile(r"<#\d+>")
_MENTION_RE = re.compile(r"<@!?(\d+)>|<@&\d+>")
_CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```", re.MULTILINE)
_MARKDOWN_RE = re.compile(r"[*_~`|>]+")
_HEADER_RE = re.compile(r"^#+\s*", re.MULTILINE)
_EMOJI_NAME_RE = re.compile(r":([A-Za-zА-Яа-яёЁ0-9_?]+):")
_WS_RE = re.compile(r"\s+")

_VOWELS = set("aeiouyаеёиоуыэюя")
_CONSONANT_RUN_RE = re.compile(r"[^aeiouyаеёиоуыэюя\d\s_]{4,}")


def _looks_like_word(name: str) -> bool:
    """Читаемое ли название кастомного эмодзи? Белиберду не озвучиваем."""
    word = name.lower()
    if len(word) < 3 or any(ch.isdigit() for ch in word):
        return False
    letters = [ch for ch in word if ch.isalpha()]
    if not letters:
        return False
    vowel_share = sum(ch in _VOWELS for ch in letters) / len(letters)
    if vowel_share < 0.2:
        return False
    return _CONSONANT_RUN_RE.search("".join(letters)) is None


def _unicode_emoji_to_names(text: str) -> str:
    """«хаха 😂» → «хаха смеется до слез»; «😂😂» схлопываются в одно название."""
    text = emoji_lib.demojize(text, language="ru")
    # Схлопнуть одинаковые подряд: ":смеется_до_слез::смеется_до_слез: " → одно
    text = re.sub(
        r"(:[\wа-яё]+:)(?:\1)+",
        lambda m: m.group(1) + " ",
        text,
        flags=re.IGNORECASE,
    )
    return _EMOJI_NAME_RE.sub(lambda m: m.group(1).replace("_", " ") + " ", text)


def clean_message(
    text: str,
    mentions: dict[str, str] | None = None,
    max_length: int = 300,
) -> str:
    """Приводит сырой текст Discord-сообщения к озвучиваемому виду.

    `mentions` — соответствие id пользователя → отображаемое имя,
    чтобы упоминания звучали как имена.
    """
    if mentions:
        text = _MENTION_RE.sub(lambda m: mentions.get(m.group(1) or "", ""), text)
    else:
        text = _MENTION_RE.sub("", text)
    text = _CODE_BLOCK_RE.sub(" ", text)
    text = _URL_RE.sub(" ", text)
    text = _CUSTOM_EMOJI_RE.sub(
        lambda m: " " + m.group(1).replace("_", " ") + " " if _looks_like_word(m.group(1)) else " ",
        text,
    )
    text = _CHANNEL_RE.sub(" ", text)
    text = _unicode_emoji_to_names(text)
    text = _MARKDOWN_RE.sub(" ", text)
    text = _HEADER_RE.sub("", text)
    text = _WS_RE.sub(" ", text).strip()

    if len(text) > max_length:
        cut = text[:max_length]
        boundary = cut.rfind(" ")
        if boundary > 0:
            cut = cut[:boundary]
        text = cut.rstrip(".,!?;: ") + "…"

    return text

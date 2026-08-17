"""Конфигурация из .env. Токен в коде не храним."""

import os

from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN: str | None = os.getenv("DISCORD_TOKEN")
TTS_VOICE: str = os.getenv("TTS_VOICE", "ru-RU-SvetlanaNeural")
TTS_RATE: str = os.getenv("TTS_RATE", "+0%")
TTS_VOLUME: str = os.getenv("TTS_VOLUME", "+0%")
MAX_TEXT_LENGTH: int = int(os.getenv("MAX_TEXT_LENGTH", "300"))
TTS_ENGINE: str = os.getenv("TTS_ENGINE", "piper")


def require_token() -> str:
    if not DISCORD_TOKEN:
        raise SystemExit(
            "Нет DISCORD_TOKEN. Скопируй .env.example в .env и вставь токен бота "
            "(Discord Developer Portal → Bot → Token)."
        )
    return DISCORD_TOKEN

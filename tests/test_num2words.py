import os
from pathlib import Path

import pytest

from tts_silero import numbers_to_words

_silero_cached = (Path(os.path.expanduser("~")) / ".cache" / "torch" / "hub" / "snakers4_silero-models_master").exists()


def test_plain_digits_become_words():
    assert numbers_to_words("у меня 2 кота") == "у меня два кота"
    assert numbers_to_words("123") == "сто двадцать три"
    assert numbers_to_words("2024 год") == "две тысячи двадцать четыре год"


def test_text_without_numbers_untouched():
    assert numbers_to_words("просто текст") == "просто текст"


@pytest.mark.skipif(not _silero_cached, reason="модель Silero не прогрета")
@pytest.mark.asyncio
async def test_silero_speaks_pure_digits():
    from tts import synthesize

    stream = await synthesize("123", voice="aidar", engine="silero")
    data = b""
    async for chunk in stream:
        data += chunk
    assert data[:4] == b"RIFF"
    assert len(data) > 48000  # что-то реально произнесли

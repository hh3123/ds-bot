import os
from pathlib import Path

import pytest

from tts import synthesize

_silero_cached = (Path(os.path.expanduser("~")) / ".cache" / "torch" / "hub" / "snakers4_silero-models_master").exists()


@pytest.mark.skipif(not _silero_cached, reason="модель Silero не прогрета")
@pytest.mark.asyncio
async def test_silero_synthesize_produces_wav_stream():
    stream = await synthesize("проверка силеро", voice="aidar", engine="silero")
    data = b""
    async for chunk in stream:
        data += chunk

    assert data[:4] == b"RIFF"
    assert len(data) > 48000 * 2 // 2  # хотя бы полсекунды звука


@pytest.mark.skipif(not _silero_cached, reason="модель Silero не прогрета")
@pytest.mark.asyncio
async def test_all_silero_voices_answer():
    for name in ("aidar", "eugene", "baya", "kseniya", "xenia", "anime", "loli", "angel", "witch", "demon", "goblin"):
        stream = await synthesize("тест", voice=name, engine="silero")
        first = await anext(stream)
        assert first[:4] == b"RIFF"


@pytest.mark.skipif(not _silero_cached, reason="модель Silero не прогрета")
@pytest.mark.asyncio
async def test_anime_keeps_duration_but_differs():
    """Длительность как у Ксюши (atempo компенсирует), байты другие (тон выше)."""
    async def full(voice: str) -> bytes:
        stream = await synthesize("один два три четыре пять", voice=voice, engine="silero")
        return b"".join([c async for c in stream])

    normal, anime = await full("xenia"), await full("anime")
    assert normal != anime
    ratio = len(anime) / len(normal)
    assert 0.7 < ratio < 1.4, f"длительность разъехалась: {ratio:.2f}"

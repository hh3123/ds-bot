import pytest

import tts_piper
from piper import PiperVoice

from tts import synthesize

MODELS_OK = (tts_piper.MODELS_DIR / "ruslan" / "medium" / "ru_RU-ruslan-medium.onnx").exists()


def test_wav_header_is_valid_44_bytes():
    h = tts_piper.wav_header()
    assert len(h) == 44
    assert h[:4] == b"RIFF"
    assert h[8:12] == b"WAVE"


@pytest.mark.skipif(not MODELS_OK, reason="модели piper не скачаны")
@pytest.mark.asyncio
async def test_piper_synthesize_produces_wav_stream():
    stream = await synthesize("проверка локальной скорости", voice="ruslan", engine="piper")
    data = b""
    async for chunk in stream:
        data += chunk

    assert data[:4] == b"RIFF"
    assert len(data) > 44100  # хотя бы секунда речи с 22кГц моно


@pytest.mark.skipif(not MODELS_OK, reason="модели piper не скачаны")
def test_all_four_models_load():
    for name in ("ruslan", "dmitri", "denis", "irina"):
        assert isinstance(tts_piper._load_model(name), PiperVoice)


def test_unknown_engine_raises():
    import asyncio

    with pytest.raises(ValueError, match="Неизвестный движок"):
        asyncio.run(synthesize("x", engine="qwen-tts"))

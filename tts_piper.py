"""Локальный движок Piper TTS: мгновенный старт (~0.1с на CPU), офлайн.

Отдаём PCM 22050 Гц mono с WAV-заголовком с «бесконечной» длиной,
чтобы ffmpeg принял поток точно так же, как mp3-стрим от Edge.
"""

from __future__ import annotations

import asyncio
import struct
from collections.abc import AsyncIterator
from functools import lru_cache
from pathlib import Path

from piper import PiperVoice
from piper.config import SynthesisConfig

MODELS_DIR = Path(__file__).with_name("voices_piper") / "ru" / "ru_RU"
SAMPLE_RATE = 22050


@lru_cache(maxsize=None)
def _load_model(name: str) -> PiperVoice:
    base = MODELS_DIR / name / "medium" / f"ru_RU-{name}-medium"
    return PiperVoice.load(str(base) + ".onnx", str(base) + ".onnx.json")


def wav_header(sample_rate: int = SAMPLE_RATE, channels: int = 1) -> bytes:
    """WAV header с поддельным размером данных (стрим в stdin без известного конца)."""
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 0xFFFFFFFF, b"WAVE",
        b"fmt ", 16, 1, channels, sample_rate, sample_rate * channels * 2, channels * 2, 16,
        b"data", 0xFFFFFFFF,
    )


def _percent(value: str, default: int = 0) -> int:
    return int(value.strip().rstrip("%")) if value.strip().rstrip("%").lstrip("+-").isdigit() else default


def _synth_all(text: str, voice: str, rate: str, volume: str) -> bytes:
    model = _load_model(voice)
    rate_pct = _percent(rate)
    syn = SynthesisConfig(
        length_scale=max(0.5, 1.0 / (1 + rate_pct / 100)),
        volume=max(0.0, 1 + _percent(volume) / 100),
    )
    return b"".join(chunk.audio_int16_bytes for chunk in model.synthesize(text, syn_config=syn))


async def synthesize(
    text: str,
    voice: str = "ruslan",
    pitch: str = "+0Hz",
    rate: str = "+0%",
    volume: str = "+0%",
) -> AsyncIterator[bytes]:
    """Стрим один: WAV-заголовок + вся фраза (синтез фразы ~0.1с). pitch игнорируем."""
    if not text.strip():
        raise ValueError("Пустой текст нечего озвучивать")

    pcm = await asyncio.to_thread(_synth_all, text, voice, rate, volume)

    async def _stream() -> AsyncIterator[bytes]:
        yield wav_header()
        if pcm:
            yield pcm

    return _stream()

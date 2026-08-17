"""Движок Silero v5.1: качество выше Piper при той же локальной скорости.

Пять русских голосов: aidar, eugene (M), baya, kseniya, xenia (F).
Отдаём PCM 48000 Гц mono с WAV-шапкой, как и Piper.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import re

import numpy as np
from num2words import num2words

from tts_piper import wav_header

SAMPLE_RATE = 48000

_NUMBER_RE = re.compile(r"\d+")


def numbers_to_words(text: str) -> str:
    """Silero падает на чистых цифрах — разворачиваем их в русские слова."""
    return _NUMBER_RE.sub(lambda m: num2words(int(m.group()), lang="ru"), text)

_model = None
_apply_lock = asyncio.Lock()


def _load_model():
    global _model
    if _model is None:
        import torch

        torch.set_num_threads(1)  # слабый облачный CPU/RAM: без перегрева и пиков
        _model, _ = torch.hub.load(
            "snakers4/silero-models",
            "silero_tts",
            language="ru",
            speaker="v5_1_ru",
            trust_repo=True,
        )
    return _model


# Кастомные голоса — вариации базовых спикеров со сдвигом тона.
# asetrate разгоняет звук (выше тон + быстрее), atempo возвращает длительность.
_PITCH_VARIANTS: dict[str, tuple[str, float]] = {
    "anime": ("xenia", 1.22),
    "loli": ("xenia", 1.42),
    "angel": ("baya", 1.12),
    "witch": ("kseniya", 0.92),
    "demon": ("eugene", 0.78),
    "goblin": ("aidar", 1.35),
}


def _pitch_shift_ffmpeg(pcm: bytes, factor: float) -> bytes:
    import subprocess

    import imageio_ffmpeg

    proc = subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", "1", "-i", "-",
            "-af", f"asetrate={SAMPLE_RATE}*{factor},aresample={SAMPLE_RATE},atempo={1/factor:.4f}",
            "-f", "s16le", "-loglevel", "error", "pipe:1",
        ],
        input=pcm,
        capture_output=True,
        timeout=30,
    )
    return proc.stdout


def _synth_all(text: str, voice: str) -> bytes:
    model = _load_model()
    variant = _PITCH_VARIANTS.get(voice)
    speaker = variant[0] if variant else voice
    audio = model.apply_tts(text=numbers_to_words(text), sample_rate=SAMPLE_RATE, speaker=speaker)
    pcm = np.clip(audio.cpu().numpy(), -1.0, 1.0)
    data = (pcm * 32767).astype(np.int16).tobytes()
    if variant:
        data = _pitch_shift_ffmpeg(data, variant[1])
    return data


async def synthesize(
    text: str,
    voice: str = "aidar",
    pitch: str = "+0Hz",
    rate: str = "+0%",
    volume: str = "+0%",
) -> AsyncIterator[bytes]:
    """Стрим: WAV-шапка + PCM всей фразы. pitch/rate у Silero не бывает."""
    if not text.strip():
        raise ValueError("Пустой текст нечего озвучивать")

    async with _apply_lock:  # модель небезопасна для параллельных вызовов
        pcm = await asyncio.to_thread(_synth_all, text, voice)

    async def _stream() -> AsyncIterator[bytes]:
        yield wav_header(SAMPLE_RATE)
        if pcm:
            yield pcm

    return _stream()


async def preload() -> None:
    """Прогреть модель заранее, чтобы первое сообщение не ждало 10с."""
    await asyncio.to_thread(_load_model)

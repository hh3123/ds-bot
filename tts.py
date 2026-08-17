"""Диспетчер синтеза речи.

Движки:
- piper — локальный (быстрый старт ~0.1с, офлайн, русские модели);
- edge  — Microsoft Edge-TTS (облако 0.6–2.5с до первого звука, но человечнее).

Оба дают ASYNC-итератор байт контейнера (mp3 / wav), совместимого со
stdin ffmpeg.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import edge_tts

import tts_piper

DEFAULT_VOICE = "ru-RU-SvetlanaNeural"  # альтернатива: ru-RU-DmitryNeural (мужской, Edge)


async def _audio_chunks(communicate: edge_tts.Communicate) -> AsyncIterator[bytes]:
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            yield chunk["data"]


async def _primed(first: bytes | None, rest: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    if first is not None:
        yield first
    async for chunk in rest:
        yield chunk


async def _synthesize_edge(
    text: str,
    voice: str,
    pitch: str,
    rate: str,
    volume: str,
) -> AsyncIterator[bytes]:
    communicate = edge_tts.Communicate(
        text, voice=voice, rate=rate, volume=volume, pitch=pitch
    )
    chunks = _audio_chunks(communicate)
    first = await anext(chunks, None)
    return _primed(first, chunks)


async def synthesize(
    text: str,
    voice: str = DEFAULT_VOICE,
    pitch: str = "+0Hz",
    rate: str = "+0%",
    volume: str = "+0%",
    engine: str = "piper",
) -> AsyncIterator[bytes]:
    """Стрим озвучки. Первый кусок добывается до возврата (для edge —
    что даёт очереди смысл упреждающей подготовки следующего трека).
    """
    if not text.strip():
        raise ValueError("Пустой текст нечего озвучивать")

    if engine == "edge":
        return await _synthesize_edge(text, voice, pitch, rate, volume)
    if engine == "piper":
        return await tts_piper.synthesize(text, voice=voice, pitch=pitch, rate=rate, volume=volume)
    if engine == "silero":
        import tts_silero  # тяжёлый импорт torch: только когда выбран

        return await tts_silero.synthesize(text, voice=voice, pitch=pitch, rate=rate, volume=volume)
    raise ValueError(f"Неизвестный движок TTS: {engine!r}")

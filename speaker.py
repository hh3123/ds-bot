"""Последовательная очередь озвучки.

Speaker не знает ни про Discord, ни про Edge-TTS: ему дают два
корутинных колбека — синтез (текст+голос+тон -> async-стрим байт) и
проигрывание (стрим -> ждать окончания). Это позволяет тестировать
очередь без сервера и сети.

Гарантии: FIFO, не более одной дорожки одновременно, упреждающий синтез
следующего трека во время игры текущего, ошибка одного трека не роняет
очередь.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable

Synthesize = Callable[[str, str, str], Awaitable[AsyncIterator[bytes]]]
Play = Callable[[AsyncIterator[bytes]], Awaitable[None]]

log = logging.getLogger("tts-speaker")

_Item = tuple[str, str, str]  # текст, голос, тон


class Speaker:
    def __init__(self, synthesize: Synthesize, play: Play) -> None:
        self._synthesize = synthesize
        self._play = play
        self._queue: asyncio.Queue[_Item] = asyncio.Queue()
        self._worker: asyncio.Task | None = None

    async def start(self) -> None:
        """Запустить фонового воркера. Идемпотентно."""
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run())

    def enqueue(self, text: str, voice: str, pitch: str) -> None:
        self._queue.put_nowait((text, voice, pitch))

    async def drain(self) -> None:
        await self._queue.join()

    async def stop(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None

    async def _run(self) -> None:
        # Упреждающий синтез: пока играет трек N, параллельно тянем первые
        # байты N+1, если он уже в очереди. Проигрывание строго FIFO.
        next_task: asyncio.Task[AsyncIterator[bytes]] | None = None
        next_item: _Item | None = None
        while True:
            if next_task is None:
                next_item = await self._queue.get()
                next_task = asyncio.create_task(self._synthesize(*next_item))
            item, task = next_item, next_task
            next_task, next_item = None, None
            t_start = time.monotonic()

            try:
                stream = await task
                t_synth = time.monotonic()
                try:
                    next_item = self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                else:
                    next_task = asyncio.create_task(self._synthesize(*next_item))
                await self._play(stream)
                log.info(
                    "ЛАТЕНТНОСТЬ: синтез-первый-кусок %dмс, проигрывание %dмс, всего %dмс",
                    round((t_synth - t_start) * 1000),
                    round((time.monotonic() - t_synth) * 1000),
                    round((time.monotonic() - t_start) * 1000),
                )
            except Exception:
                log.exception("Не удалось озвучить: %r", item)
            finally:
                self._queue.task_done()

"""Мост: блокирующий file-like ридер поверх асинхронного TTS-стрима.

Discord.py в pipe-режиме ffmpeg сам крутит поток `source.read()`, а Edge-TTS
отдаёт аудио через async-итератор. Этот класс склеивает два мира: `feed()`
из event loop'а кладёт байты в буффер, `read()` во writer-потоке ждёт их.
"""

from __future__ import annotations

import io
import threading


class AsyncStreamReader(io.RawIOBase):
    def __init__(self) -> None:
        self._buf = bytearray()
        self._eof = False
        self._cond = threading.Condition()

    def feed(self, data: bytes) -> None:
        with self._cond:
            self._buf += data
            self._cond.notify()

    def close_write(self) -> None:
        """Больше байт не будет: read() отработает остаток и вернёт EOF."""
        with self._cond:
            self._eof = True
            self._cond.notify_all()

    def readable(self) -> bool:
        return True

    def read(self, n: int = -1) -> bytes:
        with self._cond:
            while not self._buf and not self._eof:
                self._cond.wait()
            if not self._buf:
                return b""
            if n < 0 or n > len(self._buf):
                n = len(self._buf)
            out = bytes(self._buf[:n])
            del self._buf[:n]
            return out

    def readinto(self, b) -> int:
        data = self.read(len(b))
        b[: len(data)] = data
        return len(data)

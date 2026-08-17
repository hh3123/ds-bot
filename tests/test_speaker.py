import asyncio
from collections.abc import AsyncIterator

import pytest

from speaker import Speaker

V, P = "ru-RU-SvetlanaNeural", "+0Hz"


async def stream_of(*chunks: bytes) -> AsyncIterator[bytes]:
    for c in chunks:
        yield c


def make_spy_speaker():
    events: list[str] = []
    synth_calls: list[str] = []

    async def synth(text: str, voice: str, pitch: str) -> AsyncIterator[bytes]:
        synth_calls.append(text)
        return stream_of(b"chunk1-", b"chunk2")

    async def play(stream: AsyncIterator[bytes]) -> None:
        events.append("play-start")
        got = b""
        async for chunk in stream:
            got += chunk
        events.append(f"play-end:{got.decode()}")
        await asyncio.sleep(0.01)

    speaker = Speaker(synthesize=synth, play=play)
    return speaker, synth_calls, events


@pytest.mark.asyncio
async def test_plays_all_messages_in_fifo_order():
    speaker, synth_calls, events = make_spy_speaker()
    await speaker.start()

    speaker.enqueue("a", V, P)
    speaker.enqueue("b", V, P)
    speaker.enqueue("c", V, P)
    await speaker.drain()

    assert synth_calls == ["a", "b", "c"]
    assert [e for e in events if e.startswith("play-end")] == [
        "play-end:chunk1-chunk2"
    ] * 3
    await speaker.stop()


@pytest.mark.asyncio
async def test_never_plays_two_tracks_at_once():
    speaker, _, events = make_spy_speaker()
    await speaker.start()

    for t in ["a", "b", "c"]:
        speaker.enqueue(t, V, P)
    await speaker.drain()

    playing = 0
    for e in events:
        playing += 1 if e == "play-start" else -1
        assert playing in (0, 1), f"Параллельное проигрывание: {events}"
    assert len(events) == 6
    await speaker.stop()


@pytest.mark.asyncio
async def test_synthesizes_next_track_while_current_plays():
    events: list[str] = []

    async def synth(text: str, voice: str, pitch: str) -> AsyncIterator[bytes]:
        events.append(f"synth:{text}")
        return stream_of(b"x")

    async def play(stream: AsyncIterator[bytes]) -> None:
        events.append("play-start:a")
        async for _ in stream:
            pass
        await asyncio.sleep(0.05)
        events.append("play-end:a")

    speaker = Speaker(synthesize=synth, play=play)
    await speaker.start()

    speaker.enqueue("a", V, P)
    speaker.enqueue("b", V, P)
    await speaker.drain()

    assert events.index("synth:b") < events.index("play-end:a"), events
    await speaker.stop()


@pytest.mark.asyncio
async def test_keeps_working_after_playback_error():
    played: list[list[bytes]] = []

    async def synth(text: str, voice: str, pitch: str) -> AsyncIterator[bytes]:
        return stream_of(text.encode())

    async def flaky_play(stream: AsyncIterator[bytes]) -> None:
        data = [c async for c in stream]
        if data[0] == b"bad":
            raise RuntimeError("discord отвалился")
        played.append(data)

    speaker = Speaker(synthesize=synth, play=flaky_play)
    await speaker.start()

    speaker.enqueue("bad", V, P)
    speaker.enqueue("ok", V, P)
    await speaker.drain()

    assert played == [[b"ok"]]  # следующий трек не потерян
    await speaker.stop()


@pytest.mark.asyncio
async def test_speaker_passes_voice_and_pitch_through():
    got: list[tuple[str, str, str]] = []

    async def synth(text: str, voice: str, pitch: str) -> AsyncIterator[bytes]:
        got.append((text, voice, pitch))
        return stream_of(b"x")

    async def play(stream: AsyncIterator[bytes]) -> None:
        async for _ in stream:
            pass

    speaker = Speaker(synthesize=synth, play=play)
    await speaker.start()

    speaker.enqueue("привет", "ru-RU-DmitryNeural", "-10Hz")
    await speaker.drain()

    assert got == [("привет", "ru-RU-DmitryNeural", "-10Hz")]
    await speaker.stop()

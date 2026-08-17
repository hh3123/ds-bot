from pipe_bridge import AsyncStreamReader


def test_read_returns_fed_chunks_in_order():
    r = AsyncStreamReader()
    r.feed(b"ab")
    r.feed(b"cd")
    r.close_write()

    assert r.read(3) == b"abc"
    assert r.read(10) == b"d"
    assert r.read(10) == b""  # EOF после закрытия


def test_read_blocks_until_data_then_eof():
    import threading, time

    r = AsyncStreamReader()
    got = []

    def reader_thread():
        got.append(r.read(2))
        got.append(r.read(2))
        got.append(r.read(2))  # EOF

    t = threading.Thread(target=reader_thread)
    t.start()
    time.sleep(0.05)
    assert got == []  # чтение блокируется, данные ещё не подали

    r.feed(b"ab")
    time.sleep(0.05)
    r.feed(b"cd")
    r.close_write()

    t.join(timeout=2)
    assert got == [b"ab", b"cd", b""]

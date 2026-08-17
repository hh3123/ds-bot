"""Гейт озвучки: проговариваем только сообщения авторов,
которые сидят в том же голосовом канале, что и бот."""

from __future__ import annotations


def can_speak(bot_channel_id: int | None, author_channel_id: int | None) -> bool:
    """Один критерий: id голосового канала автора совпадает с ботом.

    Покрывает сразу три случая тишины: бот не в войсе, автор не в войсе,
    автор в другом войсе.
    """
    return (
        bot_channel_id is not None
        and author_channel_id is not None
        and bot_channel_id == author_channel_id
    )

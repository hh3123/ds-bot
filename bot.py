"""Discord-бот: озвучивает сообщения из привязанного текстового канала
в голосовом канале через Edge-TTS.

/setup  — привязать ЭТОТ текстовый канал к озвучке (+ войс автора, если он там).
/join   — бот заходит/переходит в твой голосовой канал (и привязывает чат,
          если ещё не привязан).
/leave  — выйти из войса и снять привязку.

Озвучиваются только сообщения авторов, сидящих в том же войсе, что и бот.

Голос/темп/громкость и лимит длины текста — в .env (см. .env.example).
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import logging
import time
from collections.abc import AsyncIterator
from pathlib import Path

import discord
import imageio_ffmpeg
from discord import app_commands

import tts
from bindings import load_bindings, save_bindings
from cleaner import clean_message
from config import MAX_TEXT_LENGTH, TTS_ENGINE, TTS_RATE, TTS_VOICE, TTS_VOLUME, require_token
from gate import can_speak
from pipe_bridge import AsyncStreamReader
from speaker import Speaker
from splitter import split_text
from voices import assign, load_overrides, pool_for, save_overrides, set_override

VOICE_POOL = pool_for(TTS_ENGINE)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("tts-bot")

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

intents = discord.Intents.default()
intents.message_content = True  # нужен, чтобы читать тексты сообщений
intents.voice_states = True

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

# Привязка на сервер: guild_id -> channel_id, который озвучиваем.
# Переживает перезапуски: один раз /setup — и навсегда, пока /leave.
import os

DATA_DIR = Path(os.getenv("DATA_DIR", str(Path(__file__).parent)))
BINDINGS_FILE = DATA_DIR / "bindings.json"
VOICES_FILE = DATA_DIR / "voices.json"
bound_channels: dict[int, dict] = load_bindings(BINDINGS_FILE)
voice_overrides: dict[int, int] = load_overrides(VOICES_FILE)


def _save_bindings() -> None:
    save_bindings(BINDINGS_FILE, bound_channels)


async def _play(stream: AsyncIterator[bytes]) -> None:
    """Проигрывает аудио-стрим в войс: mp3-куски на лету в stdin ffmpeg."""
    for vc in list(bot.voice_clients):
        t0 = time.monotonic()
        done = asyncio.Event()
        reader = AsyncStreamReader()
        source = discord.FFmpegPCMAudio(
            reader, executable=FFMPEG_EXE, pipe=True, options="-loglevel warning"
        )
        t_ffmpeg = time.monotonic()
        vc.play(source, after=lambda err: bot.loop.call_soon_threadsafe(done.set))
        log.info("ЛАТЕНТНОСТЬ: спавн ffmpeg %dмс", round((t_ffmpeg - t0) * 1000))
        first = True
        try:
            async for chunk in stream:
                if first:
                    log.info("ЛАТЕНТНОСТЬ: первый кусок дошёл до ffmpeg за %dмс", round((time.monotonic() - t0) * 1000))
                    first = False
                reader.feed(chunk)
        finally:
            reader.close_write()
        await done.wait()
        with contextlib.suppress(Exception):
            source.cleanup()


synthesize = functools.partial(tts.synthesize, rate=TTS_RATE, volume=TTS_VOLUME, engine=TTS_ENGINE)
speaker = Speaker(synthesize=synthesize, play=_play)


@bot.event
async def on_ready() -> None:
    await tree.sync()
    # Дублируем команды на уровне серверов: появляются почти мгновенно,
    # в отличие от глобальной синхронизации (до часа).
    for guild in bot.guilds:
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
    await speaker.start()
    log.info("Вошёл как %s (id=%s). Движок: %s", bot.user, bot.user and bot.user.id, TTS_ENGINE)

    if TTS_ENGINE == "silero":
        import tts_silero

        asyncio.create_task(tts_silero.preload())  # прогрев модели фоном

    # Автовозврат в последний войс после перезапуска, если там живые люди
    for guild in bot.guilds:
        binding = bound_channels.get(guild.id)
        if binding is None or guild.voice_client is not None:
            continue
        voice_id = binding.get("voice")
        if not voice_id:
            continue
        channel = guild.get_channel(voice_id)
        if isinstance(channel, discord.VoiceChannel) and any(not m.bot for m in channel.members):
            await channel.connect()
            log.info("Автовозврат в войс %s (%s)", channel.name, guild.name)

    if os.getenv("COMMAND_QUEUE"):
        asyncio.create_task(_modal_command_loop())
        log.info("Команды слушаю из очереди Modal (режим спящего бота)")
    if os.getenv("MODAL_WATCHDOG"):
        asyncio.create_task(_watchdog())


async def _modal_command_loop() -> None:
    """Читает команды слэша, приехавшие через вебхук Modal."""
    import modal as modal_lib

    q = modal_lib.Queue.from_name(os.environ["COMMAND_QUEUE"], create_if_missing=True)
    asyncio.create_task(_modal_heartbeat())
    while True:
        try:
            cmd = await asyncio.to_thread(q.get, True, 30)
        except Exception:
            cmd = None
        if not cmd:
            continue
        try:
            await _dispatch_modal_command(cmd)
        except Exception:
            log.exception("Не исполнилось команда из очереди: %r", cmd)


async def _dispatch_modal_command(cmd: dict) -> None:
    guild = bot.get_guild(int(cmd["guild_id"]))
    if guild is None:
        return
    channel = guild.get_channel(int(cmd["channel_id"]))
    member = guild.get_member(int(cmd["user_id"]))
    name = cmd["command"]

    async def reply(text: str) -> None:
        if isinstance(channel, discord.abc.Messageable):
            await channel.send(text)

    if name in ("setup", "join"):
        if name == "setup" or guild.id not in bound_channels or not bound_channels[guild.id].get("text"):
            binding = bound_channels.setdefault(guild.id, {"text": None, "voice": None})
            binding["text"] = int(cmd["channel_id"])
        voice_channel = member.voice.channel if member is not None and member.voice else None
        if voice_channel is None:
            await reply("Зайди в голосовой канал — и повтори команду.")
            return
        vc = guild.voice_client
        if vc is not None:
            await vc.move_to(voice_channel)
        else:
            await voice_channel.connect()
        bound_channels[guild.id]["voice"] = voice_channel.id
        _save_bindings()
        await reply(f"Зашёл в **{voice_channel.name}**. Озвучиваю привязанный чат.")
    elif name == "leave":
        vc = guild.voice_client
        bound_channels.pop(guild.id, None)
        _save_bindings()
        if vc is not None:
            await vc.disconnect()
        await reply("Вышел и снял привязку.")
    elif name == "voice":
        value = cmd.get("value")
        if value is None:
            return
        chosen = VOICE_POOL[int(value)]
        set_override(voice_overrides, int(cmd["user_id"]), chosen)
        save_overrides(VOICES_FILE, voice_overrides)
        await reply(f"{member.display_name if member else 'Ты'}: голос теперь **{chosen.label}**.")


async def _modal_heartbeat() -> None:
    """Держит флаг 'бот жив' в Modal Dict: вебхук не спавнит второй процесс."""
    import modal as modal_lib

    status = modal_lib.Dict.from_name("ds-bot-state", create_if_missing=True)
    while True:
        try:
            status.put("runner-alive", time.time())
        except Exception:
            log.warning("Не смог записать heartbeat в Modal Dict")
        await asyncio.sleep(60)


async def _watchdog() -> None:
    """Modal-режим: войса нет 10 минут — умираем, контейнер гаснет, $0."""
    await asyncio.sleep(120)
    idle_since: float | None = None
    while True:
        await asyncio.sleep(60)
        if not bot.voice_clients:
            idle_since = idle_since or time.monotonic()
            if time.monotonic() - idle_since > 600:
                log.info("Войса нет 10 минут — ухожу спать (контейнер Modal гаснет)")
                os._exit(0)
        else:
            idle_since = None


@bot.event
async def on_guild_join(guild: discord.Guild) -> None:
    tree.copy_global_to(guild=guild)
    await tree.sync(guild=guild)


def _author_voice_channel(interaction: discord.Interaction) -> discord.VoiceChannel | None:
    voice = interaction.user.voice  # type: ignore[attr-defined]
    return voice.channel if voice is not None else None  # type: ignore[return-value]


async def _join_author_voice(interaction: discord.Interaction) -> discord.VoiceChannel | None:
    """Подключает бота к войсу автора или переносит туда. Возвращает канал."""
    channel = _author_voice_channel(interaction)
    if channel is None:
        return None
    vc = interaction.guild and interaction.guild.voice_client
    if vc is not None:
        await vc.move_to(channel)
    else:
        await channel.connect()
    return channel


@tree.command(
    name="setup",
    description="Привязать этот текстовый канал: всё, что тут пишут, озвучивается",
)
async def setup(interaction: discord.Interaction) -> None:
    assert interaction.guild is not None
    binding = bound_channels.setdefault(interaction.guild.id, {"text": None, "voice": None})
    binding["text"] = interaction.channel.id  # type: ignore[union-attr]

    channel = await _join_author_voice(interaction)
    if channel is not None:
        binding["voice"] = channel.id
    _save_bindings()
    if channel is not None:
        reply = (
            f"Чат привязан (**#{interaction.channel.name}**), зашёл в **{channel.name}**. "  # type: ignore[union-attr]
            "Озвучиваю сообщения только тех, кто сидит в этом войсе."
        )
    else:
        reply = (
            f"Чат привязан (**#{interaction.channel.name}**). Ты не в войсе — как зайдёшь, "
            "напиши `/join`, и начну озвучивать."
        )
    await interaction.response.send_message(reply)


@tree.command(name="join", description="Бот заходит в твой голосовой канал")
async def join(interaction: discord.Interaction) -> None:
    assert interaction.guild is not None
    channel = await _join_author_voice(interaction)
    if channel is None:
        await interaction.response.send_message(
            "Сначала зайди в голосовой канал — потом зови меня.", ephemeral=True
        )
        return

    binding = bound_channels.setdefault(interaction.guild.id, {"text": None, "voice": None})
    if binding["text"] is None:
        binding["text"] = interaction.channel.id  # type: ignore[union-attr]
        reply = f"Зашёл в **{channel.name}** и привязался к чату **#{interaction.channel.name}**."  # type: ignore[union-attr]
    else:
        reply = f"Зашёл в **{channel.name}**. Озвучиваю привязанный чат."
    binding["voice"] = channel.id
    _save_bindings()
    await interaction.response.send_message(reply)


@tree.command(name="leave", description="Бот выходит из голосового канала и снимает привязку чата")
async def leave(interaction: discord.Interaction) -> None:
    assert interaction.guild is not None
    vc = interaction.guild.voice_client
    bound_channels.pop(interaction.guild.id, None)
    _save_bindings()
    if vc is not None:
        await vc.disconnect()
        await interaction.response.send_message("Вышел из войса и снял привязку. Пока!")
    else:
        await interaction.response.send_message("Привязку снял. В войсе я и так не был.", ephemeral=True)


@tree.command(name="voice", description="Выбрать себе голос для озвучки твоих сообщений")
@app_commands.describe(variant="Голос, которым будут звучать Твои сообщения")
@app_commands.choices(
    variant=[app_commands.Choice(name=v.label, value=v.idx) for v in VOICE_POOL]
)
async def voice_cmd(interaction: discord.Interaction, variant: int) -> None:
    chosen = VOICE_POOL[variant]
    set_override(voice_overrides, interaction.user.id, chosen)
    save_overrides(VOICES_FILE, voice_overrides)
    await interaction.response.send_message(
        f"Принято! Твои сообщения теперь звучат как **{chosen.label}**.", ephemeral=True
    )


@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot or message.guild is None:
        return
    binding = bound_channels.get(message.guild.id)
    if binding is None or binding.get("text") != message.channel.id:
        return

    vc = message.guild.voice_client
    bot_channel = vc.channel.id if vc is not None and vc.channel is not None else None
    author_voice = getattr(message.author, "voice", None)
    author_channel = author_voice.channel.id if author_voice and author_voice.channel else None
    if not can_speak(bot_channel_id=bot_channel, author_channel_id=author_channel):
        log.info("Молчу (гейт): %s вне моего войса: %s", message.author.display_name, message.content)
        return

    mentions = {str(m.id): m.display_name for m in message.mentions}
    text = clean_message(message.content, mentions=mentions, max_length=MAX_TEXT_LENGTH)
    if not text:
        return

    speaker_voice = assign(message.author.id, voice_overrides, pool=VOICE_POOL)
    log.info(
        "[%s] %s (%s): %s",
        message.channel.name, message.author.display_name, speaker_voice.label, text,
    )
    # Сервер начинает звук, переварив всю фразу целиком — режем на
    # предложения: первый кусок зазвучит за ~0.6с, остальные подъедут потоком.
    for part in split_text(text):
        speaker.enqueue(part, speaker_voice.voice, speaker_voice.pitch)


@bot.event
async def on_voice_state_update(
    member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
) -> None:
    """Если в войсе со мной не осталось живых людей — выхожу сам.

    Привязку текстового канала НЕ снимаем: вернётся кто-нибудь с /join —
    озвучка продолжится как ни в чём не бывало.
    """
    if member.id == (bot.user and bot.user.id):
        return
    vc = member.guild.voice_client
    if vc is None or vc.channel is None:
        return
    if before.channel == vc.channel and not any(not m.bot for m in vc.channel.members):
        channel_name = vc.channel.name
        await vc.disconnect()
        log.info("Войс %s опустел — вышел, привязку чата сохранил", channel_name)


def main() -> None:
    from bot_health import maybe_start_health_server

    maybe_start_health_server()
    bot.run(require_token(), log_handler=None)


if __name__ == "__main__":
    main()

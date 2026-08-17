"""Modal-деплой бота: спит $0, просыпается по /join в дискорде, умирает на скуке.

Два образа:
  БОЛЬШОЙ (torch+silero) — только для bot_runner, там простаиваем.
  МАЛЕНЬКИЙ (nacl+fastapi) — для вебхука; верификация URL Discord
  требует ответ <3с, холодный образ 2 ГБ туда не влезал бы.

Персистентные привязки (bindings/voices) — на Modal Volume.
"""

import fastapi
import modal

app = modal.App("ds-bot")

_BOT_IMAGE = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("libopus0")
    .pip_install("torch", index_url="https://download.pytorch.org/whl/cpu")
    .pip_install(
        "discord.py[voice]>=2.4",
        "edge-tts>=6.1",
        "imageio-ffmpeg>=0.5",
        "python-dotenv>=1.0",
        "numpy>=1.26",
        "scipy>=1.11",
        "omegaconf>=2.3",
        "soundfile>=0.12",
        "num2words>=0.5",
        "piper-tts>=1.2",
        "emoji>=2.12",
        "fastapi",
    )
    .run_commands(
        'python -c "import torch; torch.set_num_threads(2); '
        "torch.hub.load('snakers4/silero-models', 'silero_tts', language='ru', speaker='v5_1_ru', trust_repo=True)\""
    )
    .add_local_dir(
        ".",
        remote_path="/root/app",
        ignore=[
            ".venv/**",
            ".git/**",
            ".env",
            ".env.*",
            "bindings.json",
            "voices.json",
            "samples/**",
            "voices_piper/**",
            "voices_custom/**",
            "**/__pycache__/**",
            ".pytest_cache/**",
            "**/*.pyc",
        ],
    )
)

_WEBHOOK_IMAGE = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("pynacl>=1.5", "fastapi[standard]>=0.115")
    .add_local_file("interactions_core.py", "/root/interactions_core.py")
)

queue = modal.Queue.from_name("ds-bot-commands", create_if_missing=True)
status = modal.Dict.from_name("ds-bot-state", create_if_missing=True)
volume = modal.Volume.from_name("ds-bot-data", create_if_missing=True)


@app.function(
    image=_BOT_IMAGE,
    volumes={"/root/app/data": volume},
    secrets=[modal.Secret.from_name("ds-bot-secrets")],
    timeout=86400,
    cpu=1.0,
    memory=4096,
)
def bot_runner() -> None:
    import os
    import sys
    import threading
    import time

    status.put("runner-alive", time.time())  # родился — сразу отмечаемся, до импорта бота

    def _heartbeat_thread() -> None:  # бьётся независимо от asyncio — пока импорты/логин/торч
        while True:
            try:
                status.put("runner-alive", time.time())
            except Exception:
                pass
            time.sleep(30)

    threading.Thread(target=_heartbeat_thread, daemon=True).start()
    sys.path.insert(0, "/root/app")
    os.chdir("/root/app")
    os.environ.setdefault("DATA_DIR", "/root/app/data")
    os.environ.setdefault("TTS_ENGINE", "silero")
    os.environ.setdefault("COMMAND_QUEUE", "ds-bot-commands")
    os.environ.setdefault("MODAL_WATCHDOG", "1")

    from bot import main

    main()


@app.function(
    image=_WEBHOOK_IMAGE,
    secrets=[modal.Secret.from_name("ds-bot-secrets")],
    min_containers=1,
    cpu=0.125,
    memory=512,
)
@modal.fastapi_endpoint(method="POST")
async def interactions(request: fastapi.Request):
    """Приёмник взаимодействий Discord: подпись, пинг, команды -> очередь."""
    import os

    from interactions_core import parse_interaction, parse_raw_body, verify_signature

    body = await request.body()
    public_key = os.environ.get("DISCORD_PUBLIC_KEY")
    if not public_key:
        return fastapi.responses.JSONResponse(
            content={"error": "server misconfigured: no public key"}, status_code=500
        )
    if not verify_signature(
        public_key,
        request.headers.get("x-signature-timestamp", ""),
        body,
        request.headers.get("x-signature-ed25519", ""),
    ):
        return fastapi.responses.JSONResponse(
            content={"error": "invalid request signature"}, status_code=401
        )

    try:
        payload = parse_raw_body(body)
    except ValueError:
        return fastapi.responses.JSONResponse(content={"error": "bad body"}, status_code=400)

    if payload.get("type") == 1:  # пинг Discord при верификации URL
        return fastapi.responses.JSONResponse(content={"type": 1})

    command = parse_interaction(payload)
    if command is None:
        return fastapi.responses.JSONResponse(
            content={"error": "unsupported interaction type"}, status_code=400
        )

    import time as _time

    ts = await status.get.aio("runner-alive", default=None)
    alive = ts is not None and _time.time() - ts < 120
    command["ts"] = _time.time()

    try:
        if command["command"] == "join":
            await queue.put.aio(command, timeout=2)
            if alive:
                reply = "Секундочку, захожу."
            else:
                await status.put.aio("runner-alive", _time.time())
                await bot_runner.spawn.aio()
                reply = "Принято! Просыпаюсь — первый запуск займёт 2–3 минуты, потом зайду в войс."
        else:
            if alive:
                await queue.put.aio(command, timeout=2)
                reply = "Ок."
            else:
                reply = "Сплю. Сначала /join — проснусь, тогда команды пойдут как обычно."
    except Exception:
        return fastapi.responses.JSONResponse(
            content={"error": "очередь облака не отвечает — попробуй через минуту"}, status_code=500
        )
    return fastapi.responses.JSONResponse(content={"type": 4, "data": {"content": reply}})

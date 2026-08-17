"""Modal-деплой бота: спит $0, просыпается по /join в дискорде, умирает на скуке.

Два образа:
  БОЛЬШОЙ (torch+silero) — только для bot_runner, там простаиваем.
  МАЛЕНЬКИЙ (nacl+fastapi) — для вебхука; верификация URL Discord
  требует ответ <3с, холодный образ 2 ГБ туда не влезал бы.

Персистентные привязки (bindings/voices) — на Modal Volume.
"""

import modal

app = modal.App("ds-bot")

_BOT_IMAGE = (
    modal.Image.debian_slim(python_version="3.12")
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
    )
    .run_commands(
        'python -c "import torch; torch.set_num_threads(2); '
        "torch.hub.load('snakers4/silero-models', 'silero_tts', language='ru', speaker='v5_1_ru', trust_repo=True)\""
    )
    .add_local_dir(".", remote_path="/root/app")
)

_WEBHOOK_IMAGE = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("pynacl>=1.5", "fastapi[standard]>=0.115")
    .add_local_file("interactions_core.py", "/root/interactions_core.py")
)

queue = modal.Queue.from_name("ds-bot-commands", create_if_missing=True)
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

    sys.path.insert(0, "/root/app")
    os.chdir("/root/app")
    os.environ.setdefault("DATA_DIR", "/root/app/data")
    os.environ.setdefault("TTS_ENGINE", "silero")
    os.environ.setdefault("COMMAND_QUEUE", "ds-bot-commands")
    os.environ.setdefault("MODAL_WATCHDOG", "1")

    from bot import main

    main()


@app.function(image=_WEBHOOK_IMAGE, secrets=[modal.Secret.from_name("ds-bot-secrets")])
@modal.fastapi_endpoint(method="POST")
async def interactions(request):  # fastapi.Request
    """Приёмник взаимодействий Discord: подпись, пинг, команды -> очередь."""
    import os

    import fastapi

    from interactions_core import parse_interaction, parse_raw_body, verify_signature

    body = await request.body()
    if not verify_signature(
        os.environ["DISCORD_PUBLIC_KEY"],
        request.headers.get("x-signature-timestamp", ""),
        body,
        request.headers.get("x-signature-ed25519", ""),
    ):
        return fastapi.responses.JSONResponse(
            content={"error": "invalid request signature"}, status_code=401
        )

    payload = parse_raw_body(body)

    if payload.get("type") == 1:  # пинг Discord при верификации URL
        return fastapi.responses.JSONResponse(content={"type": 1})

    command = parse_interaction(payload)
    if command is None:
        return fastapi.responses.JSONResponse(
            content={"error": "unsupported interaction type"}, status_code=400
        )

    queue.put(command)

    if command["command"] == "join":
        bot_runner.spawn()
        reply = "Принято! Просыпаюсь — первый запуск займёт 2–3 минуты, потом зайду в войс."
    else:
        reply = "Принято!"
    return fastapi.responses.JSONResponse(content={"type": 4, "data": {"content": reply}})

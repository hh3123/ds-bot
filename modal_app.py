"""Modal-деплой бота: спит $0, просыпается по /join в дискорде, умирает на скуке.

two functions:
  interactions  — HTTP-приёмник слэш-команд Discord (подпись Ed25519),
                  кладёт команды в ModerQueue и будит раннера.
  bot_runner    — сам бот: gateway + войс + своя очередь команд.
                  Умирает сам, когда 10 минут нет войса (WATCHDOG в bot.py).

Персистентные привязки (bindings/voices) лежат на Modal Volume.
"""

import modal

image = (
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
        "fastapi[standard]>=0.115",
    )
    .run_commands(
        'python -c "import torch; torch.set_num_threads(2); '
        "torch.hub.load('snakers4/silero-models', 'silero_tts', language='ru', speaker='v5_1_ru', trust_repo=True)\""
    )
    .add_local_dir(".", remote_path="/root/app")
)

app = modal.App("ds-bot", image=image)

queue = modal.Queue.from_name("ds-bot-commands", create_if_missing=True)
volume = modal.Volume.from_name("ds-bot-data", create_if_missing=True)


@app.function(
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


@app.function(secrets=[modal.Secret.from_name("ds-bot-secrets")])
@modal.fastapi_endpoint(method="POST")
def interactions(body: bytes, headers: dict) -> dict:
    """Приёмник взаимодействий Discord: подпись + раскладка слэш-команд."""
    import os

    from interactions_core import parse_interaction, parse_raw_body, verify_signature

    def fail(status: int, msg: str) -> dict:
        return {"status_code": status, "body": msg}

    if not verify_signature(
        os.environ["DISCORD_PUBLIC_KEY"],
        headers.get("x-signature-timestamp", ""),
        body,
        headers.get("x-signature-ed25519", ""),
    ):
        return fail(401, "invalid request signature")

    payload = parse_raw_body(body)

    if payload.get("type") == 1:  # пинг Discord при верификации URL
        return {"type": 1}

    command = parse_interaction(payload)
    if command is None:
        return fail(400, "unsupported interaction type")

    queue.put(command)

    if command["command"] == "join":
        bot_runner.spawn()
        reply = "Принято! Просыпаюсь — первый запуск займёт 2–3 минуты, потом зайду в войс."
    else:
        reply = "Принято!"
    return {"type": 4, "data": {"content": reply}}

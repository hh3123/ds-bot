# Промпт новой сессии: TTS-бот Allah в Modal

## Что это
Discord TTS-бот (Silero ru, локальная высокая скорость синтеза) на бесплатном облаке Modal.
Репо: https://github.com/hh3123/ds-bot (main). Локаль: C:/Users/mayer/Desktop/TTS_BOT.

## Текущая армия
- Вебхук (всегда тёплый, ~$7/мес): https://nylahmikaelakpyygk5411--ds-bot-interactions.modal.run
- Раннер bot_runner: спавнится дискорд-/join через вебхук; умирает сам через 10 мин пустого войса (watchdog → `await bot.close()`, НЕ os._exit — см. правило 0).
- Бюджет: $30 фри-кредитов/мес; раннер ~8¢/час.
- Workspace: nylahmikaelakpyygk5411, CLI токен сидит в C:\Users\mayer\.modal.toml.

## Апп-структура (modal_app.py)
- `_WEBHOOK_IMAGE` (nacl+fastapi, 0.125c/512MB, min_containers=1) → `interactions(request: fastapi.Request)` — подпись Ed25519 (pynacl), parse в interactions_core, команды в Modal Queue `ds-bot-commands`, флаг жизни в Modal Dict `ds-bot-state`.
- `_BOT_IMAGE` (torch CPU + silero, libopus0, 1c/4096MB, timeout=86400) → `bot_runner` запускает bot.py; heartbeat-поток пишет флаг каждые 30с с первой строки; watchdog WATCHDOG_IDLE_SEC default 600.
- Volume ds-bot-data (bindings.json, voices.json) в /root/app/data (DATA_DIR).

## Главные правила оперирования
0. **СМЕРТЬ РАННЕРА = ТОЛЬКО `await bot.close()` (нормальный возврат из функции). os._exit/любой аномальный выход ЗАПРЕЩЁН**: контейнер, сдохший посреди spawned-вызова, Modal считает крэшем, а deployed-аппу Modal перезапускает БЕСКОНЕЧНО (guide/retries) — раннер-зомби логинится через секунды после «суицида». Именно это гоняло бота по кругу 2 часа 17.08 (лог «ухожу спать» 22:54/23:53 + новый «logging in» через 5с). Диагнозы «зависший Dict.put» и «GC сожрал» того вечера были ложными следами — реальный механизм платформенный.
1. НИКОГДА не дебаж `modal run` attached — таймаут прибьёт процесс: ловил казус «бот залез и сдох через минуту». Спавн раннера ТОЛЬКО против deployed-функции (`modal.Function.from_name('ds-bot','bot_runner').spawn.aio()`); спавн от локального импорта modal_app рождает эфемерного зомби, который тоже бьёт флаг. Работа через `modal deploy` + (если насильно убивать) `modal app stop ds-bot --yes` + вычистка флага.
2. Флаг runner-alive: пишется потоком каждые 30с; окно свежести вебхука 120с. После любой смерти флаг врёт до ~2 мин — либо жди, либо поп/обнули его в Dict (put 0). Если спавн в вебхуке упал — вебхук сам обнуляет флаг.
3. Сильные ссылки на asyncio.create_task — иначе GC сожрёт watchdog (был главным червём лета).
4. Логи: `python -m modal app logs ds-bot` (хвост, задержка до пары минут); smoke: `curl -X POST <webhook-url> -d "{}"` → ждём 401.
5. Тест: pytest tests/ -q → 59/59; деплой: `python -m modal deploy modal_app.py` (~30-60с при тёплом кэше; ~5 мин при rebuild).

## Секреты (Modal Secret ds-bot-secrets)
- DISCORD_TOKEN (в секрете только; НЕ вставлять в чат — маскируется и теряется).
- DISCORD_PUBLIC_KEY — из дев-портала Discord (Application → General Information).

## Несёркизы/остывшие гвозди
- deathsloop R1→R2 РАЗГАДАН (18.08): не очередь и не GC — os._exit посреди spawned-вызова == крэш для Modal → deployed-апп перезапускал инпут бесконечно. Лечение — правило 0. Задублированные /join из очереди гаснут idempotent-диспетчером + TTL 600с.
- Discord 3s webhook deadline ловится: slim-образ + min_containers=1.
- Grid fleet: Render (старая площадка) — юзер к удалению; UPTIMERobot монитор туда же.

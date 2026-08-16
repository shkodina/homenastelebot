# Что уже сделано

Исходник по духу — SmartHomeBot (aiogram 2, env, whitelist через `str in`, ответ посторонним, bash на хосте). Этот репозиторий — **другой** бот: YAML, точный id, тихий игнор, кнопки, без удалённого shell.

## Сделано

- Python-бот, aiogram 3, меню кнопками, справка.
- Whitelist: полное совпадение id, остальные игнор.
- Конфиг из `xtmp-cnf.yaml`; секреты не в git.
- SOCKS5 из YAML (для Telegram API и для Cursor HTTP).
- Docker: `Dockerfile.base` + `Dockerfile`, compose, `run.sh`, `compose.sh`.
- NAS → Docker → PS / Restart. NAS → System → Uptime, DF, Top. NAS → FTP. NAS → URL (таблица с nas.home, `extra_hosts`).
- Cursor → Status (usage через api2.cursor.sh) / Use (облачный агент без репо).
- Use принимает следующее сообщение целиком: текст, фото, стикер, gif, документ, аудио, voice, видео. Картинки — `prompt.images`, остальное в текст. В конец промпта дописывается протокол `TELEGRAM_FILES`; файлы из ответа уходят в Telegram.
- Хостовый вотчер restart/FTP и его start/stop вместе с `compose.sh`.
- Автозапуск: systemd `homenasbot` + `homenasbot-watch` через `scripts/install-autostart.sh`.
- Тесты локальные, папка `tests/` в gitignore; боевые id/прокси из тестов вычищены.

## Грабли (не повторять)

1. **Allowlist на `dp.update.outer_middleware`** + `data["event_from_user"]` — user ещё нет, все апдейты `is not handled`, бот «молчит», хотя polling уже есть. Чинить: middleware на message/callback, `from_user` с события.
2. **Голый `git` / `docker` в terminal allowlist Cursor** — подтянет `push` и `compose up`. Для RO только конкретные подкоманды.
3. **Тесты с боевым SOCKS5 и Telegram id** — нельзя в публичный git. Либо фиктивные значения, либо `tests/` в gitignore (сейчас оба).
4. **`socks5h://` в URL** — `python-socks` в aiogram 3.15 падает. Схема `socks5://`, rdns включает сам aiogram.
5. Restart из контейнера через socket убил бы сам бот и дал бы ему власть над всем Docker. Поэтому флаг + внешний скрипт, skip имени бота.
6. `df` без bind `/` → `/host` показывает диск контейнера, не NAS.
7. `nas.home` с хоста часто не резолвится (нет в `/etc/hosts`), а nginx отвечает на `Host: nas.home`. В контейнере без `extra_hosts` кнопка URL получит DNS error. Алиас: `nas.home:192.168.88.25` в compose.
8. **`POST /v1/agents` создаёт агента, но HTTP-ответ клиенту не приходит** (таймаут, 0 байт). GET списка/агента/run работает. Не считать таймаут фатальным: задать свой `agentId` (`bc-<uuid>`), после TimeoutError сделать `GET /v1/agents/{id}` и опросить run. Лог: `cursor prompt unexpected error` + `asyncio.TimeoutError` на POST — это оно.
9. Use без перехвата вложений отвергает фото/файлы (`message.text` пустой). Скачивать через `bot.get_file` / `download_file` (сессия бота уже с SOCKS5). В лог не писать содержимое файлов и текст промпта.
10. Облачный агент пишет файлы в workspace, но **не в `artifacts/`** — `GET /v1/agents/{id}/artifacts` будет `items: []`. Бот дописывает в промпт протокол: копировать в `artifacts/` и закрыть ответ блоком `===TELEGRAM_FILES===`. Для мелких файлов ещё `data` (base64), потому что индекс артефактов иногда пустой.

## Сознательно нет (пока не просили)

Погода, echo, произвольный bash, отдельные кнопки restart по контейнеру, follow-up в тот же Cursor-агент, альбомы из нескольких Telegram-сообщений как один промпт.

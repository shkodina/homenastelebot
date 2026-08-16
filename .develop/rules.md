# Правила

## Секреты и публичный репозиторий

- Всё секретное, личное и выдающее расположение/железо — только в `xtmp-cnf.yaml`.
- Шаблон `xtmp-*` в `.gitignore`. Рядом коммитится только `cnf.example.yaml` с плейсхолдерами.
- Не коммитить: токен бота, Telegram user id, логин/пароль прокси, внутренние IP, реальные mount-пути дисков. Исключение: `extra_hosts` для `nas.home` в compose — это адрес самого хоста бота, без него URL из контейнера не резолвится.
- `tests/` в `.gitignore`. Локальные тесты — только фиктивные id/хосты/пароли.
- В логах не писать token, password, `allowed_ids`, текст промпта Use и содержимое вложений. Прокси логировать как `type://host:port`.
- Перед пушем: `git status` — `xtmp-cnf.yaml` и `tests/` должны быть ignored.

## Доступ к боту

- Отвечать **только** при полном совпадении `message.from_user.id` с `telegram.allowed_ids` (int, не подстрока).
- Остальных **молча игнорировать**. Не писать «нет прав».
- Allowlist вешать на `router.message` и `router.callback_query`, user брать из `Message`/`CallbackQuery.from_user`. Не полагаться на `event_from_user` в `Update` outer middleware — из-за этого апдейты уходили в `is not handled`.

## Telegram UX

- Язык ответов: русский, коротко, для человека.
- Навигация — inline-кнопки и вложенные меню. `Назад` обязателен.
- `callback_data`: `menu:…` для экранов, `cmd:…` для действий. Лимит Telegram — 64 байта.
- Результат команды — **новое сообщение**, меню не затирать (история uptime/df/ps/Use должна оставаться).
- Любой апдейт от своего id (не команда) → корневое меню, **кроме** режима Use: следующее сообщение целиком (текст, картинка, файл, аудио) уходит в Cursor. `/start` и любая кнопка кроме Use сбрасывают ожидание.
- Опасные действия (restart docker и т.п.) — отдельное подтверждение кнопкой.

## Что бот не делает сам

- Не даёт shell на хосте, нет команды `bash`.
- Restart контейнеров **не** через Docker API, даже если socket примонтирован. Только флаг-файл + хостовый вотчер.
- `docker.sock` — только для read (`ps`). Restart делает `scripts/docker-restart-watch.sh`, его жизненный цикл — `./compose.sh`.
- Cursor Use — облачный агент **без репозитория**, не локальный runtime на NAS.

## Стек и деплой

- Python 3, **aiogram 3** (не v2 как в старом SmartHomeBot).
- Два образа: `Dockerfile.base` (ОС + pip) → `homenasbot-base`, `Dockerfile` (код) → `homenasbot`.
- После смены `requirements.txt` пересобирать **base**. После смены `bot/` достаточно app-образа: `docker build -t homenasbot:latest -f Dockerfile .` и `docker compose up -d --no-build --force-recreate homenasbot` (обычный `compose.sh restart` **не** подхватывает новый image и не extra_hosts).
- Сборка с нуля: `./run.sh`. Жизнь контейнера + вотчер: `./compose.sh start|restart|stop`. Автозапуск: `./scripts/install-autostart.sh`.
- Код в образ копируется, YAML монтируется в рантайме. Секреты в image не класть.
- Compose: `/` → `/host:ro` (df), `docker.sock:ro` (ps), `./xtmp-docker` (флаги), `extra_hosts: nas.home:192.168.88.25`.

## Как добавлять команду

1. Кнопка в `bot/keyboards.py`.
2. Хендлер в `bot/handlers.py`.
3. Логика в отдельном модуле, не раздувать handlers.
4. Пути/сокеты/флаги/URL — в YAML + `bot/config.py`, не хардкодить хостовые пути в коде.
5. Справка (`HELP_TEXT`) и `README.md` / `.develop/done.md` / `.develop/architecture.md`.
6. Локально: `python3 -m unittest discover -s tests -v` (фикстуры без секретов).
7. Пересобрать app-образ и recreate контейнера (см. выше).

Новые бытовые команды NAS — во вложенные меню. Cursor — в меню Cursor. В корень без нужды не класть.

# homenastelebot

Для следующего агента: сначала читай [`.develop/`](.develop/) — правила, архитектура, что уже сделано.

Telegram-бот для домашнего NAS. Стек: **Python 3** + [aiogram 3](https://docs.aiogram.dev/).

Секреты, whitelist и любые данные, которые выдают расположение или личные характеристики, живут только в `xtmp-cnf.yaml` (шаблон `xtmp-*` уже в `.gitignore`).

## Что умеет

- отвечает **только** на полный совпадающий Telegram user id из `telegram.allowed_ids`
- все остальные обращения **молча игнорирует**
- меню: `/start` → **NAS** | **Cursor** → **Docker** | **System**

## Конфиг

Скопируй пример и заполни:

```bash
cp cnf.example.yaml xtmp-cnf.yaml
```

```yaml
telegram:
  token: "токен от @BotFather"
  allowed_ids:
    - 123456789          # только точное совпадение id
  proxy:
    enabled: true
    type: socks5
    host: 10.0.0.1
    port: 1080
    username: user
    password: password

nas:
  uptime_path: /proc/uptime
  host_root: /host

docker:
  socket: /var/run/docker.sock
  restart_flag: /xtmp-docker/restart
  restart_skip:
    - homenasbot

cursor:
  api_key: "crsr_..."   # User API Key с https://cursor.com/dashboard/api
```

`nas.host_root` — корень хоста, примонтированный в контейнер (для `df`). Restart не дергает Docker API: бот пишет флаг, хостовый скрипт перезапускает контейнеры и удаляет файл.

Вотчер поднимается и гасится вместе с ботом:

```bash
./compose.sh start
./compose.sh restart
./compose.sh stop
```

Автозапуск после ребута (контейнер + вотчер):

```bash
./scripts/install-autostart.sh
```

`nas.uptime_path` — путь к файлу `/proc/uptime` (ядро хоста, не контейнера). Если бот крутится на NAS в Docker, этого достаточно.

Кнопка **Cursor** ходит в usage API аккаунта: дни до сброса биллинга, процент дефолтных токенов (Auto / Composer) и процент специализированных / API-моделей. Официального персонального usage API нет — бот обменивает User API Key (`crsr_...`) на session token и читает `GetCurrentPeriodUsage`. Ключ берётся в [Dashboard → API Keys → User API Keys](https://cursor.com/dashboard/api?section=user-keys): **New API Key**, скопировать сразу, вставить в `cursor.api_key`. Это не Cloud Agents SDK key и не Enterprise Admin key. Если ключ не задан, кнопка ответит инструкцией.

SOCKS5 для Telegram API задаётся в `telegram.proxy`. DNS резолвится через прокси (`rdns`). Чтобы ходить напрямую, поставь `enabled: false`.

## Запуск локально

```bash
pip install -r requirements.txt
python3 -m bot
```

Проверка логики без Telegram:

```bash
python3 -m unittest discover -s tests -v
```

## Запуск в Docker

Два образа: `homenasbot-base` (ОС + зависимости) и `homenasbot` (код бота). YAML монтируется в рантайме, в образ не копируется.

```bash
./run.sh
```

Или вручную:

```bash
docker build --network=host -t homenasbot-base:latest -f Dockerfile.base .
docker build --network=host -t homenasbot:latest -f Dockerfile .
docker compose up -d --no-build
```

Пересборка только base: `docker compose --profile build build homenasbot-base`.

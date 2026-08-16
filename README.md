# homenastelebot

Для следующего агента: сначала читай [`.develop/`](.develop/) — правила, архитектура, что уже сделано.

Telegram-бот для домашнего NAS. Стек: **Python 3** + [aiogram 3](https://docs.aiogram.dev/).

Секреты, whitelist и любые данные, которые выдают расположение или личные характеристики, живут только в `xtmp-cnf.yaml` (шаблон `xtmp-*` уже в `.gitignore`).

## Что умеет

- отвечает **только** на полный совпадающий Telegram user id из `telegram.allowed_ids`
- все остальные обращения **молча игнорирует**
- меню: `/start` → **NAS** | **Cursor** → Docker / System / FTP / URL; Cursor → **Status** / **Use**

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
  urls_page: http://nas.home/

docker:
  socket: /var/run/docker.sock
  restart_flag: /xtmp-docker/restart
  restart_skip:
    - homenasbot

cursor:
  api_key: "crsr_..."   # User API Key с https://cursor.com/dashboard/api

ftp:
  service: vsftpd        # хостовый systemd-юнит, On/Off через вотчер

vsftpd:
  send_on_start:
    send_login_data: true
    send_server_info: true
    send_in_splited_messages: true   # с телефона — отдельные сообщения для копирования
  user: "FTP_USER"
  pass: "FTP_PASSWORD"
  endpoints:
    internal: "ftp://192.168.88.25:21"
    external: "ftp://217.15.195.187:54321"
```

`nas.host_root` — корень хоста, примонтированный в контейнер (для `df`). Restart и FTP не дергают systemd из контейнера: бот пишет флаг, хостовый скрипт выполняет действие и удаляет файл. **FTP → On** делает `systemctl enable --now vsftpd`, **Off** — `disable --now` (после ребута остаётся как последнее нажатие). Если в `vsftpd.send_on_start` включены флаги, после успешного On бот пришлёт логин/пароль и адреса: `send_in_splited_messages: true` — отдельными сообщениями (удобно копировать с телефона), `false` — одним блоком.

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

Кнопка **URL** ходит на домашнюю страницу `nas.home` (ключ `nas.urls_page`) и присылает сводную табличку внутренних и внешних ссылок. Запрос идёт напрямую, без SOCKS5.

Раздел **Cursor**: **Status** ходит в usage API аккаунта (дни до сброса биллинга, проценты токенов). **Use** берёт следующее текстовое сообщение и запускает облачного агента без репозитория (`POST /v1/agents`), затем присылает ответ. Официального персонального usage API нет — бот обменивает User API Key (`crsr_...`) на session token и читает `GetCurrentPeriodUsage`. Тот же ключ идёт в Cloud Agents API. Ключ берётся в [Dashboard → API Keys → User API Keys](https://cursor.com/dashboard/api?section=user-keys): **New API Key**, скопировать сразу, вставить в `cursor.api_key`. Если ключ не задан, кнопки ответят инструкцией.

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

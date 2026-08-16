# Архитектура

## Дерево меню (сейчас)

```
/start
├── NAS
│   ├── Docker      menu:nas.docker
│   │   ├── PS      cmd:nas.docker.ps
│   │   └── Restart cmd:nas.docker.restart → подтверждение
│   ├── System      menu:sys
│   │   ├── Uptime  cmd:sys.uptime
│   │   ├── DF      cmd:sys.df
│   │   └── Top     cmd:sys.top
│   ├── FTP         menu:nas.ftp
│   │   ├── On      cmd:nas.ftp.on
│   │   └── Off     cmd:nas.ftp.off
│   └── URL         cmd:nas.url
├── Cursor          menu:cursor
│   ├── Status      cmd:cursor.usage
│   └── Use         cmd:cursor.use  → следующее сообщение = промпт
└── Справка         menu:help
```

Обычный текст (не команда) → корневое меню. Исключение: после **Use** следующее сообщение любого типа уходит в Cursor, а не в корень. `/start` и любая другая кнопка (не Use) сбрасывают ожидание.

## Файлы

```
bot/__main__.py       polling, SOCKS5 session, allowlist + сброс Cursor-wait на callback
bot/config.py         xtmp-cnf.yaml → Config
bot/middleware.py     точный whitelist; CursorWaitCancelMiddleware
bot/handlers.py       только роутинг Telegram
bot/keyboards.py      inline-клавиатуры
bot/cursor_usage.py   Status: usage API аккаунта (api2.cursor.sh)
bot/cursor_agent.py   Use: POST api.cursor.com/v1/agents, опрос run
bot/cursor_wait.py    после Use следующее сообщение — промпт
bot/cursor_input.py   Use: текст/картинка/файл/аудио из Telegram → prompt
bot/ftp.py            FTP on/off через флаг-файл + вотчер
bot/sysload.py        top: /host/proc loadavg, meminfo, stat, топ CPU
bot/urls.py           URL: GET nas.home, таблица ссылок в текст
bot/disks.py          df: /host/proc/1/mounts + statvfs, skip boot/tmpfs/<8G
bot/dockers.py        ps через HTTP на docker.sock; restart = запись флага
scripts/docker-restart-watch.sh   хост: флаг → docker restart / systemctl vsftpd
compose.sh            up/restart/stop compose + вотчер
scripts/install-autostart.sh  systemd: контейнер + вотчер
deploy/*.service.in           шаблоны юнитов
cnf.example.yaml      публичный шаблон
xtmp-cnf.yaml         локальные секреты, в git нет
```

## Конфиг (смысл ключей)

`telegram.token`, `telegram.allowed_ids` — обязательны.

`telegram.proxy` — SOCKS5 для api.telegram.org (`enabled`, `type`, `host`, `port`, `username`, `password`). DNS через прокси (`rdns` в aiogram). Без прокси с этой сети Telegram часто не открывается. Status/Use Cursor ходят через тот же прокси.

`nas.uptime_path` — внутри контейнера обычно `/proc/uptime` (uptime ядра хоста).

`nas.host_root` — `/host` в контейнере, bind корня хоста. DF показывает **хостовые** mountpoint'ы.

`nas.urls_page` — страница сводной таблички, по умолчанию `http://nas.home/`. Запрос **без** Telegram-прокси. В compose: `extra_hosts: nas.home:192.168.88.25` (это сам хост бота).

`cursor.api_key` — User API Key (`crsr_...`) с Dashboard → API Keys. Один ключ на Status (usage) и Use (Cloud Agents).

`docker.socket` — `/var/run/docker.sock`.

`docker.restart_flag` — `/xtmp-docker/restart`. Содержимое: `restart` и `skip=homenasbot`.

`ftp` / `vsftpd` — юнит, флаг on/off, опционально логин/адреса после On.

## Cursor Use

1. Кнопка Use → `arm_use(user_id)`, сообщение «жду запрос».
2. Следующий апдейт: скачать вложения из Telegram (`getFile` через сессию бота с SOCKS5).
3. Собрать prompt: картинки (png/jpeg/gif/webp, до 5, до 15 МБ) → `prompt.images`; текст/подпись и прочие файлы → `prompt.text` (utf-8 как текст, бинарь как base64, лимит 4 МБ).
4. `POST https://api.cursor.com/v1/agents` с заранее заданным `agentId` (`bc-<uuid>`), без репозитория.
5. Ответ POST часто **не приходит** (таймаут, 0 байт), хотя агент на сервере уже есть. Тогда `GET /v1/agents/{id}` и опрос `GET .../runs/{runId}` до FINISHED/ERROR.
6. Результат — новым сообщением (нарезка по 4096). Меню не затирать.

Альбом из нескольких сообщений Telegram — несколько апдейтов; в запрос попадает первое.

## URL

`GET nas.urls_page` напрямую, HTML-таблица → текст со ссылками. Без SOCKS5.

## PS: что слать в Telegram

Только имя контейнера, «работает», сколько живёт. Без image, портов, id.

## Restart

Бот **не** вызывает `docker restart`. Пишет флаг → хостовый вотчер. Опасная кнопка с «Да, перезапустить».

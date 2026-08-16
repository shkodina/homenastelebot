from __future__ import annotations

import logging
from pathlib import Path

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from bot.config import Config, proxy_url
from bot.cursor_agent import SETUP_TEXT, cursor_prompt, split_telegram_text
from bot.cursor_input import (
    build_cursor_prompt,
    download_attachments,
    message_text,
    telegram_file_specs,
)
from bot.cursor_usage import cursor_usage_text
from bot.cursor_wait import (
    NasDraft,
    arm_nas,
    arm_use,
    cancel_use,
    consume_nas,
    consume_use,
    put_nas_draft,
    take_nas_draft,
)
from bot.cursor_media import send_outgoing_files
from bot.cursor_nas import (
    BUSY_TEXT,
    NasBusy,
    NasTimeout,
    answer_from_job,
    build_nas_prompt,
    enqueue_job,
    wait_job,
)
from bot.disks import nas_df_text
from bot.dockers import nas_docker_ps_text, request_restart
from bot.ftp import apply_ftp, ftp_info_messages, ftp_menu_text
from bot.keyboards import (
    cursor_keyboard,
    cursor_nas_confirm_keyboard,
    docker_keyboard,
    docker_restart_keyboard,
    ftp_keyboard,
    help_keyboard,
    nas_keyboard,
    root_keyboard,
    sys_keyboard,
)
from bot.sysload import sys_top_text
from bot.uptime import nas_uptime_text
from bot.urls import nas_urls_text

logger = logging.getLogger(__name__)

router = Router()

ROOT_TEXT = "Домашний NAS-бот.\nВыбери раздел:"
NAS_TEXT = "NAS — доступные команды:"
CURSOR_TEXT = "Cursor — доступные команды:"
USE_WAIT_TEXT = "Жду запрос. Следующее сообщение — текст, картинка, файл или аудио — уйдёт в Cursor."
NAS_WAIT_TEXT = (
    "Жду запрос для NAS. Следующее сообщение уйдёт локальному Cursor на хост (полный shell).\n"
    "Запуск только после кнопки Выполнить."
)
SYS_TEXT = "System — доступные команды:"
DOCKER_TEXT = "Docker — доступные команды:"
RESTART_CONFIRM = (
    "Перезапустить все запущенные контейнеры, кроме бота?\n"
    "Запрос уйдёт хостовому скрипту через флаг-файл."
)
HELP_TEXT = (
    "Справка\n"
    "\n"
    "Команды:\n"
    "• /start — главное меню\n"
    "• /help — эта справка\n"
    "• NAS → Docker → PS — запущенные контейнеры\n"
    "• NAS → Docker → Restart — перезапуск контейнеров через хост\n"
    "• NAS → System → Uptime — время работы сервера\n"
    "• NAS → System → DF — место на основных дисках\n"
    "• NAS → System → Top — CPU, RAM, LA, топ процессов\n"
    "• NAS → FTP — включить / выключить vsftpd на хосте\n"
    "• NAS → URL — сводная табличка внутренних и внешних ссылок\n"
    "• Cursor → Status — дни до рефреша и проценты токенов\n"
    "• Cursor → Use — следующее сообщение уйдёт в облачный Cursor; ответ придёт текстом и файлами\n"
    "• Cursor → NAS — локальный агент на хосте с shell; перед запуском кнопка Выполнить\n"
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    if message.from_user is not None:
        cancel_use(message.from_user.id)
    await message.answer(ROOT_TEXT, reply_markup=root_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, reply_markup=help_keyboard())


@router.callback_query(F.data == "menu:root")
async def menu_root(callback: CallbackQuery) -> None:
    await callback.message.edit_text(ROOT_TEXT, reply_markup=root_keyboard())
    await callback.answer()


@router.callback_query(F.data == "menu:nas")
async def menu_nas(callback: CallbackQuery) -> None:
    await callback.message.edit_text(NAS_TEXT, reply_markup=nas_keyboard())
    await callback.answer()


@router.callback_query(F.data == "menu:cursor")
async def menu_cursor(callback: CallbackQuery) -> None:
    await callback.message.edit_text(CURSOR_TEXT, reply_markup=cursor_keyboard())
    await callback.answer()


@router.callback_query(F.data == "menu:sys")
async def menu_sys(callback: CallbackQuery) -> None:
    await callback.message.edit_text(SYS_TEXT, reply_markup=sys_keyboard())
    await callback.answer()


@router.callback_query(F.data == "menu:help")
async def menu_help(callback: CallbackQuery) -> None:
    await callback.message.edit_text(HELP_TEXT, reply_markup=help_keyboard())
    await callback.answer()


@router.callback_query(F.data == "menu:nas.docker")
async def menu_docker(callback: CallbackQuery) -> None:
    await callback.message.edit_text(DOCKER_TEXT, reply_markup=docker_keyboard())
    await callback.answer()


@router.callback_query(F.data == "menu:nas.ftp")
async def menu_ftp(callback: CallbackQuery, config: Config) -> None:
    await callback.message.edit_text(
        ftp_menu_text(config.host_root, config.ftp.service),
        reply_markup=ftp_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.in_({"cmd:sys.uptime", "cmd:nas.uptime"}))
async def cmd_sys_uptime(callback: CallbackQuery, config: Config) -> None:
    await callback.message.answer(nas_uptime_text(config.uptime_path))
    await callback.answer()


@router.callback_query(F.data.in_({"cmd:sys.df", "cmd:nas.df"}))
async def cmd_sys_df(callback: CallbackQuery, config: Config) -> None:
    await callback.message.answer(nas_df_text(config.host_root, config.df_min_bytes))
    await callback.answer()


@router.callback_query(F.data == "cmd:sys.top")
async def cmd_sys_top(callback: CallbackQuery, config: Config) -> None:
    await callback.answer()
    await callback.message.answer(await sys_top_text(config.host_root))


@router.callback_query(F.data == "cmd:cursor.usage")
async def cmd_cursor_usage(callback: CallbackQuery, config: Config) -> None:
    await callback.answer()
    await callback.message.answer(
        await cursor_usage_text(config.cursor_api_key, proxy_url(config))
    )


@router.callback_query(F.data == "cmd:cursor.use")
async def cmd_cursor_use(callback: CallbackQuery) -> None:
    if callback.from_user is not None:
        arm_use(callback.from_user.id)
    await callback.message.answer(USE_WAIT_TEXT)
    await callback.answer()


@router.callback_query(F.data == "cmd:cursor.nas")
async def cmd_cursor_nas(callback: CallbackQuery, config: Config) -> None:
    if not config.cursor_nas.enabled:
        await callback.message.answer("NAS-агент выключен в конфиге.")
        await callback.answer()
        return
    if not config.cursor_api_key:
        await callback.message.answer(SETUP_TEXT)
        await callback.answer()
        return
    if callback.from_user is not None:
        arm_nas(callback.from_user.id)
    await callback.message.answer(NAS_WAIT_TEXT)
    await callback.answer()


@router.callback_query(F.data == "cmd:cursor.nas.yes")
async def cmd_cursor_nas_yes(callback: CallbackQuery, config: Config) -> None:
    await callback.answer()
    user = callback.from_user
    if user is None:
        return
    draft = take_nas_draft(user.id)
    if draft is None:
        await callback.message.answer("Нет черновика. Нажми NAS ещё раз.")
        return
    job_dir = Path(config.cursor_nas.job_dir)
    try:
        job_id = enqueue_job(job_dir, draft.prompt, draft.attachments)
    except NasBusy:
        put_nas_draft(user.id, draft)
        await callback.message.answer(BUSY_TEXT)
        return
    await callback.message.answer("Запускаю на NAS…")
    try:
        job = await wait_job(job_dir, job_id, config.cursor_nas.timeout_sec)
    except NasTimeout:
        await callback.message.answer("Cursor NAS не ответил за отведённое время.")
        return
    except Exception:
        logger.exception("cursor nas wait failed")
        await callback.message.answer("Не удалось дождаться NAS-агента.")
        return
    if str(job.get("status") or "") == "error":
        text, files = answer_from_job(job_dir, job_id)
        await callback.message.answer(text or "Cursor NAS вернул ошибку.")
        return
    text, files = answer_from_job(job_dir, job_id)
    if text:
        for chunk in split_telegram_text(text):
            await callback.message.answer(chunk)
    if files:
        await send_outgoing_files(callback.message, files)


@router.callback_query(F.data == "cmd:nas.url")
async def cmd_nas_url(callback: CallbackQuery, config: Config) -> None:
    await callback.answer()
    await callback.message.answer(await nas_urls_text(config.urls_page))


@router.callback_query(F.data == "cmd:nas.docker.ps")
async def cmd_docker_ps(callback: CallbackQuery, config: Config) -> None:
    await callback.message.answer(nas_docker_ps_text(config.docker_socket))
    await callback.answer()


@router.callback_query(F.data == "cmd:nas.docker.restart")
async def cmd_docker_restart(callback: CallbackQuery) -> None:
    await callback.message.edit_text(RESTART_CONFIRM, reply_markup=docker_restart_keyboard())
    await callback.answer()


@router.callback_query(F.data == "cmd:nas.docker.restart.yes")
async def cmd_docker_restart_yes(callback: CallbackQuery, config: Config) -> None:
    await callback.message.answer(request_restart(config.restart_flag, config.restart_skip))
    await callback.answer()


@router.callback_query(F.data.in_({"cmd:nas.ftp.on", "cmd:nas.ftp.off"}))
async def cmd_ftp_toggle(callback: CallbackQuery, config: Config) -> None:
    await callback.answer()
    action = "on" if callback.data == "cmd:nas.ftp.on" else "off"
    text, ok = await apply_ftp(
        action=action,
        flag_path=config.ftp.flag,
        result_path=config.ftp.result,
        host_root=config.host_root,
        service=config.ftp.service,
    )
    await callback.message.answer(text)
    if ok and action == "on":
        for msg in ftp_info_messages(
            user=config.ftp.user,
            password=config.ftp.password,
            internal=config.ftp.endpoint_internal,
            external=config.ftp.endpoint_external,
            send_login_data=config.ftp.send_login_data,
            send_server_info=config.ftp.send_server_info,
            send_in_split_messages=config.ftp.send_in_split_messages,
        ):
            await callback.message.answer(msg)
    try:
        await callback.message.edit_text(
            ftp_menu_text(config.host_root, config.ftp.service),
            reply_markup=ftp_keyboard(),
        )
    except TelegramBadRequest:
        pass


@router.message()
async def any_message(message: Message, config: Config) -> None:
    user = message.from_user
    if user is not None and consume_nas(user.id):
        try:
            specs = telegram_file_specs(message)
            attachments = await download_attachments(message.bot, specs)
            pairs = [(item.name, item.data) for item in attachments]
            prompt, preview, files = build_nas_prompt(message_text(message), pairs)
        except Exception:
            logger.exception("cursor nas attachment download failed")
            await message.answer("Не удалось скачать вложение из Telegram. Нажми NAS ещё раз.")
            return
        if not message_text(message) and not files:
            await message.answer("Нужен текст или вложение. Нажми NAS ещё раз.")
            return
        put_nas_draft(user.id, NasDraft(prompt=prompt, preview=preview, attachments=files))
        await message.answer(
            f"Запрос на NAS:\n{preview}\n\nНажми Выполнить, чтобы запустить локальный Cursor.",
            reply_markup=cursor_nas_confirm_keyboard(),
        )
        return
    if user is not None and consume_use(user.id):
        try:
            specs = telegram_file_specs(message)
            attachments = await download_attachments(message.bot, specs)
            prompt = build_cursor_prompt(message_text(message), attachments)
        except Exception:
            logger.exception("cursor attachment download failed")
            await message.answer("Не удалось скачать вложение из Telegram. Нажми Use ещё раз.")
            return
        if not prompt.get("text") and not prompt.get("images"):
            await message.answer("Нужен текст или вложение. Нажми Use ещё раз.")
            return
        await message.answer("Отправляю в Cursor…")
        answer = await cursor_prompt(
            config.cursor_api_key,
            prompt,
            proxy_url(config),
        )
        if answer.text:
            for chunk in split_telegram_text(answer.text):
                await message.answer(chunk)
        if answer.files:
            await send_outgoing_files(message, answer.files)
        return
    await message.answer(ROOT_TEXT, reply_markup=root_keyboard())

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from bot.config import Config
from bot.disks import nas_df_text
from bot.dockers import nas_docker_ps_text, request_restart
from bot.keyboards import (
    docker_keyboard,
    docker_restart_keyboard,
    help_keyboard,
    nas_keyboard,
    root_keyboard,
    sys_keyboard,
)
from bot.sysload import sys_top_text
from bot.uptime import nas_uptime_text

router = Router()

ROOT_TEXT = "Домашний NAS-бот.\nВыбери раздел:"
NAS_TEXT = "NAS — доступные команды:"
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
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
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


@router.message()
async def any_message(message: Message) -> None:
    await message.answer(ROOT_TEXT, reply_markup=root_keyboard())

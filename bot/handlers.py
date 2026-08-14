from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from bot.config import Config
from bot.keyboards import help_keyboard, nas_keyboard, root_keyboard
from bot.uptime import nas_uptime_text

router = Router()

ROOT_TEXT = "Домашний NAS-бот.\nВыбери раздел:"
NAS_TEXT = "NAS — доступные команды:"
HELP_TEXT = (
    "Справка\n"
    "\n"
    "Команды:\n"
    "• /start — главное меню\n"
    "• /help — эта справка\n"
    "• NAS → Uptime — время работы сервера\n"
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


@router.callback_query(F.data == "menu:help")
async def menu_help(callback: CallbackQuery) -> None:
    await callback.message.edit_text(HELP_TEXT, reply_markup=help_keyboard())
    await callback.answer()


@router.callback_query(F.data == "cmd:nas.uptime")
async def cmd_nas_uptime(callback: CallbackQuery, config: Config) -> None:
    await callback.message.answer(nas_uptime_text(config.uptime_path))
    await callback.answer()

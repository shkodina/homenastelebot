from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def _keyboard(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=data) for text, data in row]
            for row in rows
        ]
    )


def root_keyboard() -> InlineKeyboardMarkup:
    return _keyboard(
        [
            [("NAS", "menu:nas")],
            [("Справка", "menu:help")],
        ]
    )


def nas_keyboard() -> InlineKeyboardMarkup:
    return _keyboard(
        [
            [("Uptime", "cmd:nas.uptime")],
            [("Назад", "menu:root")],
        ]
    )


def help_keyboard() -> InlineKeyboardMarkup:
    return _keyboard(
        [
            [("NAS", "menu:nas")],
            [("Назад", "menu:root")],
        ]
    )

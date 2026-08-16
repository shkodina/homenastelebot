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
            [("NAS", "menu:nas"), ("Cursor", "cmd:cursor.usage")],
            [("Справка", "menu:help")],
        ]
    )


def nas_keyboard() -> InlineKeyboardMarkup:
    return _keyboard(
        [
            [("Docker", "menu:nas.docker"), ("System", "menu:sys")],
            [("FTP", "menu:nas.ftp"), ("URL", "cmd:nas.url")],
            [("Назад", "menu:root")],
        ]
    )


def sys_keyboard() -> InlineKeyboardMarkup:
    return _keyboard(
        [
            [("Uptime", "cmd:sys.uptime")],
            [("DF", "cmd:sys.df")],
            [("Top", "cmd:sys.top")],
            [("Назад", "menu:nas")],
        ]
    )


def ftp_keyboard() -> InlineKeyboardMarkup:
    return _keyboard(
        [
            [("On", "cmd:nas.ftp.on"), ("Off", "cmd:nas.ftp.off")],
            [("Назад", "menu:nas")],
        ]
    )


def docker_keyboard() -> InlineKeyboardMarkup:
    return _keyboard(
        [
            [("PS", "cmd:nas.docker.ps")],
            [("Restart", "cmd:nas.docker.restart")],
            [("Назад", "menu:nas")],
        ]
    )


def docker_restart_keyboard() -> InlineKeyboardMarkup:
    return _keyboard(
        [
            [("Да, перезапустить", "cmd:nas.docker.restart.yes")],
            [("Отмена", "menu:nas.docker")],
        ]
    )


def help_keyboard() -> InlineKeyboardMarkup:
    return _keyboard(
        [
            [("NAS", "menu:nas"), ("Cursor", "cmd:cursor.usage")],
            [("Назад", "menu:root")],
        ]
    )

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_SERVICE = "vsftpd"
DEFAULT_FLAG = "/xtmp-docker/ftp"
DEFAULT_RESULT = "/xtmp-docker/ftp.result"


def _proc_root(host_root: str) -> Path:
    root = host_root.rstrip("/") or "/"
    if root == "/":
        return Path("/proc")
    return Path(root) / "proc"


def ftp_running(host_root: str, process: str = DEFAULT_SERVICE) -> bool:
    proc = _proc_root(host_root)
    try:
        entries = list(proc.iterdir())
    except OSError as exc:
        logger.warning("ftp status read failed: %s", exc)
        return False
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            comm = (entry / "comm").read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if comm == process:
            return True
    return False


def ftp_menu_text(host_root: str, process: str = DEFAULT_SERVICE) -> str:
    state = "включён" if ftp_running(host_root, process) else "выключен"
    return f"FTP — {process}\nСейчас: {state}"


def parse_kv(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            out[key] = value.strip()
    return out


def request_ftp(flag_path: str, action: str, service: str = DEFAULT_SERVICE) -> str:
    if action not in {"on", "off"}:
        raise ValueError(f"unsupported ftp action: {action}")
    req = str(time.time_ns())
    path = Path(flag_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"action={action}\nservice={service}\nreq={req}\n", encoding="utf-8")
    return req


def read_ftp_result(result_path: str) -> dict[str, str]:
    path = Path(result_path)
    try:
        return parse_kv(path.read_text(encoding="utf-8"))
    except OSError:
        return {}


async def wait_ftp_result(
    result_path: str,
    req: str,
    timeout: float = 8.0,
    interval: float = 0.25,
) -> dict[str, str]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = read_ftp_result(result_path)
        if data.get("req") == req:
            return data
        await asyncio.sleep(interval)
    return {}


def format_ftp_result(action: str, data: dict[str, str], running: bool) -> str:
    wanted_on = action == "on"
    if not data:
        return (
            "Запрос на FTP ушёл хостовому скрипту, но подтверждения нет.\n"
            "Проверь, что homenasbot-watch запущен."
        )
    if data.get("active") == "1":
        is_on = True
    elif data.get("active") == "0":
        is_on = False
    else:
        is_on = running
    if data.get("ok") == "1" and is_on == wanted_on:
        return "FTP включён." if wanted_on else "FTP выключен."
    detail = data.get("detail") or ""
    if detail:
        return f"Не удалось переключить FTP.\n{detail}"
    return "Не удалось переключить FTP."


def ftp_toggle_ok(action: str, data: dict[str, str], running: bool) -> bool:
    wanted_on = action == "on"
    if data.get("active") == "1":
        is_on = True
    elif data.get("active") == "0":
        is_on = False
    else:
        is_on = running
    return bool(data) and data.get("ok") == "1" and is_on == wanted_on


def ftp_info_messages(
    *,
    user: str,
    password: str,
    internal: str,
    external: str,
    send_login_data: bool,
    send_server_info: bool,
    send_in_split_messages: bool,
) -> list[str]:
    login_parts: list[tuple[str, str]] = []
    if send_login_data:
        if user:
            login_parts.append(("логин", user))
        if password:
            login_parts.append(("пароль", password))
    server_parts: list[tuple[str, str]] = []
    if send_server_info:
        if internal:
            server_parts.append(("внутри", internal))
        if external:
            server_parts.append(("снаружи", external))
    parts = login_parts + server_parts
    if not parts:
        return []
    if send_in_split_messages:
        return [value for _label, value in parts]
    return ["\n".join(f"{label}: {value}" for label, value in parts)]


async def apply_ftp(
    *,
    action: str,
    flag_path: str,
    result_path: str,
    host_root: str,
    service: str = DEFAULT_SERVICE,
) -> tuple[str, bool]:
    try:
        req = request_ftp(flag_path, action, service)
    except OSError as exc:
        logger.warning("ftp flag failed: %s", exc)
        return "Не удалось записать запрос на FTP.", False
    data = await wait_ftp_result(result_path, req)
    running = ftp_running(host_root, service)
    return format_ftp_result(action, data, running), ftp_toggle_ok(action, data, running)

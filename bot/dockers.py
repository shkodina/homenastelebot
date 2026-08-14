from __future__ import annotations

import json
import logging
import re
import socket
from http.client import HTTPConnection
from pathlib import Path

logger = logging.getLogger(__name__)

_AGE_MAP = (
    ("weeks", "нед."),
    ("week", "нед."),
    ("days", "дн."),
    ("day", "дн."),
    ("hours", "ч."),
    ("hour", "ч."),
    ("minutes", "мин."),
    ("minute", "мин."),
    ("seconds", "сек."),
    ("second", "сек."),
)

_STATE_RU = {
    "running": "работает",
    "restarting": "перезапуск",
    "paused": "пауза",
    "created": "создан",
    "exited": "остановлен",
    "dead": "мертв",
}


class UnixHTTPConnection(HTTPConnection):
    def __init__(self, socket_path: str, timeout: float = 8) -> None:
        super().__init__("localhost", timeout=timeout)
        self.socket_path = socket_path

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self.socket_path)
        self.sock = sock


def skip_container(name: str, skip: list[str]) -> bool:
    return any(token and token in name for token in skip)


def _container_name(row: dict) -> str:
    names = row.get("Names") or []
    if names:
        return str(names[0]).lstrip("/")
    return str(row.get("Id") or "?")[:12]


def _age_ru(status: str) -> str:
    text = re.sub(r"\s*\(.*?\)\s*", " ", status).strip()
    text = re.sub(r"^Up\s+", "", text, flags=re.I).strip()
    lower = text.lower()
    for en, ru in _AGE_MAP:
        lower = re.sub(rf"\b{en}\b", ru, lower)
    return re.sub(r"\s+", " ", lower).strip()


def format_container_lines(rows: list[dict]) -> str:
    if not rows:
        return "Нет запущенных контейнеров."
    lines: list[str] = []
    for row in rows:
        name = _container_name(row)
        state = _STATE_RU.get(str(row.get("State") or ""), str(row.get("State") or ""))
        age = _age_ru(str(row.get("Status") or ""))
        if age:
            lines.append(f"{name}\n{state} · {age}")
        else:
            lines.append(f"{name}\n{state}")
    return "\n\n".join(lines)


def fetch_running_containers(socket_path: str) -> list[dict]:
    conn = UnixHTTPConnection(socket_path)
    try:
        conn.request("GET", "/containers/json")
        resp = conn.getresponse()
        body = resp.read()
        if resp.status != 200:
            raise RuntimeError(f"docker api {resp.status}: {body[:200]!r}")
        data = json.loads(body.decode("utf-8"))
        if not isinstance(data, list):
            raise RuntimeError("docker api returned non-list")
        return data
    finally:
        conn.close()


def nas_docker_ps_text(socket_path: str) -> str:
    try:
        rows = fetch_running_containers(socket_path)
    except OSError as exc:
        logger.warning("docker ps failed: %s", exc)
        return "Не удалось обратиться к Docker. Проверь docker.sock."
    except (RuntimeError, json.JSONDecodeError) as exc:
        logger.warning("docker ps failed: %s", exc)
        return "Docker не вернул список контейнеров."
    return format_container_lines(rows)


def request_restart(flag_path: str, skip: tuple[str, ...] | list[str] = ()) -> str:
    path = Path(flag_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        skip_line = ",".join(item for item in skip if item)
        path.write_text(f"restart\nskip={skip_line}\n", encoding="utf-8")
    except OSError as exc:
        logger.warning("restart flag failed: %s", exc)
        return "Не удалось записать запрос на перезапуск."
    return (
        "Запросил перезапуск контейнеров.\n"
        "Хостовый скрипт подхватит файл и перезапустит Docker, кроме самого бота."
    )

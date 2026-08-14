from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def read_uptime_seconds(path: str) -> float:
    raw = Path(path).read_text(encoding="utf-8").strip().split()
    return float(raw[0])


def format_uptime(seconds: float) -> str:
    total = int(seconds)
    if total < 60:
        return "меньше минуты"
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days} дн.")
    if hours or days:
        parts.append(f"{hours} ч.")
    parts.append(f"{minutes} мин.")
    return " ".join(parts)


def nas_uptime_text(path: str) -> str:
    try:
        seconds = read_uptime_seconds(path)
    except OSError as exc:
        logger.warning("uptime read failed: %s", exc)
        return "Не удалось прочитать время работы сервера."
    return f"NAS работает: {format_uptime(seconds)}"

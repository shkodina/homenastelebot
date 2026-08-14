from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path

from bot.disks import human_bytes

logger = logging.getLogger(__name__)

SAMPLE_SEC = 0.4


def _proc_root(host_root: str) -> Path:
    root = host_root.rstrip("/") or "/"
    if root == "/":
        return Path("/proc")
    return Path(root) / "proc"


def parse_loadavg(text: str) -> tuple[float, float, float]:
    parts = text.split()
    return float(parts[0]), float(parts[1]), float(parts[2])


def parse_meminfo(text: str) -> tuple[int, int]:
    values: dict[str, int] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        num = raw.strip().split()[0]
        try:
            values[key] = int(num) * 1024
        except ValueError:
            continue
    total = values.get("MemTotal", 0)
    avail = values.get("MemAvailable")
    if avail is None:
        avail = values.get("MemFree", 0) + values.get("Buffers", 0) + values.get("Cached", 0)
    return total, avail


def parse_stat_cpu(text: str) -> tuple[int, int, int]:
    for line in text.splitlines():
        if line.startswith("cpu "):
            parts = [int(x) for x in line.split()[1:9]]
            user = parts[0] + parts[1]
            idle = parts[3] + parts[4]
            total = sum(parts)
            return user, idle, total
    raise ValueError("no cpu line")


def parse_stat_proc(text: str) -> tuple[str, int]:
    left = text.find("(")
    right = text.rfind(")")
    comm = text[left + 1 : right]
    rest = text[right + 1 :].split()
    utime = int(rest[11])
    stime = int(rest[12])
    return comm, utime + stime


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _sample_processes(proc: Path) -> dict[int, tuple[str, int]]:
    out: dict[int, tuple[str, int]] = {}
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            comm, ticks = parse_stat_proc(_read(entry / "stat"))
        except (OSError, ValueError, IndexError):
            continue
        out[int(entry.name)] = (comm, ticks)
    return out


def _cpu_pct(idle0: int, total0: int, idle1: int, total1: int) -> float:
    d_total = total1 - total0
    if d_total <= 0:
        return 0.0
    d_idle = idle1 - idle0
    return max(0.0, min(100.0, 100.0 * (1.0 - d_idle / d_total)))


def _proc_cpu_pct(ticks0: int, ticks1: int, elapsed: float, clk: float) -> float:
    if elapsed <= 0 or clk <= 0:
        return 0.0
    return max(0.0, 100.0 * (ticks1 - ticks0) / (clk * elapsed))


def format_sys_top(
    *,
    cpu_pct: float,
    mem_used: int,
    mem_total: int,
    mem_avail: int,
    la: tuple[float, float, float],
    top_procs: list[tuple[str, float]],
) -> str:
    mem_pct = 0
    if mem_total:
        mem_pct = round(100 * mem_used / mem_total)
    la1, la5, la15 = la
    lines = [
        f"CPU  {cpu_pct:.0f}%",
        f"RAM  {human_bytes(mem_used)} из {human_bytes(mem_total)} ({mem_pct}%)",
        f"своб. {human_bytes(mem_avail)}",
        "",
        "LA     1м    5м   15м",
        f"     {la1:5.2f} {la5:5.2f} {la15:5.2f}",
        "",
        "топ CPU",
    ]
    if not top_procs:
        lines.append("нет данных")
    else:
        for name, pct in top_procs:
            short = name if len(name) <= 18 else name[:17] + "…"
            lines.append(f"{short:<18} {pct:.0f}%")
    return "\n".join(lines)


async def sys_top_text(host_root: str) -> str:
    proc = _proc_root(host_root)
    try:
        la = parse_loadavg(_read(proc / "loadavg"))
        mem_total, mem_avail = parse_meminfo(_read(proc / "meminfo"))
        _, idle0, total0 = parse_stat_cpu(_read(proc / "stat"))
        procs0 = _sample_processes(proc)
        t0 = time.monotonic()
        await asyncio.sleep(SAMPLE_SEC)
        _, idle1, total1 = parse_stat_cpu(_read(proc / "stat"))
        procs1 = _sample_processes(proc)
        elapsed = max(time.monotonic() - t0, 0.001)
    except OSError as exc:
        logger.warning("sys top read failed: %s", exc)
        return "Не удалось прочитать загрузку системы."

    try:
        clk = float(os.sysconf("SC_CLK_TCK") or 100)
    except (ValueError, OSError):
        clk = 100.0

    ranked: list[tuple[str, float]] = []
    for pid, (name, ticks1) in procs1.items():
        prev = procs0.get(pid)
        if prev is None:
            continue
        pct = _proc_cpu_pct(prev[1], ticks1, elapsed, clk)
        if pct < 0.5:
            continue
        ranked.append((name, pct))
    ranked.sort(key=lambda row: row[1], reverse=True)

    mem_used = max(mem_total - mem_avail, 0)
    return format_sys_top(
        cpu_pct=_cpu_pct(idle0, total0, idle1, total1),
        mem_used=mem_used,
        mem_total=mem_total,
        mem_avail=mem_avail,
        la=la,
        top_procs=ranked[:5],
    )

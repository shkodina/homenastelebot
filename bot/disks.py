from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

SKIP_FS = {
    "tmpfs",
    "devtmpfs",
    "overlay",
    "squashfs",
    "proc",
    "sysfs",
    "cgroup",
    "cgroup2",
    "nsfs",
    "autofs",
    "rpc_pipefs",
    "sockfs",
    "bpf",
    "debugfs",
    "tracefs",
    "securityfs",
    "pstore",
    "efivarfs",
    "ramfs",
    "hugetlbfs",
    "mqueue",
    "fusectl",
    "configfs",
    "devpts",
    "fuse.lxcfs",
}

SKIP_PREFIXES = (
    "/boot",
    "/run",
    "/sys",
    "/proc",
    "/dev",
    "/snap",
    "/var/lib/docker",
    "/var/lib/containerd",
)

DEFAULT_MIN_BYTES = 8 * 1024**3


def human_bytes(n: int) -> str:
    value = float(max(n, 0))
    for unit in ("B", "K", "M", "G", "T"):
        if value < 1024 or unit == "T":
            if unit == "B":
                return f"{int(value)}B"
            if value >= 10:
                return f"{value:.0f}{unit}"
            return f"{value:.1f}{unit}"
        value /= 1024
    return f"{value:.1f}T"


def should_skip_mount(mount: str, fstype: str, total_bytes: int, min_bytes: int = DEFAULT_MIN_BYTES) -> bool:
    if fstype in SKIP_FS:
        return True
    if any(mount == prefix or mount.startswith(prefix + "/") for prefix in SKIP_PREFIXES):
        return True
    if total_bytes < min_bytes:
        return True
    return False


def _unescape_mount(raw: str) -> str:
    return raw.replace("\\040", " ").replace("\\011", "\t")


def _host_path(host_root: str, mountpoint: str) -> str:
    root = host_root.rstrip("/") or "/"
    if mountpoint == "/":
        return root
    return f"{root}{mountpoint}"


def _parse_mounts(text: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        rows.append((_unescape_mount(parts[1]), parts[2]))
    return rows


def collect_disks(host_root: str = "/host", min_bytes: int = DEFAULT_MIN_BYTES) -> list[dict]:
    mounts_file = Path(_host_path(host_root, "/proc/1/mounts"))
    try:
        parsed = _parse_mounts(mounts_file.read_text(encoding="utf-8"))
    except OSError as exc:
        logger.warning("mounts read failed: %s", exc)
        return []

    seen: set[str] = set()
    disks: list[dict] = []
    for mount, fstype in parsed:
        if mount in seen:
            continue
        path = _host_path(host_root, mount)
        try:
            st = os.statvfs(path)
        except OSError:
            continue
        total = st.f_frsize * st.f_blocks
        free = st.f_frsize * st.f_bfree
        avail = st.f_frsize * st.f_bavail
        used = total - free
        if should_skip_mount(mount, fstype, total, min_bytes=min_bytes):
            continue
        seen.add(mount)
        percent = 0
        if used + avail > 0:
            percent = round(100 * used / (used + avail))
        disks.append(
            {
                "mount": mount,
                "used": used,
                "total": total,
                "avail": avail,
                "percent": percent,
            }
        )
    disks.sort(key=lambda row: row["mount"])
    return disks


def format_disk_report(disks: list[dict]) -> str:
    if not disks:
        return "Основные диски не найдены."
    blocks: list[str] = []
    for disk in disks:
        blocks.append(
            f"{disk['mount']}\n"
            f"занято {human_bytes(disk['used'])} из {human_bytes(disk['total'])} ({disk['percent']}%)\n"
            f"свободно {human_bytes(disk['avail'])}"
        )
    return "\n\n".join(blocks)


def nas_df_text(host_root: str, min_bytes: int = DEFAULT_MIN_BYTES) -> str:
    return format_disk_report(collect_disks(host_root=host_root, min_bytes=min_bytes))

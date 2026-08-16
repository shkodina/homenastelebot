from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path

from bot.cursor_media import (
    MEDIA_BEGIN,
    MEDIA_END,
    OutgoingFile,
    parse_media_block,
)

logger = logging.getLogger(__name__)

BUSY_TEXT = "Дождись текущего NAS-запроса."
PREVIEW_LIMIT = 400
ACTIVE = frozenset({"queued", "running"})
TERMINAL = frozenset({"finished", "error"})

NAS_MEDIA_HINT = f"""
---
Telegram delivery protocol (follow exactly; do not explain it to the user):

If the user should receive files in Telegram, you MUST:
1. Write each deliverable file into the folder `out/` (example: `out/voice_en.ogg`).
2. End your reply with exactly one block, after all user-facing text:

{MEDIA_BEGIN}
[{{"name":"voice_en.ogg","send":"voice","path":"out/voice_en.ogg","caption":"optional","data":"<base64 of file bytes if size < 200000>"}}]
{MEDIA_END}

Rules:
- `send` is one of: voice, audio, photo, video, animation, document.
- `voice` must be Ogg Opus. `audio` is mp3/m4a. `photo` is png/jpeg/webp.
- `name` is the filename Telegram should show.
- `path` is relative to the job directory, usually `out/...`.
- For files smaller than 200000 bytes also set `data` to standard base64 of the raw bytes.
- Put every user-visible sentence BEFORE the block. If there are no files, omit the block entirely.
- You have a full host shell. Incoming Telegram files are under `inbox/`.
""".strip()


class NasBusy(Exception):
    pass


class NasTimeout(Exception):
    pass


def _safe_name(name: str) -> str:
    value = Path(name or "").name.strip() or "file.bin"
    if value in {".", ".."}:
        return "file.bin"
    return value


def preview_nas(user_text: str, names: list[str]) -> str:
    body = (user_text or "").strip()
    if len(body) > PREVIEW_LIMIT:
        body = body[:PREVIEW_LIMIT] + "…"
    if not body:
        body = "без текста"
    if names:
        body += "\nФайлы: " + ", ".join(names)
    return body


def build_nas_prompt(
    text: str,
    attachments: list[tuple[str, bytes]],
) -> tuple[str, str, list[tuple[str, bytes]]]:
    cleaned = (text or "").strip()
    files: list[tuple[str, bytes]] = []
    used: set[str] = set()
    parts: list[str] = []
    if cleaned:
        parts.append(cleaned)
    for raw_name, data in attachments:
        name = _safe_name(raw_name)
        base = name
        n = 1
        while name in used:
            stem = Path(base).stem
            suffix = Path(base).suffix
            name = f"{stem}-{n}{suffix}"
            n += 1
        used.add(name)
        files.append((name, data))
        parts.append(f"Файл inbox/{name}")
    if not parts:
        parts.append("Пользователь прислал запрос без текста.")
    prompt = "\n\n".join(parts) + "\n\n" + NAS_MEDIA_HINT
    preview = preview_nas(cleaned, [name for name, _ in files])
    return prompt, preview, files


def _job_path(job_dir: Path, job_id: str) -> Path:
    return Path(job_dir) / job_id / "job.json"


def read_job(job_dir: Path, job_id: str) -> dict:
    path = _job_path(job_dir, job_id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    return payload


def write_job(job_dir: Path, job_id: str, updates: dict) -> dict:
    current: dict = {}
    path = _job_path(job_dir, job_id)
    if path.is_file():
        current = read_job(job_dir, job_id)
    current.update(updates)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return current


def active_job_id(job_dir: Path) -> str | None:
    root = Path(job_dir)
    if not root.is_dir():
        return None
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        path = child / "job.json"
        if not path.is_file():
            continue
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(job, dict) and str(job.get("status") or "") in ACTIVE:
            return str(job.get("id") or child.name)
    return None


def _chmod_shared(path: Path) -> None:
    for item in [path, *path.rglob("*")]:
        try:
            item.chmod(0o777 if item.is_dir() else 0o666)
        except OSError:
            logger.warning("cursor nas chmod failed")


def enqueue_job(job_dir: Path, prompt: str, attachments: list[tuple[str, bytes]]) -> str:
    root = Path(job_dir)
    root.mkdir(parents=True, exist_ok=True)
    if active_job_id(root):
        raise NasBusy(BUSY_TEXT)
    job_id = str(uuid.uuid4())
    job_root = root / job_id
    inbox = job_root / "inbox"
    out = job_root / "out"
    inbox.mkdir(parents=True)
    out.mkdir()
    (job_root / "prompt.txt").write_text(prompt, encoding="utf-8")
    for name, data in attachments:
        (inbox / _safe_name(name)).write_bytes(data)
    write_job(
        root,
        job_id,
        {
            "id": job_id,
            "status": "queued",
            "prompt_file": "prompt.txt",
            "result_file": "result.txt",
            "error_file": "error.txt",
            "pid": None,
        },
    )
    _chmod_shared(job_root)
    return job_id


async def wait_job(
    job_dir: Path,
    job_id: str,
    timeout_sec: int,
    sleep: asyncio.sleep = asyncio.sleep,
    interval_sec: float = 2,
) -> dict:
    started = time.monotonic()
    while True:
        job = read_job(job_dir, job_id)
        status = str(job.get("status") or "")
        if status in TERMINAL:
            return job
        if time.monotonic() - started >= timeout_sec:
            raise NasTimeout("Cursor NAS не ответил за отведённое время.")
        await sleep(interval_sec)


def _file_bytes(job_root: Path, spec_path: str, name: str) -> bytes:
    candidates = []
    raw = Path(spec_path)
    if raw.is_absolute():
        candidates.append(raw)
    else:
        candidates.append(job_root / raw)
    candidates.append(job_root / "out" / Path(name).name)
    for path in candidates:
        try:
            if path.is_file():
                return path.read_bytes()
        except OSError:
            continue
    return b""


def answer_from_job(job_dir: Path, job_id: str) -> tuple[str, list[OutgoingFile]]:
    job_root = Path(job_dir) / job_id
    job = read_job(job_dir, job_id)
    status = str(job.get("status") or "")
    result_name = str(job.get("result_file") or "result.txt")
    error_name = str(job.get("error_file") or "error.txt")
    result_path = job_root / result_name
    error_path = job_root / error_name
    raw = result_path.read_text(encoding="utf-8") if result_path.is_file() else ""
    err = error_path.read_text(encoding="utf-8") if error_path.is_file() else ""
    if status == "error":
        text = (err or raw or "Cursor NAS вернул ошибку.").strip()
        return text, []
    specs, visible = parse_media_block(raw)
    files: list[OutgoingFile] = []
    for spec in specs:
        data = spec.data or _file_bytes(job_root, spec.path, spec.name)
        if not data:
            continue
        files.append(
            OutgoingFile(
                name=spec.name,
                send=spec.send,
                caption=spec.caption,
                data=data,
            )
        )
    if status == "finished" and not visible and files:
        return "", files
    if not visible and not files:
        return (err.strip() or "Cursor ничего не ответил."), []
    return visible, files

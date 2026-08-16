from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable
from urllib.parse import quote

logger = logging.getLogger(__name__)

MEDIA_BEGIN = "===TELEGRAM_FILES==="
MEDIA_END = "===END_TELEGRAM_FILES==="
ARTIFACT_PREFIX = "artifacts/"
MAX_TELEGRAM_FILE = 45 * 1024 * 1024
CAPTION_LIMIT = 1024

SEND_BY_SUFFIX = {
    ".ogg": "voice",
    ".opus": "voice",
    ".mp3": "audio",
    ".m4a": "audio",
    ".wav": "audio",
    ".png": "photo",
    ".jpg": "photo",
    ".jpeg": "photo",
    ".webp": "photo",
    ".mp4": "video",
    ".mov": "video",
    ".gif": "animation",
}
ALLOWED_SEND = frozenset({"voice", "audio", "photo", "video", "animation", "document"})

MEDIA_HINT = f"""
---
Telegram delivery protocol (follow exactly; do not explain it to the user):

If the user should receive files in Telegram, you MUST:
1. Write each deliverable file into the workspace folder `{ARTIFACT_PREFIX}` (example: `{ARTIFACT_PREFIX}voice_en.ogg`). Cloud Agent API only exports this folder.
2. End your reply with exactly one block, after all user-facing text:

{MEDIA_BEGIN}
[{{"name":"voice_en.ogg","send":"voice","path":"{ARTIFACT_PREFIX}voice_en.ogg","caption":"optional","data":"<base64 of file bytes if size < 200000>"}}]
{MEDIA_END}

Rules:
- `send` is one of: voice, audio, photo, video, animation, document.
- `voice` must be Ogg Opus. `audio` is mp3/m4a. `photo` is png/jpeg/webp.
- `name` is the filename Telegram should show.
- `path` must start with `{ARTIFACT_PREFIX}`.
- For files smaller than 200000 bytes also set `data` to standard base64 of the raw bytes (fallback if artifacts API is empty).
- Put every user-visible sentence BEFORE the block. If there are no files, omit the block entirely.
""".strip()

BLOCK_RE = re.compile(
    rf"{re.escape(MEDIA_BEGIN)}\s*(.*?)\s*{re.escape(MEDIA_END)}",
    re.DOTALL,
)

RequestFn = Callable[[str, str, dict | None], Awaitable[dict]]
DownloadFn = Callable[[str], Awaitable[bytes]]


@dataclass(frozen=True)
class MediaSpec:
    name: str
    send: str
    path: str
    caption: str
    data: bytes


@dataclass(frozen=True)
class OutgoingFile:
    name: str
    send: str
    caption: str
    data: bytes


def append_media_hint(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    return f"{cleaned}\n\n{MEDIA_HINT}"


def strip_media_block(text: str) -> str:
    visible, _ = _split_block(text or "")
    return visible


def parse_media_block(text: str) -> tuple[list[MediaSpec], str]:
    visible, raw_json = _split_block(text or "")
    if raw_json is None:
        return [], visible
    payload = _parse_json_payload(raw_json)
    specs = [_spec_from_item(item) for item in payload]
    return [item for item in specs if item is not None], visible


def _split_block(text: str) -> tuple[str, str | None]:
    match = BLOCK_RE.search(text)
    if not match:
        return text.strip(), None
    visible = (text[: match.start()] + text[match.end() :]).strip()
    return visible, match.group(1).strip()


def _parse_json_payload(raw: str) -> list[dict]:
    body = raw.strip()
    if body.startswith("```"):
        body = re.sub(r"^```(?:json)?\s*", "", body)
        body = re.sub(r"\s*```$", "", body)
        body = body.strip()
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        logger.warning("cursor media block is not JSON")
        return []
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _guess_send(name: str, send: str) -> str:
    kind = (send or "").strip().lower()
    if kind in ALLOWED_SEND:
        return kind
    lower = (name or "").strip().lower()
    for suffix, guessed in SEND_BY_SUFFIX.items():
        if lower.endswith(suffix):
            return guessed
    return "document"


def _normalize_path(path: str, name: str) -> str:
    value = (path or "").strip().lstrip("/")
    if not value and name:
        value = name.strip().lstrip("/")
    if not value:
        return ""
    if value.startswith(ARTIFACT_PREFIX):
        return value
    return ARTIFACT_PREFIX + value


def _decode_data(raw: object) -> bytes:
    if not raw:
        return b""
    text = str(raw).strip()
    if not text:
        return b""
    try:
        return base64.b64decode(text, validate=False)
    except Exception:
        logger.warning("cursor media base64 decode failed")
        return b""


def _spec_from_item(item: dict) -> MediaSpec | None:
    name = str(item.get("name") or item.get("filename") or "").strip()
    path = _normalize_path(str(item.get("path") or ""), name)
    if not name:
        name = path.rsplit("/", 1)[-1] if path else ""
    data = _decode_data(item.get("data"))
    if not name and not path and not data:
        return None
    if not name:
        name = "file.bin"
    caption = str(item.get("caption") or "").strip()[:CAPTION_LIMIT]
    return MediaSpec(
        name=name,
        send=_guess_send(name, str(item.get("send") or "")),
        path=path,
        caption=caption,
        data=data,
    )


async def fetch_artifact_bytes(
    agent_id: str,
    path: str,
    request: RequestFn,
    download: DownloadFn,
) -> bytes:
    listed = await request("GET", f"/v1/agents/{agent_id}/artifacts", None)
    items = listed.get("items") if isinstance(listed, dict) else None
    if not isinstance(items, list):
        items = []
    known = {str(item.get("path") or "") for item in items if isinstance(item, dict)}
    if known and path not in known:
        logger.warning("cursor artifact path not in list, trying download anyway")
    encoded = quote(path, safe="/")
    payload = await request(
        "GET",
        f"/v1/agents/{agent_id}/artifacts/download?path={encoded}",
        None,
    )
    url = str((payload or {}).get("url") or "").strip()
    if not url:
        return b""
    data = await download(url)
    return data or b""


async def resolve_outgoing_files(
    specs: list[MediaSpec],
    agent_id: str | None,
    request: RequestFn | None,
    download: DownloadFn | None,
) -> list[OutgoingFile]:
    files: list[OutgoingFile] = []
    for spec in specs:
        data = spec.data
        if not data and agent_id and spec.path and request is not None and download is not None:
            try:
                data = await fetch_artifact_bytes(agent_id, spec.path, request, download)
            except Exception:
                logger.exception("cursor artifact download failed")
                data = b""
        if not data:
            logger.warning("cursor media file missing bytes")
            continue
        if len(data) > MAX_TELEGRAM_FILE:
            logger.warning("cursor media file too large")
            continue
        files.append(
            OutgoingFile(
                name=spec.name,
                send=spec.send,
                caption=spec.caption,
                data=data,
            )
        )
    return files


async def send_outgoing_files(
    message: Any,
    files: list[OutgoingFile],
    file_cls: Any = None,
) -> None:
    if file_cls is None:
        from aiogram.types import BufferedInputFile as file_cls

    for item in files:
        buf = file_cls(item.data, filename=item.name)
        caption = item.caption or None
        method_name = {
            "voice": "answer_voice",
            "audio": "answer_audio",
            "photo": "answer_photo",
            "video": "answer_video",
            "animation": "answer_animation",
            "document": "answer_document",
        }.get(item.send, "answer_document")
        method = getattr(message, method_name)
        try:
            await method(buf, caption=caption)
        except Exception:
            logger.exception("telegram send %s failed, fallback document", item.send)
            await message.answer_document(buf, caption=caption)

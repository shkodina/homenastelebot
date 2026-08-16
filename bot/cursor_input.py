from __future__ import annotations

import base64
from dataclasses import dataclass

from bot.cursor_media import append_media_hint

IMAGE_MIMES = {
    "image/png": "image/png",
    "image/jpeg": "image/jpeg",
    "image/jpg": "image/jpeg",
    "image/gif": "image/gif",
    "image/webp": "image/webp",
}
TEXT_MIMES = {
    "text/plain",
    "text/csv",
    "text/markdown",
    "text/html",
    "text/xml",
    "application/json",
    "application/xml",
    "application/javascript",
    "application/x-python",
    "application/sql",
}
IMAGE_MAX_BYTES = 15 * 1024 * 1024
FILE_INLINE_MAX_BYTES = 4 * 1024 * 1024
MAX_IMAGES = 5
PLACEHOLDER_TEXT = "Пользователь прислал вложение."


@dataclass(frozen=True)
class CursorAttachment:
    name: str
    mime: str
    data: bytes


def telegram_file_specs(message: object) -> list[tuple[str, str, str]]:
    specs: list[tuple[str, str, str]] = []
    photo = getattr(message, "photo", None) or []
    if photo:
        specs.append((photo[-1].file_id, "photo.jpg", "image/jpeg"))
    document = getattr(message, "document", None)
    if document is not None:
        specs.append(
            (
                document.file_id,
                str(getattr(document, "file_name", None) or "document.bin"),
                str(getattr(document, "mime_type", None) or "application/octet-stream"),
            )
        )
    audio = getattr(message, "audio", None)
    if audio is not None:
        specs.append(
            (
                audio.file_id,
                str(getattr(audio, "file_name", None) or "audio.mp3"),
                str(getattr(audio, "mime_type", None) or "audio/mpeg"),
            )
        )
    voice = getattr(message, "voice", None)
    if voice is not None:
        specs.append(
            (
                voice.file_id,
                "voice.ogg",
                str(getattr(voice, "mime_type", None) or "audio/ogg"),
            )
        )
    video = getattr(message, "video", None)
    if video is not None:
        specs.append(
            (
                video.file_id,
                str(getattr(video, "file_name", None) or "video.mp4"),
                str(getattr(video, "mime_type", None) or "video/mp4"),
            )
        )
    video_note = getattr(message, "video_note", None)
    if video_note is not None:
        specs.append((video_note.file_id, "video_note.mp4", "video/mp4"))
    animation = getattr(message, "animation", None)
    if animation is not None:
        specs.append(
            (
                animation.file_id,
                str(getattr(animation, "file_name", None) or "animation.gif"),
                str(getattr(animation, "mime_type", None) or "image/gif"),
            )
        )
    sticker = getattr(message, "sticker", None)
    if sticker is not None:
        is_anim = bool(getattr(sticker, "is_animated", False) or getattr(sticker, "is_video", False))
        mime = "application/x-tgsticker" if is_anim else "image/webp"
        name = "sticker.tgs" if is_anim else "sticker.webp"
        specs.append((sticker.file_id, name, mime))
    return specs


def message_text(message: object) -> str:
    text = getattr(message, "text", None) or getattr(message, "caption", None) or ""
    return str(text).strip()


def _image_mime(mime: str) -> str | None:
    return IMAGE_MIMES.get((mime or "").strip().lower())


def _looks_like_text(mime: str, data: bytes) -> bool:
    if (mime or "").strip().lower() in TEXT_MIMES:
        return True
    if (mime or "").startswith("text/"):
        return True
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return not any(byte == 0 for byte in data[:1024]) and len(data) <= FILE_INLINE_MAX_BYTES


def build_cursor_prompt(text: str, attachments: list[CursorAttachment]) -> dict:
    parts: list[str] = []
    cleaned = (text or "").strip()
    if cleaned:
        parts.append(cleaned)
    images: list[dict] = []
    for item in attachments:
        mime = (item.mime or "application/octet-stream").strip().lower()
        image_mime = _image_mime(mime)
        if image_mime and len(images) < MAX_IMAGES and len(item.data) <= IMAGE_MAX_BYTES:
            images.append(
                {
                    "data": base64.b64encode(item.data).decode("ascii"),
                    "mimeType": image_mime,
                }
            )
            continue
        if image_mime and len(item.data) > IMAGE_MAX_BYTES:
            parts.append(f"Файл {item.name} слишком большой для картинки ({len(item.data)} байт).")
            continue
        if _looks_like_text(mime, item.data) and len(item.data) <= FILE_INLINE_MAX_BYTES:
            body = item.data.decode("utf-8", errors="replace")
            parts.append(f"Файл {item.name} ({mime}):\n{body}")
            continue
        if len(item.data) > FILE_INLINE_MAX_BYTES:
            parts.append(
                f"Файл {item.name} ({mime}, {len(item.data)} байт) слишком большой, содержимое не вложено."
            )
            continue
        encoded = base64.b64encode(item.data).decode("ascii")
        parts.append(
            f"Файл {item.name} ({mime}, {len(item.data)} байт), base64:\n{encoded}"
        )
    prompt_text = "\n\n".join(parts).strip()
    if images and not prompt_text:
        prompt_text = PLACEHOLDER_TEXT
    prompt_text = append_media_hint(prompt_text)
    payload: dict = {"text": prompt_text}
    if images:
        payload["images"] = images
    return payload


async def download_attachments(bot: object, specs: list[tuple[str, str, str]]) -> list[CursorAttachment]:
    from io import BytesIO

    out: list[CursorAttachment] = []
    for file_id, name, mime in specs:
        info = await bot.get_file(file_id)
        path = getattr(info, "file_path", None)
        if not path:
            continue
        buf = BytesIO()
        downloaded = await bot.download_file(path, destination=buf)
        data = downloaded.getvalue() if downloaded is not None else buf.getvalue()
        if not data:
            continue
        out.append(CursorAttachment(name=name, mime=mime, data=data))
    return out

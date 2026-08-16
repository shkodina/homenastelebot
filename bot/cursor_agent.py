from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from bot.cursor_media import (
    DownloadFn,
    OutgoingFile,
    parse_media_block,
    resolve_outgoing_files,
)

logger = logging.getLogger(__name__)

API_BASE = "https://api.cursor.com"
CREATE_PATH = "/v1/agents"
REQUEST_TIMEOUT_SEC = 20
CREATE_WAIT_SEC = 8
POLL_INTERVAL_SEC = 2
POLL_ATTEMPTS = 600
POLL_LOG_EVERY = 15
TELEGRAM_LIMIT = 4096
TERMINAL = {"FINISHED", "ERROR", "CANCELLED", "EXPIRED"}

SETUP_TEXT = (
    "Cursor API key не задан.\n"
    "\n"
    "Создай User API Key:\n"
    "1. Открой https://cursor.com/dashboard/api?section=user-keys\n"
    "2. User API Keys → New API Key (или Add)\n"
    "3. Скопируй ключ сразу — он показывается один раз\n"
    "4. Добавь в xtmp-cnf.yaml:\n"
    "\n"
    "cursor:\n"
    '  api_key: "crsr_..."\n'
)

EMPTY_PROMPT = "Нужен текст или вложение. Нажми Use ещё раз."
NO_ANSWER = "Cursor ничего не ответил."
FETCH_ERROR = "Не удалось отправить запрос в Cursor."


class CursorAgentError(Exception):
    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


RequestFn = Callable[[str, str, dict | None], Awaitable[dict]]
SleepFn = Callable[[float], Awaitable[Any]]


@dataclass
class CursorAnswer:
    text: str
    files: list[OutgoingFile] = field(default_factory=list)


def parse_create_response(payload: dict) -> tuple[str, str]:
    agent = payload.get("agent") or {}
    run = payload.get("run") or {}
    agent_id = str(agent.get("id") or "").strip()
    run_id = str(run.get("id") or "").strip()
    if not agent_id or not run_id:
        raise CursorAgentError("Cursor не вернул id агента.")
    return agent_id, run_id


def format_run_result(run: dict) -> str:
    status = str(run.get("status") or "").upper()
    result = str(run.get("result") or "").strip()
    if status == "FINISHED":
        return result or NO_ANSWER
    if status == "ERROR":
        if result:
            return f"Cursor вернул ошибку.\n{result}"
        return "Cursor вернул ошибку."
    if status == "CANCELLED":
        return "Запрос в Cursor отменён."
    if status == "EXPIRED":
        return "Запрос в Cursor истек."
    return FETCH_ERROR


async def _answer_from_run(
    run: dict,
    agent_id: str | None,
    request: RequestFn | None,
    download: DownloadFn | None,
) -> CursorAnswer:
    raw = str(run.get("result") or "")
    specs, visible = parse_media_block(raw)
    files = await resolve_outgoing_files(specs, agent_id, request, download)
    status = str(run.get("status") or "").upper()
    if status == "FINISHED" and not visible and files:
        text = ""
    else:
        text = format_run_result({**run, "result": visible})
    if specs and not files:
        note = "Cursor указал файлы, но скачать их не удалось."
        text = f"{text}\n{note}".strip() if text else note
    return CursorAnswer(text=text, files=files)


def parse_agent_lookup(payload: dict, fallback_id: str) -> tuple[str, str]:
    agent_id = str(payload.get("id") or fallback_id).strip()
    run_id = str(payload.get("latestRunId") or "").strip()
    if not agent_id or not run_id:
        raise CursorAgentError("Cursor принял запрос, но run не появился.")
    return agent_id, run_id


def split_telegram_text(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    if not text:
        return [NO_ANSWER]
    chunks: list[str] = []
    rest = text
    while rest:
        chunks.append(rest[:limit])
        rest = rest[limit:]
    return chunks


async def _client_session(proxy: str | None, timeout_sec: int = REQUEST_TIMEOUT_SEC) -> Any:
    import aiohttp

    timeout = aiohttp.ClientTimeout(total=timeout_sec)
    if proxy:
        from aiohttp_socks import ProxyConnector

        connector = ProxyConnector.from_url(proxy)
        return aiohttp.ClientSession(connector=connector, timeout=timeout)
    return aiohttp.ClientSession(timeout=timeout)


async def _download_url(url: str, proxy: str | None, timeout_sec: int = REQUEST_TIMEOUT_SEC) -> bytes:
    session = await _client_session(proxy, timeout_sec)
    try:
        async with session.get(url) as response:
            if response.status >= 400:
                raise CursorAgentError("Cursor artifact download failed.")
            return await response.read()
    finally:
        await session.close()


async def _http_request(
    api_key: str,
    method: str,
    path: str,
    json: dict | None = None,
    proxy: str | None = None,
    timeout_sec: int = REQUEST_TIMEOUT_SEC,
) -> dict:
    import aiohttp

    session = await _client_session(proxy, timeout_sec)
    try:
        url = f"{API_BASE}{path}"
        auth = aiohttp.BasicAuth(api_key, "")
        async with session.request(method, url, json=json, auth=auth) as response:
            try:
                payload = await response.json(content_type=None)
            except Exception as exc:
                raise CursorAgentError("Cursor вернул не JSON.") from exc
            if not isinstance(payload, dict):
                payload = {}
            if response.status >= 400:
                detail = str(payload.get("message") or payload.get("error") or response.status)
                if response.status in {401, 403}:
                    raise CursorAgentError("Cursor отклонил API key.")
                raise CursorAgentError(f"Cursor API: {detail}")
            return payload
    finally:
        await session.close()


def _prompt_payload(prompt: str | dict) -> dict | None:
    if isinstance(prompt, dict):
        text = str(prompt.get("text") or "").strip()
        images = prompt.get("images") or []
        if not isinstance(images, list):
            images = []
        if not text and not images:
            return None
        if not text:
            text = "Пользователь прислал вложение."
        payload: dict = {"text": text}
        if images:
            payload["images"] = images
        return payload
    text = (prompt or "").strip()
    if not text:
        return None
    return {"text": text}


async def cursor_prompt(
    api_key: str,
    prompt: str | dict,
    proxy: str | None = None,
    request: RequestFn | None = None,
    sleep: SleepFn | None = None,
    download: DownloadFn | None = None,
) -> CursorAnswer:
    key = (api_key or "").strip()
    if not key:
        return CursorAnswer(text=SETUP_TEXT)
    payload = _prompt_payload(prompt)
    if payload is None:
        return CursorAnswer(text=EMPTY_PROMPT)

    waiter = sleep or asyncio.sleep
    agent_id = "bc-" + str(uuid.uuid4())

    if request is not None:
        try:
            try:
                created = await request(
                    "POST",
                    CREATE_PATH,
                    {"prompt": payload, "agentId": agent_id},
                )
                agent_id, run_id = parse_create_response(created)
            except (TimeoutError, asyncio.TimeoutError):
                logger.warning("cursor create timed out, lookup agent")
                looked: dict = {}
                run_id = ""
                for _ in range(8):
                    looked = await request("GET", f"{CREATE_PATH}/{agent_id}", None)
                    try:
                        agent_id, run_id = parse_agent_lookup(looked, agent_id)
                        break
                    except CursorAgentError:
                        await waiter(POLL_INTERVAL_SEC)
                if not run_id:
                    agent_id, run_id = parse_agent_lookup(looked, agent_id)
                logger.info("cursor agent found after timeout, polling run")
            run_path = f"{CREATE_PATH}/{agent_id}/runs/{run_id}"
            for attempt in range(POLL_ATTEMPTS):
                run = await request("GET", run_path, None)
                status = str((run or {}).get("status") or "").upper()
                if status in TERMINAL:
                    return await _answer_from_run(run, agent_id, request, download)
                if attempt and attempt % POLL_LOG_EVERY == 0:
                    logger.info(
                        "cursor still %s attempt %s/%s",
                        status or "UNKNOWN",
                        attempt,
                        POLL_ATTEMPTS,
                    )
                await waiter(POLL_INTERVAL_SEC)
            logger.warning("cursor poll budget exhausted")
            return CursorAnswer(text="Cursor не ответил за отведённое время.")
        except CursorAgentError as exc:
            logger.warning("cursor prompt failed: %s", exc.user_message)
            return CursorAnswer(text=f"{FETCH_ERROR}\n{exc.user_message}")
        except Exception:
            logger.exception("cursor prompt unexpected error")
            return CursorAnswer(text=FETCH_ERROR)

    import aiohttp

    try:
        async def http_request(method: str, path: str, json: dict | None = None) -> dict:
            wait = CREATE_WAIT_SEC if method == "POST" else REQUEST_TIMEOUT_SEC
            return await _http_request(key, method, path, json, proxy, wait)

        async def http_download(url: str) -> bytes:
            return await _download_url(url, proxy)

        return await cursor_prompt(
            key,
            payload,
            proxy,
            request=http_request,
            sleep=waiter,
            download=http_download,
        )
    except aiohttp.ClientError:
        logger.warning("cursor prompt network failed")
        return CursorAnswer(text="Не удалось подключиться к Cursor API.")


async def cursor_prompt_text(
    api_key: str,
    prompt: str | dict,
    proxy: str | None = None,
    request: RequestFn | None = None,
    sleep: SleepFn | None = None,
    download: DownloadFn | None = None,
) -> str:
    answer = await cursor_prompt(
        api_key,
        prompt,
        proxy,
        request=request,
        sleep=sleep,
        download=download,
    )
    return answer.text

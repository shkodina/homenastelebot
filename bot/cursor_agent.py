from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

API_BASE = "https://api.cursor.com"
CREATE_PATH = "/v1/agents"
REQUEST_TIMEOUT_SEC = 20
POLL_INTERVAL_SEC = 2
POLL_ATTEMPTS = 150
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

EMPTY_PROMPT = "Нужен текстовый запрос. Нажми Use ещё раз."
NO_ANSWER = "Cursor ничего не ответил."
FETCH_ERROR = "Не удалось отправить запрос в Cursor."


class CursorAgentError(Exception):
    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


RequestFn = Callable[[str, str, dict | None], Awaitable[dict]]
SleepFn = Callable[[float], Awaitable[Any]]


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


async def _client_session(proxy: str | None) -> Any:
    import aiohttp

    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SEC)
    if proxy:
        from aiohttp_socks import ProxyConnector

        connector = ProxyConnector.from_url(proxy)
        return aiohttp.ClientSession(connector=connector, timeout=timeout)
    return aiohttp.ClientSession(timeout=timeout)


async def _http_request(
    session: Any,
    api_key: str,
    method: str,
    path: str,
    json: dict | None = None,
) -> dict:
    import aiohttp

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


async def cursor_prompt_text(
    api_key: str,
    prompt: str,
    proxy: str | None = None,
    request: RequestFn | None = None,
    sleep: SleepFn | None = None,
) -> str:
    key = (api_key or "").strip()
    if not key:
        return SETUP_TEXT
    text = (prompt or "").strip()
    if not text:
        return EMPTY_PROMPT

    waiter = sleep or asyncio.sleep
    agent_id = "bc-" + str(uuid.uuid4())

    if request is not None:
        try:
            try:
                created = await request(
                    "POST",
                    CREATE_PATH,
                    {"prompt": {"text": text}, "agentId": agent_id},
                )
                agent_id, run_id = parse_create_response(created)
            except (TimeoutError, asyncio.TimeoutError):
                logger.warning("cursor create timed out, lookup agent")
                looked = await request("GET", f"{CREATE_PATH}/{agent_id}", None)
                agent_id, run_id = parse_agent_lookup(looked, agent_id)
            run_path = f"{CREATE_PATH}/{agent_id}/runs/{run_id}"
            for _ in range(POLL_ATTEMPTS):
                run = await request("GET", run_path, None)
                status = str((run or {}).get("status") or "").upper()
                if status in TERMINAL:
                    return format_run_result(run)
                await waiter(POLL_INTERVAL_SEC)
            return "Cursor не ответил за отведённое время."
        except CursorAgentError as exc:
            logger.warning("cursor prompt failed: %s", exc.user_message)
            return f"{FETCH_ERROR}\n{exc.user_message}"
        except Exception:
            logger.exception("cursor prompt unexpected error")
            return FETCH_ERROR

    import aiohttp

    session = await _client_session(proxy)
    try:
        async def http_request(method: str, path: str, json: dict | None = None) -> dict:
            return await _http_request(session, key, method, path, json)

        return await cursor_prompt_text(key, text, proxy, request=http_request, sleep=waiter)
    except aiohttp.ClientError:
        logger.warning("cursor prompt network failed")
        return "Не удалось подключиться к Cursor API."
    finally:
        await session.close()

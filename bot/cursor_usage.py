from __future__ import annotations

import asyncio
import base64
import json
import logging
import math
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

API_BASE = "https://api2.cursor.sh"
EXCHANGE_PATH = "/auth/exchange_user_api_key"
USAGE_PATH = "/aiserver.v1.DashboardService/GetCurrentPeriodUsage"
REQUEST_TIMEOUT_SEC = 20
TOKEN_REFRESH_SKEW_SEC = 300

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
    "\n"
    "Ключ вида crsr_... — это User API Key из дашборда, не Cloud Agents SDK."
)


class CursorUsageError(Exception):
    def __init__(self, user_message: str, http_status: int | None = None) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.http_status = http_status


class _TokenCache:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._api_key = ""
        self._access_token = ""
        self._expires_at = 0.0

    async def get(self, api_key: str, session: Any) -> str:
        now = time.time()
        async with self._lock:
            if (
                self._api_key == api_key
                and self._access_token
                and now + TOKEN_REFRESH_SKEW_SEC < self._expires_at
            ):
                return self._access_token
            token, expires_at = await _exchange_api_key(session, api_key)
            self._api_key = api_key
            self._access_token = token
            self._expires_at = expires_at
            return token

    def invalidate(self) -> None:
        self._access_token = ""
        self._expires_at = 0.0


_TOKEN_CACHE = _TokenCache()


def _b64url_decode(raw: str) -> bytes:
    padded = raw + "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def jwt_exp(token: str) -> float | None:
    try:
        payload = json.loads(_b64url_decode(token.split(".")[1]))
        return float(payload["exp"])
    except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def parse_cycle_ms(value: object) -> int | None:
    if value is None or value is False:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        n = int(value)
    else:
        text = str(value).strip()
        if not text:
            return None
        if text.isdigit():
            n = int(text)
        else:
            try:
                dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
    if n <= 0:
        return None
    if n < 10_000_000_000:
        n *= 1000
    return n


def days_until(end_ms: int, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    end = datetime.fromtimestamp(end_ms / 1000, tz=timezone.utc)
    seconds = (end - now).total_seconds()
    if seconds <= 0:
        return 0
    return math.ceil(seconds / 86400)


def format_percent(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "н/д"
    if not math.isfinite(number):
        return "н/д"
    number = max(0.0, number)
    text = f"{number:.1f}"
    if text.endswith(".0"):
        return f"{int(float(text))}%"
    return f"{text}%"


def _nested_get(data: dict[str, Any], *keys: str) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def format_cursor_usage(payload: dict[str, Any], now: datetime | None = None) -> str:
    plan = payload.get("planUsage")
    if not isinstance(plan, dict):
        individual = _nested_get(payload, "individualUsage", "plan")
        plan = individual if isinstance(individual, dict) else {}

    auto_pct = plan.get("autoPercentUsed")
    api_pct = plan.get("apiPercentUsed")
    specialized_pct = plan.get("specializedPercentUsed", api_pct)
    total_pct = plan.get("totalPercentUsed")

    end_ms = parse_cycle_ms(payload.get("billingCycleEnd"))
    if end_ms is None:
        refresh = "н/д"
    else:
        left = days_until(end_ms, now)
        refresh = "сегодня" if left == 0 else f"{left} дн."

    lines = [
        "Cursor",
        f"До рефреша: {refresh}",
        "",
        f"Дефолтные: {format_percent(auto_pct)}",
        f"Специализированные: {format_percent(specialized_pct)}",
        f"API: {format_percent(api_pct)}",
    ]
    if total_pct is not None:
        lines.append(f"Всего: {format_percent(total_pct)}")
    return "\n".join(lines)


def _error_message(status: int, body: str) -> str:
    snippet = body.strip().replace("\n", " ")
    if len(snippet) > 180:
        snippet = snippet[:177] + "..."
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        message = data.get("message") or data.get("error")
        if isinstance(message, dict):
            message = message.get("message") or message.get("code")
        if message:
            return str(message)
    if status == 401:
        return "Ключ Cursor отклонён (401). Проверь api_key в конфиге."
    if status == 403:
        return "Нет доступа к usage API Cursor (403)."
    if snippet:
        return f"Cursor API HTTP {status}: {snippet}"
    return f"Cursor API HTTP {status}"


async def _read_json(response: Any) -> dict[str, Any]:
    body = await response.text()
    if response.status >= 400:
        raise CursorUsageError(_error_message(response.status, body), response.status)
    try:
        data = json.loads(body) if body else {}
    except json.JSONDecodeError as exc:
        raise CursorUsageError("Cursor API вернул не JSON.") from exc
    if not isinstance(data, dict):
        raise CursorUsageError("Неожиданный ответ Cursor API.")
    if data.get("code") == "error":
        raise CursorUsageError(str(data.get("message") or "Cursor API error"))
    error = data.get("error")
    if isinstance(error, dict) and error.get("message"):
        raise CursorUsageError(str(error["message"]))
    return data


async def _exchange_api_key(session: Any, api_key: str) -> tuple[str, float]:
    async with session.post(
        f"{API_BASE}{EXCHANGE_PATH}",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={},
    ) as response:
        data = await _read_json(response)
    token = str(data.get("accessToken") or "").strip()
    if not token:
        raise CursorUsageError("Cursor не вернул accessToken. Проверь User API Key.")
    expires = jwt_exp(token) or (time.time() + 3300)
    return token, expires


async def _get_period_usage(session: Any, access_token: str) -> dict[str, Any]:
    async with session.post(
        f"{API_BASE}{USAGE_PATH}",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Connect-Protocol-Version": "1",
        },
        json={},
    ) as response:
        return await _read_json(response)


async def _client_session(proxy: str | None) -> Any:
    import aiohttp

    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SEC)
    if proxy:
        from aiohttp_socks import ProxyConnector

        connector = ProxyConnector.from_url(proxy)
        return aiohttp.ClientSession(connector=connector, timeout=timeout)
    return aiohttp.ClientSession(timeout=timeout)


async def fetch_cursor_usage(api_key: str, proxy: str | None = None) -> dict[str, Any]:
    session = await _client_session(proxy)
    try:
        token = await _TOKEN_CACHE.get(api_key, session)
        try:
            return await _get_period_usage(session, token)
        except CursorUsageError as exc:
            if exc.http_status != 401:
                raise
            _TOKEN_CACHE.invalidate()
            token = await _TOKEN_CACHE.get(api_key, session)
            return await _get_period_usage(session, token)
    finally:
        await session.close()


async def cursor_usage_text(api_key: str, proxy: str | None = None) -> str:
    key = (api_key or "").strip()
    if not key:
        return SETUP_TEXT

    import aiohttp

    try:
        payload = await fetch_cursor_usage(key, proxy)
        return format_cursor_usage(payload)
    except CursorUsageError as exc:
        logger.warning("cursor usage failed: %s", exc.user_message)
        return f"Не удалось получить статус Cursor.\n{exc.user_message}"
    except aiohttp.ClientError as exc:
        logger.warning("cursor usage network failed: %s", exc)
        return "Не удалось подключиться к Cursor API."
    except Exception:
        logger.exception("cursor usage unexpected error")
        return "Не удалось получить статус Cursor."

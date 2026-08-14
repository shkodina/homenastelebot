from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

from bot.auth import is_allowed

logger = logging.getLogger(__name__)


class AllowlistMiddleware(BaseMiddleware):
    def __init__(self, allowed_ids: frozenset[int]) -> None:
        self.allowed_ids = allowed_ids

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        if user is None or not is_allowed(user.id, self.allowed_ids):
            logger.info("ignore user_id=%s", None if user is None else user.id)
            return None
        return await handler(event, data)

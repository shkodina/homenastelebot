from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update, User

from bot.auth import is_allowed

logger = logging.getLogger(__name__)


def user_from_event(event: TelegramObject, data: Dict[str, Any]) -> User | None:
    user = data.get("event_from_user")
    if isinstance(user, User):
        return user
    if isinstance(event, (Message, CallbackQuery)):
        return event.from_user
    if isinstance(event, Update):
        if event.message is not None:
            return event.message.from_user
        if event.callback_query is not None:
            return event.callback_query.from_user
        if event.edited_message is not None:
            return event.edited_message.from_user
    return None


class AllowlistMiddleware(BaseMiddleware):
    def __init__(self, allowed_ids: frozenset[int]) -> None:
        self.allowed_ids = allowed_ids

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = user_from_event(event, data)
        if user is None or not is_allowed(user.id, self.allowed_ids):
            logger.info("ignore user_id=%s event=%s", None if user is None else user.id, type(event).__name__)
            return None
        return await handler(event, data)

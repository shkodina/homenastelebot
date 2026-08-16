from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession

from bot.config import ConfigError, load_config, proxy_log_target, proxy_url
from bot.handlers import router
from bot.middleware import AllowlistMiddleware, CursorWaitCancelMiddleware

logger = logging.getLogger(__name__)


async def run() -> None:
    config_path = os.environ.get("CONFIG_PATH", "xtmp-cnf.yaml")
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        logger.error("%s", exc)
        raise SystemExit(1) from exc

    session = None
    url = proxy_url(config)
    if url:
        session = AiohttpSession(proxy=url)
        logger.info("telegram proxy %s", proxy_log_target(config))

    bot = Bot(token=config.token, session=session)
    dp = Dispatcher()
    dp["config"] = config
    allowlist = AllowlistMiddleware(config.allowed_ids)
    router.message.middleware(allowlist)
    router.callback_query.middleware(allowlist)
    router.callback_query.middleware(CursorWaitCancelMiddleware())
    dp.include_router(router)
    logger.info("polling started")
    await dp.start_polling(bot)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run())


if __name__ == "__main__":
    main()

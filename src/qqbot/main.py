from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from .config import get_settings
from .core.router import Bot
from .llm.client import ChatClient
from .logging import setup_logging
from .memory.store import Store
from .onebot.api import OneBotAPI
from .onebot.ws import create_ws_router
from .persona.loader import load_persona

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if settings.owner_qq <= 0:
        raise SystemExit("OWNER_QQ 未配置：请把 .env 里的 OWNER_QQ 改成你自己的 QQ 号")
    if not settings.deepseek_api_key:
        raise SystemExit("DEEPSEEK_API_KEY 未配置")

    store = Store(settings.data_dir / "qqbot.db")
    await store.init()
    chat = ChatClient()
    api = OneBotAPI()
    bot = Bot(api, chat, store, load_persona(settings.persona_file))
    app.state.bot = bot

    log.info("服务已启动，等待 NapCat 连接 %s", settings.onebot_ws_path)
    try:
        yield
    finally:
        await api.close()
        await chat.close()
        await store.close()


def create_app() -> FastAPI:
    async def handle(event: dict) -> None:
        bot = getattr(app.state, "bot", None)
        if bot is not None:
            await bot.handle_event(event)

    app = FastAPI(lifespan=lifespan)
    app.include_router(create_ws_router(handle))
    return app


def main() -> None:
    settings = get_settings()
    setup_logging(settings.data_dir)
    uvicorn.run(create_app(), host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from .app import AppContext, build_context, shutdown
from .config import Settings, get_settings
from .logging import setup_logging
from .onebot.ws import create_ws_router

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        ctx = await build_context(settings)
        app.state.ctx = ctx
        log.info("服务已启动，等待 NapCat 连接 %s", settings.onebot_ws_path)
        try:
            yield
        finally:
            await shutdown(ctx)

    async def handle(event: dict) -> None:
        ctx: AppContext = app.state.ctx
        await ctx.bus.dispatch(event)

    app = FastAPI(lifespan=lifespan)
    app.include_router(create_ws_router(handle))
    return app


def main() -> None:
    settings = get_settings()
    setup_logging(settings.data_dir)
    uvicorn.run(create_app(), host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()

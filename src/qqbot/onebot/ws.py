from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..config import get_settings

log = logging.getLogger(__name__)

EventHandler = Callable[[dict], Awaitable[None]]


def create_ws_router(handler: EventHandler) -> APIRouter:
    settings = get_settings()
    router = APIRouter()

    @router.websocket(settings.onebot_ws_path)
    async def onebot_ws(ws: WebSocket) -> None:
        await ws.accept()
        log.info("NapCat 已通过反向 WS 连接")
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    log.warning("收到非 JSON 数据，已忽略")
                    continue
                # 不要让处理阻塞事件接收
                asyncio.create_task(handler(event))
        except WebSocketDisconnect:
            log.warning("NapCat 反向 WS 断开")
        except Exception:
            log.exception("反向 WS 异常")

    return router

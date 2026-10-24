from __future__ import annotations

import logging

import httpx

from ..config import get_settings

log = logging.getLogger(__name__)


class OneBotAPI:
    """NapCat 的 HTTP API 封装，所有动作集中在这一层。"""

    def __init__(self) -> None:
        settings = get_settings()
        self.base = settings.onebot_http_url.rstrip("/")
        self.token = settings.onebot_token
        self._client = httpx.AsyncClient(timeout=20.0)

    def _headers(self) -> dict[str, str]:
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    async def call(self, action: str, **params):
        url = f"{self.base}/{action}"
        resp = await self._client.post(url, json=params, headers=self._headers())
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("status") == "failed" or payload.get("retcode", 0) not in (0, None):
            raise RuntimeError(f"OneBot {action} 失败: {payload}")
        return payload.get("data")

    async def send_private_msg(self, user_id: int, message: str):
        return await self.call("send_private_msg", user_id=user_id, message=message)

    async def get_login_info(self):
        return await self.call("get_login_info")

    async def set_self_longnick(self, longnick: str):
        return await self.call("set_self_longnick", longnick=longnick)

    async def send_qzone_msg(self, content: str, images: list[str] | None = None):
        params: dict = {"content": content, "ugc_right": 1}
        if images:
            params["images"] = images
        return await self.call("send_qzone_msg", **params)

    async def close(self) -> None:
        await self._client.aclose()
        log.info("OneBot HTTP 客户端已关闭")

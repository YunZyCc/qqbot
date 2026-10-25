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

    async def send_group_msg(self, group_id: int, message: str):
        return await self.call("send_group_msg", group_id=group_id, message=message)

    async def get_login_info(self):
        return await self.call("get_login_info")

    async def send_qzone_msg(
        self,
        content: str,
        images: list[str] | None = None,
        ugc_right: int = 1,
        target_uins: list[int] | None = None,
    ):
        params: dict = {"content": content, "ugc_right": ugc_right}
        if images:
            params["images"] = images
        if target_uins:
            params["target_uins"] = target_uins
        return await self.call("send_qzone_msg", **params)

    async def set_self_longnick(self, longnick: str):
        """改个性签名。NapCat 的返回结构不是标准 OneBot，要单独判 result。"""
        data = await self.call("set_self_longnick", longNick=longnick)
        if isinstance(data, dict):
            result = data.get("result")
            if result not in (0, None):
                raise RuntimeError(f"改签名失败：{data.get('errMsg') or result}")
        return data

    async def close(self) -> None:
        await self._client.aclose()
        log.info("OneBot HTTP 客户端已关闭")

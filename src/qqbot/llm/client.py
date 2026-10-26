from __future__ import annotations

import datetime as dt
import logging
from typing import TYPE_CHECKING

import httpx

from ..config import get_settings

if TYPE_CHECKING:
    from ..memory.store import Store

log = logging.getLogger(__name__)

FALLBACK = "……我刚刚走神了，你再说一遍？"


class ChatClient:
    """OpenAI 兼容的聊天客户端，带每日 token 预算。"""

    def __init__(self, store: Store | None = None) -> None:
        settings = get_settings()
        self.base = settings.deepseek_base_url.rstrip("/")
        self.key = settings.deepseek_api_key
        self.model = settings.deepseek_model
        self.timeout = settings.request_timeout
        self.budget = settings.daily_token_budget
        self.used_tokens = 0
        # 有 store 就按自然日持久化计数；没有就退回进程内计数（测试用）
        self.store = store
        self._client = httpx.AsyncClient(timeout=self.timeout)

    def _today_key(self) -> str:
        return f"token_usage:{dt.date.today().isoformat()}"

    async def _over_budget(self) -> bool:
        """budget <= 0 表示不限，只记账不拦截。"""
        if self.budget <= 0:
            return False
        if self.store is None:
            return self.used_tokens >= self.budget
        used = await self.store.counter(self._today_key())
        return used >= self.budget

    async def _add_usage(self, usage: int) -> None:
        self.used_tokens += usage
        if self.store is not None and usage > 0:
            await self.store.incr_counter(self._today_key(), usage)

    async def complete(
        self,
        messages: list[dict],
        max_tokens: int = 600,
        temperature: float = 0.85,
    ) -> tuple[str, int]:
        if not self.key:
            raise RuntimeError("DEEPSEEK_API_KEY 未配置")
        if await self._over_budget():
            return "（今天的话痨额度用完了，明天再聊吧。）", 0

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        headers = {"Authorization": f"Bearer {self.key}"}
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                resp = await self._client.post(
                    f"{self.base}/chat/completions", json=payload, headers=headers
                )
                resp.raise_for_status()
                data = resp.json()
                content = (data["choices"][0]["message"]["content"] or "").strip()
                usage = int(data.get("usage", {}).get("total_tokens", 0))
                await self._add_usage(usage)
                log.info("LLM 调用完成，tokens=%s 今日累计=%s", usage, self.used_tokens)
                return content, usage
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                log.warning("LLM 第 %s 次调用失败: %s", attempt + 1, exc)
        log.error("LLM 调用最终失败: %s", last_error)
        return FALLBACK, 0

    async def complete_with_tools(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 600,
        temperature: float = 0.85,
    ) -> tuple[str, int, list[dict]]:
        """带工具的调用，返回 (文本, tokens, tool_calls)。"""
        if not self.key:
            raise RuntimeError("DEEPSEEK_API_KEY 未配置")
        if await self._over_budget():
            return "（今天的话痨额度用完了，明天再聊吧。）", 0, []

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
        headers = {"Authorization": f"Bearer {self.key}"}
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                resp = await self._client.post(
                    f"{self.base}/chat/completions", json=payload, headers=headers
                )
                resp.raise_for_status()
                data = resp.json()
                message = data["choices"][0]["message"]
                content = (message.get("content") or "").strip()
                usage = int(data.get("usage", {}).get("total_tokens", 0))
                await self._add_usage(usage)
                return content, usage, message.get("tool_calls") or []
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                log.warning("LLM(tool) 第 %s 次调用失败: %s", attempt + 1, exc)
        log.error("LLM(tool) 调用最终失败: %s", last_error)
        return FALLBACK, 0, []

    async def close(self) -> None:
        await self._client.aclose()

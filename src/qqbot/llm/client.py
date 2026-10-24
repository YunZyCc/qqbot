from __future__ import annotations

import logging

import httpx

from ..config import get_settings

log = logging.getLogger(__name__)

FALLBACK = "……我刚刚走神了，你再说一遍？"


class ChatClient:
    """OpenAI 兼容的聊天客户端，带每日 token 预算。"""

    def __init__(self) -> None:
        settings = get_settings()
        self.base = settings.deepseek_base_url.rstrip("/")
        self.key = settings.deepseek_api_key
        self.model = settings.deepseek_model
        self.timeout = settings.request_timeout
        self.budget = settings.daily_token_budget
        self.used_tokens = 0
        self._client = httpx.AsyncClient(timeout=self.timeout)

    async def complete(
        self,
        messages: list[dict],
        max_tokens: int = 600,
        temperature: float = 0.85,
    ) -> tuple[str, int]:
        if not self.key:
            raise RuntimeError("DEEPSEEK_API_KEY 未配置")
        if self.used_tokens >= self.budget:
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
                self.used_tokens += usage
                log.info("LLM 调用完成，tokens=%s 累计=%s", usage, self.used_tokens)
                return content, usage
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                log.warning("LLM 第 %s 次调用失败: %s", attempt + 1, exc)
        log.error("LLM 调用最终失败: %s", last_error)
        return FALLBACK, 0

    async def close(self) -> None:
        await self._client.aclose()

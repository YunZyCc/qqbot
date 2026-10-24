from __future__ import annotations

import base64
import logging
from typing import Protocol

import httpx

log = logging.getLogger(__name__)

DEFAULT_QUESTION = (
    "用一两句话描述这张图。如果是表情包，说明它表达的情绪和内容；"
    "如果有文字，念出来。不要评价，不要编造。"
)


class VisionProvider(Protocol):
    model: str

    async def describe(self, image: bytes, mime: str, question: str = "") -> str: ...

    async def close(self) -> None: ...


class NullVision:
    model = "none"

    async def describe(self, image: bytes, mime: str, question: str = "") -> str:
        return ""

    async def close(self) -> None:
        return None


class OpenAICompatibleVision:
    """Ollama / 硅基流动 的 OpenAI 兼容图片输入。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 120.0,
    ) -> None:
        self.base = base_url.rstrip("/")
        self.key = api_key
        self.model = model
        self._client = httpx.AsyncClient(timeout=timeout)

    async def describe(self, image: bytes, mime: str, question: str = "") -> str:
        encoded = base64.b64encode(image).decode()
        prompt = (question or "").strip() or DEFAULT_QUESTION
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{encoded}"},
                        },
                    ],
                }
            ],
            "max_tokens": 300,
            "temperature": 0.3,
        }
        headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
        resp = await self._client.post(
            f"{self.base}/chat/completions", json=payload, headers=headers
        )
        resp.raise_for_status()
        data = resp.json()
        return (data["choices"][0]["message"]["content"] or "").strip()

    async def close(self) -> None:
        await self._client.aclose()

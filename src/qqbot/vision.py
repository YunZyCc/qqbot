from __future__ import annotations

import base64
import io
import logging
from typing import Protocol

import httpx

log = logging.getLogger(__name__)

DEFAULT_QUESTION = (
    "用一两句话描述这张图。如果是表情包，说明它表达的情绪和内容；"
    "如果有文字，念出来。不要评价，不要编造。"
)

# Ollama 对动图支持不好，GIF/WebP 统一取第一帧转 JPEG 再送
_STATIC_MIMES = {"image/jpeg", "image/png"}


def _flatten_image(image: bytes, mime: str) -> tuple[bytes, str]:
    if mime in _STATIC_MIMES:
        return image, mime
    try:
        from PIL import Image

        with Image.open(io.BytesIO(image)) as opened:
            opened.seek(0)
            frame = opened.convert("RGB")
            buffer = io.BytesIO()
            frame.save(buffer, format="JPEG", quality=85)
            return buffer.getvalue(), "image/jpeg"
    except Exception:
        log.warning("动图转静帧失败，按原格式发送", exc_info=True)
        return image, mime


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
        self._client = httpx.AsyncClient(timeout=timeout, trust_env=False)

    async def describe(self, image: bytes, mime: str, question: str = "") -> str:
        image, mime = _flatten_image(image, mime)
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
        if resp.status_code >= 400:
            # 之前只 raise 不带响应体，排查时看不到原因
            log.warning(
                "视觉模型返回 %s：%s（mime=%s, %s bytes）",
                resp.status_code,
                resp.text[:300],
                mime,
                len(image),
            )
        resp.raise_for_status()
        data = resp.json()
        return (data["choices"][0]["message"]["content"] or "").strip()

    async def close(self) -> None:
        await self._client.aclose()

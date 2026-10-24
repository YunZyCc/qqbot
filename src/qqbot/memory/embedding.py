from __future__ import annotations

import logging
from typing import Protocol

import httpx

log = logging.getLogger(__name__)


class EmbeddingProvider(Protocol):
    model: str
    dim: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    async def close(self) -> None: ...


class NullEmbedding:
    """未配置或探测失败时使用，所有调用返回空。"""

    model = "none"
    dim = 0

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return []

    async def close(self) -> None:
        return None


class OpenAICompatibleEmbedding:
    """Ollama / 硅基流动 / 阿里百炼 / vLLM 通用的 /v1/embeddings。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        dim: int,
        timeout: float = 30.0,
    ) -> None:
        self.base = base_url.rstrip("/")
        self.key = api_key
        self.model = model
        self.dim = dim
        self._client = httpx.AsyncClient(timeout=timeout, trust_env=False)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
        payload = {"model": self.model, "input": texts}
        resp = await self._client.post(f"{self.base}/embeddings", json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        vectors = [item["embedding"] for item in data["data"]]
        for vec in vectors:
            if len(vec) != self.dim:
                raise ValueError(
                    f"embedding 维度不匹配：配置 {self.dim}，模型返回 {len(vec)}"
                )
        return vectors

    async def close(self) -> None:
        await self._client.aclose()

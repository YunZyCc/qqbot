from __future__ import annotations

from qqbot.memory.embedding import NullEmbedding


async def test_null_embedding_returns_empty():
    provider = NullEmbedding()
    assert provider.dim == 0
    assert await provider.embed(["a", "b"]) == []
    await provider.close()


def test_null_embedding_attributes():
    provider = NullEmbedding()
    assert provider.model == "none"

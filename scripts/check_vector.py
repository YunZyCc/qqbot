"""手动验证向量检索：需要本机 Ollama + bge-m3。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from qqbot.config import get_settings  # noqa: E402
from qqbot.memory.embedding import OpenAICompatibleEmbedding  # noqa: E402
from qqbot.memory.hybrid import HybridRetriever  # noqa: E402
from qqbot.memory.store import Store  # noqa: E402
from qqbot.memory.vector import NumpyVectorIndex  # noqa: E402


async def main() -> None:
    settings = get_settings()
    db_path = settings.data_dir / "check_vector.db"
    db_path.unlink(missing_ok=True)

    store = Store(db_path, default_scope="user:test")
    await store.init()
    embedder = OpenAICompatibleEmbedding(
        settings.embedding_base_url,
        settings.embedding_api_key,
        settings.embedding_model,
        settings.embedding_dim,
    )
    vector = NumpyVectorIndex(store, embedder)

    for predicate, obj in [("喜欢", "猫"), ("讨厌", "香菜"), ("住在", "成都")]:
        fact_id = await store.upsert_fact("user:test", "user", predicate, obj, 0.9)
        await vector.upsert("user:test", "fact", fact_id, f"{predicate}: {obj}")

    retriever = HybridRetriever(store, vector)
    for query in ["养什么宠物好", "吃火锅不放什么", "你住哪儿"]:
        hits = await retriever.recall("user:test", query, 2)
        print(f"{query} -> {[hit['object'] for hit in hits]}")

    await embedder.close()
    await store.close()
    db_path.unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(main())

from __future__ import annotations

from qqbot.memory.hybrid import HybridRetriever
from qqbot.memory.retrieve import retrieve
from qqbot.memory.store import Store


async def _store_with_facts(tmp_path) -> Store:
    store = Store(tmp_path / "h.db", default_scope="private:1")
    await store.init()
    await store.upsert_fact("user:1", "user", "喜欢", "猫", 0.9)
    await store.upsert_fact("user:1", "user", "讨厌", "狗", 0.9)
    return store


async def test_keyword_only_matches_retrieve(tmp_path):
    store = await _store_with_facts(tmp_path)
    retriever = HybridRetriever(store, None)

    facts = await store.active_facts("user:1")
    expected = retrieve("猫", facts, 2)
    actual = await retriever.recall("user:1", "猫", 2)
    assert [f["id"] for f in actual] == [f["id"] for f in expected]
    await store.close()


class StubVector:
    def __init__(self, ids: list[int]) -> None:
        self.ids = ids
        self.embedder = type("E", (), {"dim": 2})()

    async def search(self, scope, ref_type, query, k):
        return [(i, 1.0) for i in self.ids[:k]]


async def test_rrf_merges_keyword_and_vector(tmp_path):
    store = await _store_with_facts(tmp_path)
    facts = await store.active_facts("user:1")
    cat_id = next(f["id"] for f in facts if f["object"] == "猫")
    dog_id = next(f["id"] for f in facts if f["object"] == "狗")

    retriever = HybridRetriever(store, StubVector([dog_id, cat_id]))
    result = await retriever.recall("user:1", "猫", 2)
    # 猫在关键词和向量里都出现，应排第一
    assert result[0]["object"] == "猫"
    await store.close()


async def test_empty_facts_returns_empty(tmp_path):
    store = Store(tmp_path / "e.db", default_scope="private:1")
    await store.init()
    retriever = HybridRetriever(store, None)
    assert await retriever.recall("user:1", "随便", 5) == []
    await store.close()

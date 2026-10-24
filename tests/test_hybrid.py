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


async def test_recall_episodes_prefers_keyword_hit(tmp_path):
    store = Store(tmp_path / "ep.db", default_scope="private:1")
    await store.init()
    await store.add_episode("private:1", 0.0, 10.0, "用户在看 CS 比赛，聊到绿龙和 BB")
    await store.add_episode("private:1", 10.0, 20.0, "用户调试表情包功能")
    retriever = HybridRetriever(store, None)

    eps = await retriever.recall_episodes("private:1", "CS 比赛", 1)
    assert eps and "CS" in eps[0]["text"]
    await store.close()


async def test_recall_episodes_falls_back_to_recent(tmp_path):
    store = Store(tmp_path / "ep2.db", default_scope="private:1")
    await store.init()
    await store.add_episode("private:1", 0.0, 10.0, "聊了比赛")
    await store.add_episode("private:1", 10.0, 20.0, "聊了吃饭")
    retriever = HybridRetriever(store, None)

    # 没有关键词命中时也要给最近几条，否则「在吗」这种就完全失忆
    eps = await retriever.recall_episodes("private:1", "在吗", 1)
    assert [e["text"] for e in eps] == ["聊了吃饭"]
    await store.close()


async def test_recall_all_returns_both(tmp_path):
    store = Store(tmp_path / "all.db", default_scope="private:1")
    await store.init()
    await store.upsert_fact("private:1", "user", "喜欢", "猫", 0.9)
    await store.add_episode("private:1", 0.0, 10.0, "聊了猫的事")
    retriever = HybridRetriever(store, None)

    got = await retriever.recall_all("private:1", "猫", 5, 3)
    assert got["facts"] and got["facts"][0]["object"] == "猫"
    assert got["episodes"] and "猫" in got["episodes"][0]["text"]
    await store.close()

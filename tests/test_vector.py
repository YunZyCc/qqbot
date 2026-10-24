from __future__ import annotations

from qqbot.memory.store import Store
from qqbot.memory.vector import NumpyVectorIndex


class FakeEmbedder:
    model = "fake"
    dim = 2

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            if "猫" in text:
                out.append([1.0, 0.0])
            elif "狗" in text:
                out.append([0.0, 1.0])
            else:
                out.append([0.5, 0.5])
        return out

    async def close(self) -> None:
        return None


async def _store(tmp_path) -> Store:
    store = Store(tmp_path / "v.db", default_scope="private:1")
    await store.init()
    return store


async def test_upsert_and_search(tmp_path):
    store = await _store(tmp_path)
    index = NumpyVectorIndex(store, FakeEmbedder())

    await index.upsert("user:1", "fact", 1, "喜欢猫")
    await index.upsert("user:1", "fact", 2, "喜欢狗")

    hits = await index.search("user:1", "fact", "猫", 2)
    assert hits and hits[0][0] == 1
    await store.close()


async def test_search_scope_isolation(tmp_path):
    store = await _store(tmp_path)
    index = NumpyVectorIndex(store, FakeEmbedder())

    await index.upsert("user:1", "fact", 1, "喜欢猫")
    await index.upsert("user:2", "fact", 2, "喜欢狗")

    hits = await index.search("user:1", "fact", "猫", 5)
    assert [ref_id for ref_id, _ in hits] == [1]
    await store.close()


async def test_rebuild_replaces_vectors(tmp_path):
    store = await _store(tmp_path)
    index = NumpyVectorIndex(store, FakeEmbedder())

    await index.upsert("user:1", "fact", 1, "喜欢猫")
    count = await index.rebuild("user:1", "fact", [(3, "喜欢狗")])
    assert count == 1
    hits = await index.search("user:1", "fact", "狗", 5)
    assert hits[0][0] == 3
    await store.close()

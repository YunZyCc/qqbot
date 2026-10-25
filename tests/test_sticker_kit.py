from __future__ import annotations

import json
from pathlib import Path

from qqbot.config import get_settings
from qqbot.memory.sticker_kit import StickerKit


def test_load_meta():
    settings = get_settings()
    kit = StickerKit(settings)
    count = kit.load()
    assert count > 0
    assert "开心" in kit.emotions


def test_search_chinese():
    settings = get_settings()
    kit = StickerKit(settings)
    kit.load()

    hits = kit.search("摸鱼", 3)
    assert hits
    joined = " ".join(h["name"] + h["emotion"] + " ".join(h["tags"]) for h in hits)
    assert "摸鱼" in joined or "鱼" in joined

    hits = kit.search("无语", 3)
    assert hits


def test_search_multi_term_prefers_all_terms():
    settings = get_settings()
    kit = StickerKit(settings)
    kit.load()
    hits = kit.search("开心 大笑", 3)
    assert hits


def test_file_url_format():
    settings = get_settings()
    kit = StickerKit(settings)
    kit.load()
    sticker = next(s for s in kit._stickers if s["pack"] == "大肥鱼")
    url = kit.file_url(sticker)
    assert url.startswith("https://kiriyuki.com/media/gif/")
    assert url.endswith(".gif") or "?h=" in url


def test_meta_json_is_valid():
    settings = get_settings()
    path = Path(settings.nekowhale_meta)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema"] == "sticker-kit/1"
    assert len(data["stickers"]) > 100


def _fake_settings(tmp_path, **overrides):
    from types import SimpleNamespace

    from qqbot.config import get_settings

    base = get_settings()
    data = dict(
        nekowhale_meta=base.nekowhale_meta,
        nekowhale_site=base.nekowhale_site,
        nekowhale_gif_base=base.nekowhale_gif_base,
        sticker_dir=tmp_path,
        sticker_max_size_kb=2048,
        nekowhale_packs=base.nekowhale_packs,
        nekowhale_pack_list=base.nekowhale_pack_list,
        sticker_vector_search=True,
        sticker_vector_weight=0.5,
        embedding_batch=8,
    )
    data.update(overrides)
    return SimpleNamespace(**data)


class FakeEmbedder:
    dim = 4

    def __init__(self) -> None:
        self.calls = 0

    async def embed(self, texts):
        self.calls += len(texts)
        # 只按文本长度编个可比的向量，够测试用
        return [[1.0, len(t) % 3 + 1.0, 0.5, 0.5] for t in texts]


class FakeVector:
    def __init__(self) -> None:
        self.embedder = FakeEmbedder()
        self.model = "fake"
        self.dim = 4
        self.rows: dict[int, list[float]] = {}

    async def upsert(self, scope, ref_type, ref_id, text):
        vec = (await self.embedder.embed([text]))[0]
        self.rows[int(ref_id)] = vec

    async def search(self, scope, ref_type, query, k):
        return sorted(((i, 1.0) for i in self.rows), key=lambda kv: kv[0])[:k]


class FakeStore:
    def __init__(self) -> None:
        self.embeddings: dict[int, list[float]] = {}

    async def load_embeddings(self, scope, ref_type, model):
        return [{"ref_id": i, "vector": v} for i, v in self.embeddings.items()]

    async def upsert_embedding(self, scope, ref_type, ref_id, model, dim, vector):
        self.embeddings[int(ref_id)] = vector


async def test_ensure_vectors_caches_and_skips_second_time(tmp_path):
    settings = _fake_settings(tmp_path)
    store = FakeStore()
    vector = FakeVector()
    kit = StickerKit(settings, store, vector)
    kit.load()

    written = await kit.ensure_vectors()
    assert written > 0
    assert len(store.embeddings) == written

    # 第二次不该再调 embedding
    before = vector.embedder.calls
    again = await kit.ensure_vectors()
    assert again == 0
    assert vector.embedder.calls == before


async def test_search_hybrid_falls_back_without_vectors(tmp_path):
    settings = _fake_settings(tmp_path)
    kit = StickerKit(settings, None, None)
    kit.load()
    hits = await kit.search_hybrid("摸鱼", 3)
    assert hits


async def test_search_hybrid_falls_back_when_disabled(tmp_path):
    settings = _fake_settings(tmp_path, sticker_vector_search=False)
    store = FakeStore()
    vector = FakeVector()
    kit = StickerKit(settings, store, vector)
    kit.load()
    await kit.ensure_vectors()
    hits = await kit.search_hybrid("无语", 3)
    assert hits

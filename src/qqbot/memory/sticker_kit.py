from __future__ import annotations

import asyncio
import json
import logging
import re
import urllib.parse
from pathlib import Path

import httpx
import numpy as np

from .store import Store
from .vector import NumpyVectorIndex

log = logging.getLogger(__name__)

# 向量存在独立 ref_type 下，避免和本地图片库的 sticker 撞 id
KIT_SCOPE = "sticker:global"
KIT_REF = "sticker_kit"
RRF_K = 60

# 移植自 dsh-nekowhale-stickers/src/core/search.ts 的加权检索
WEIGHTS: tuple[tuple[str, int], ...] = (
    ("name", 6),
    ("tags", 5),
    ("emotion", 4),
    ("text", 4),
    ("meme", 3),
    ("use", 3),
    ("en", 2),
    ("desc", 1),
    ("dir", 2),
)

_CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
_SPLIT = re.compile(r"[\s,，。.!！?？、;；:：/|]+")


class StickerKit:
    """nekowhale 表情包知识库：加载元数据、加权检索、懒下载 GIF。"""

    def __init__(
        self,
        settings,
        store: Store | None = None,
        vector: NumpyVectorIndex | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.vector = vector
        self.meta_path = Path(settings.nekowhale_meta)
        self.site = settings.nekowhale_site.rstrip("/")
        self.gif_base = settings.nekowhale_gif_base
        self.cache_dir = (Path(settings.sticker_dir) / "nekowhale").resolve()
        self.packs = set(settings.nekowhale_pack_list)
        self._stickers: list[dict] = []
        # 向量用整数 ref_id，这里维护 序号 → sticker 的映射
        self._by_num: dict[int, dict] = {}
        self._vectors_ready = False
        self._recent: list[str] = []
        # trust_env=False：直连，避免被系统代理拖住
        self._client = httpx.AsyncClient(
            timeout=30.0, follow_redirects=True, trust_env=False
        )

    def load(self) -> int:
        if not self.meta_path.exists():
            log.warning("找不到表情包元数据：%s", self.meta_path)
            return 0
        try:
            data = json.loads(self.meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            log.exception("表情包元数据读取失败")
            return 0

        items: list[dict] = []
        for raw in data.get("stickers", []):
            if not isinstance(raw, dict):
                continue
            sticker_id = str(raw.get("id") or "")
            pack, _, stem = sticker_id.partition("/")
            if not pack or not stem:
                continue
            if self.packs and pack not in self.packs:
                continue
            name = stem.split("_", 1)[1] if "_" in stem else stem
            items.append(
                {
                    "id": sticker_id,
                    "pack": pack,
                    "stem": stem,
                    "name": name,
                    "file": f"{stem}.gif",
                    "hash": str(raw.get("hash") or ""),
                    "text": str(raw.get("text") or ""),
                    "emotion": str(raw.get("emotion") or ""),
                    "tags": list(raw.get("tags") or []),
                    "use": str(raw.get("use") or ""),
                    "desc": str(raw.get("desc") or ""),
                    "meme": str(raw.get("meme") or ""),
                    "dir": str(raw.get("dir") or ""),
                    "en": str(raw.get("en") or ""),
                }
            )
        self._stickers = items
        # 按 id 排序后分配稳定序号，向量就存在这个序号上；重启后顺序不变才能命中缓存
        self._by_num = {
            index + 1: sticker
            for index, sticker in enumerate(sorted(items, key=lambda s: s["id"]))
        }
        self._id_index = {sticker["id"]: sticker for sticker in items}
        log.info("nekowhale 表情包知识库加载完成：%s 张", len(items))
        return len(items)

    def _embed_text(self, sticker: dict) -> str:
        """拼成一段用于 embedding 的文本；梗注释和用法比名字更有区分度。"""
        parts = [
            sticker["name"],
            " ".join(sticker["tags"]),
            sticker["emotion"],
            sticker["text"],
            sticker["meme"],
            sticker["use"],
            sticker["desc"],
        ]
        return " ".join(part for part in parts if part)[:500]

    async def ensure_vectors(self) -> int:
        """补建缺失的向量；已建过的跳过，所以只有第一次慢。"""
        if self.store is None or self.vector is None:
            return 0
        if not getattr(self.settings, "sticker_vector_search", True):
            return 0
        if self.vector is None or not self.vector.embedder.dim or not self._by_num:
            return 0

        model = self.vector.model
        rows = await self.store.load_embeddings(KIT_SCOPE, KIT_REF, model)
        have = {int(row["ref_id"]) for row in rows}
        missing = [num for num in self._by_num if num not in have]
        if not missing:
            self._vectors_ready = True
            return 0

        batch = max(1, int(getattr(self.settings, "embedding_batch", 16)))
        written = 0
        for start in range(0, len(missing), batch):
            chunk = missing[start : start + batch]
            texts = [self._embed_text(self._by_num[num]) for num in chunk]
            try:
                vectors = await self.vector.embedder.embed(texts)
            except Exception:
                log.warning("表情包向量生成失败，本次跳过", exc_info=True)
                continue
            for num, vector in zip(chunk, vectors, strict=False):
                vec = np.asarray(vector, dtype=np.float32)
                if vec.shape[0] != self.vector.dim:
                    continue
                await self.store.upsert_embedding(
                    KIT_SCOPE, KIT_REF, num, model, self.vector.dim, vec.tobytes()
                )
                written += 1
        self._vectors_ready = True
        if written:
            log.info("表情包向量补建完成：%s 条（共 %s 张）", written, len(self._by_num))
        return written

    @property
    def emotions(self) -> list[str]:
        seen: list[str] = []
        for sticker in self._stickers:
            emotion = sticker["emotion"]
            if emotion and emotion not in seen:
                seen.append(emotion)
        return seen

    def _fields(self, sticker: dict) -> dict[str, str]:
        return {
            "name": sticker["name"],
            "tags": " ".join(sticker["tags"]),
            "emotion": sticker["emotion"],
            "text": sticker["text"],
            "meme": sticker["meme"],
            "use": sticker["use"],
            "en": sticker["en"],
            "desc": sticker["desc"],
            "dir": sticker["dir"],
        }

    def _score(self, fields: dict[str, str], queries: list[str]) -> float:
        total = 0.0
        matched = 0
        for query in queries:
            best = 0.0
            for key, weight in WEIGHTS:
                value = fields.get(key, "")
                if not value:
                    continue
                if query in value:
                    best = max(best, weight * (1.5 if value == query else 1.0))
                elif _CJK.search(query) and len(query) > 2:
                    grams = [query[i : i + 2] for i in range(len(query) - 1)]
                    hit = sum(1 for gram in grams if gram in value)
                    if hit:
                        best = max(best, weight * hit / len(grams) * 0.8)
            total += best
            if best > 0:
                matched += 1
        if len(queries) > 1:
            total *= (matched / len(queries)) ** 2
        return total

    def search(self, query: str, k: int = 3) -> list[dict]:
        """纯关键词检索（保底用）。"""
        queries = [q for q in _SPLIT.split((query or "").lower()) if q]
        if not queries or not self._stickers:
            return []
        scored: list[tuple[float, dict]] = []
        for sticker in self._stickers:
            fields = {key: value.lower() for key, value in self._fields(sticker).items()}
            score = self._score(fields, queries)
            if score > 0:
                scored.append((score, sticker))
        scored.sort(key=lambda item: item[0], reverse=True)

        results: list[dict] = []
        for score, sticker in scored:
            if sticker["id"] in self._recent and len(scored) > k:
                continue
            results.append({**sticker, "score": score})
            if len(results) >= k:
                break
        return results

    async def search_hybrid(self, query: str, k: int = 3) -> list[dict]:
        """向量 + 关键词，RRF 融合。向量不可用时自动退回纯关键词。"""
        keyword_hits = self.search(query, max(k * 4, k))

        weight = float(getattr(self.settings, "sticker_vector_weight", 0.5))
        enabled = getattr(self.settings, "sticker_vector_search", True)
        if (
            not enabled
            or weight <= 0
            or self.vector is None
            or not self._vectors_ready
        ):
            return keyword_hits[:k]

        try:
            hits = await self.vector.search(KIT_SCOPE, KIT_REF, query, max(k * 4, k))
        except Exception:
            log.warning("表情包向量检索失败，回退关键词", exc_info=True)
            return keyword_hits[:k]
        if not hits:
            return keyword_hits[:k]

        scores: dict[str, float] = {}
        for rank, sticker in enumerate(keyword_hits):
            scores[sticker["id"]] = scores.get(sticker["id"], 0.0) + (
                1 - weight
            ) / (RRF_K + rank)
        for rank, (num, _score) in enumerate(hits):
            sticker = self._by_num.get(int(num))
            if sticker is None:
                continue
            scores[sticker["id"]] = scores.get(sticker["id"], 0.0) + weight / (
                RRF_K + rank
            )

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        results: list[dict] = []
        for sticker_id, score in ranked:
            sticker = self._id_index.get(sticker_id)
            if sticker is None:
                continue
            if sticker_id in self._recent and len(ranked) > k:
                continue
            results.append({**sticker, "score": score})
            if len(results) >= k:
                break
        return results

    def mark_used(self, sticker_id: str) -> None:
        self._recent.append(sticker_id)
        self._recent = self._recent[-5:]

    def file_url(self, sticker: dict) -> str:
        pack = urllib.parse.quote(sticker["pack"])
        file = urllib.parse.quote(sticker["file"])
        url = f"{self.site}{self.gif_base}/{pack}/{file}"
        if sticker["hash"]:
            url += f"?h={sticker['hash']}"
        return url

    async def ensure_file(self, sticker: dict) -> Path | None:
        path = self.cache_dir / sticker["pack"] / sticker["file"]
        if path.exists() and path.stat().st_size > 0:
            return path

        url = self.file_url(sticker)
        resp = None
        for attempt in range(2):
            try:
                resp = await self._client.get(url)
                resp.raise_for_status()
                break
            except Exception:
                if attempt == 1:
                    log.warning("表情包下载失败：%s", url)
                    return None
                await asyncio.sleep(1)
        if resp is None:
            return None

        content_type = resp.headers.get("content-type", "")
        if "gif" not in content_type:
            log.warning("下载到的不是 GIF：%s", content_type)
            return None
        data = resp.content
        if not data or len(data) > self.settings.sticker_max_size_kb * 1024:
            log.warning("表情包大小异常：%s bytes", len(data))
            return None

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.mark_used(sticker["id"])
        return path

    async def close(self) -> None:
        await self._client.aclose()

from __future__ import annotations

import logging

from .retrieve import _relevance, retrieve
from .store import Store
from .vector import NumpyVectorIndex

log = logging.getLogger(__name__)

RRF_K = 60


def _rrf_fuse(
    keyword_ids: list[int], vector_ids: list[int], k: int
) -> list[int]:
    scores: dict[int, float] = {}
    for rank, item_id in enumerate(keyword_ids):
        scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (RRF_K + rank)
    for rank, item_id in enumerate(vector_ids):
        scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (RRF_K + rank)
    return [
        item_id
        for item_id, _ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:k]
    ]


class HybridRetriever:
    """关键词 + 向量，RRF 融合；向量不可用时退化为纯关键词。

    facts 是稳定的长期事实，episodes 是发生过的事件记录，两者分开检索和渲染。
    """

    def __init__(self, store: Store, vector: NumpyVectorIndex | None = None) -> None:
        self.store = store
        self.vector = vector

    @property
    def _vector_ready(self) -> bool:
        return self.vector is not None and bool(self.vector.embedder.dim)

    async def recall(self, scope: str, query: str, k: int = 5) -> list[dict]:
        facts = await self.store.active_facts(scope)
        if not facts:
            return []

        keyword = retrieve(query, facts, max(k * 4, k))
        keyword_ids = [int(f["id"]) for f in keyword]
        if not keyword_ids:
            return []

        vector_ids: list[int] = []
        if self._vector_ready:
            try:
                hits = await self.vector.search(scope, "fact", query, max(k * 4, k))
                vector_ids = [ref_id for ref_id, _ in hits]
            except Exception:
                log.warning("事实向量检索失败，使用纯关键词", exc_info=True)

        fused = _rrf_fuse(keyword_ids, vector_ids, k) if vector_ids else keyword_ids[:k]
        fact_map = {int(f["id"]): f for f in facts}
        return [fact_map[fact_id] for fact_id in fused if fact_id in fact_map]

    async def recall_episodes(self, scope: str, query: str, k: int = 3) -> list[dict]:
        """按关键词 + 向量召回相关事件记录；没有命中就退回最近几条。"""
        episodes = await self.store.recent_episodes(scope, 40)
        if not episodes:
            return []

        scored: list[tuple[float, dict]] = []
        for ep in episodes:
            rel = _relevance(query, ep.get("text") or "")
            if rel > 0:
                scored.append((rel, ep))
        scored.sort(key=lambda kv: kv[0], reverse=True)
        keyword_ids = [int(ep["id"]) for _, ep in scored[: max(k * 4, k)]]

        vector_ids: list[int] = []
        if self._vector_ready:
            try:
                hits = await self.vector.search(scope, "episode", query, max(k * 4, k))
                vector_ids = [ref_id for ref_id, _ in hits]
            except Exception:
                log.warning("事件向量检索失败，使用纯关键词", exc_info=True)

        ep_map = {int(ep["id"]): ep for ep in episodes}
        if keyword_ids or vector_ids:
            fused = _rrf_fuse(keyword_ids, vector_ids, k)
            picked = [ep_map[i] for i in fused if i in ep_map]
            if picked:
                return picked

        # 问的话跟历史无关（「在吗」「吃饭了」），给最近几条兜底
        return episodes[-k:]

    async def recall_diaries(self, scope: str, query: str, k: int = 2) -> list[dict]:
        """按语义召回以前写过的日记。只在本 scope 里找，不会串到别人。"""
        if not self._vector_ready:
            return []
        try:
            hits = await self.vector.search(scope, "diary", query, max(k * 3, k))
        except Exception:
            log.warning("日记向量检索失败", exc_info=True)
            return []
        if not hits:
            return []

        results: list[dict] = []
        for diary_id, score in hits:
            cur = await self.store.db.execute(
                "SELECT * FROM diaries WHERE id=?", (diary_id,)
            )
            row = await cur.fetchone()
            if row is None:
                continue
            data = dict(row)
            # 双保险：向量库里的 scope 就分开了，这里再核一次
            if scope and data.get("scope") and data["scope"] != scope:
                continue
            results.append({**data, "score": score})
            if len(results) >= k:
                break
        return results

    async def recall_all(self, scope: str, query: str, k: int = 5, ep_k: int = 3) -> dict:
        return {
            "facts": await self.recall(scope, query, k),
            "episodes": await self.recall_episodes(scope, query, ep_k),
            "diaries": await self.recall_diaries(scope, query, 2),
        }

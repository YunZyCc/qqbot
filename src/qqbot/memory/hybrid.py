from __future__ import annotations

import logging

from .retrieve import retrieve
from .store import Store
from .vector import NumpyVectorIndex

log = logging.getLogger(__name__)

RRF_K = 60


class HybridRetriever:
    """关键词 + 向量，RRF 融合，再乘时间衰减。向量不可用时退化为纯关键词。"""

    def __init__(self, store: Store, vector: NumpyVectorIndex | None = None) -> None:
        self.store = store
        self.vector = vector

    async def recall(self, scope: str, query: str, k: int = 5) -> list[dict]:
        facts = await self.store.active_facts(scope)
        if not facts:
            return []

        keyword = retrieve(query, facts, max(k * 4, k))
        keyword_ids = [int(f["id"]) for f in keyword]

        vector_ids: list[int] = []
        if self.vector is not None and self.vector.embedder.dim:
            try:
                hits = await self.vector.search(scope, "fact", query, max(k * 4, k))
                vector_ids = [ref_id for ref_id, _ in hits]
            except Exception:
                log.warning("向量检索失败，使用纯关键词", exc_info=True)

        if not vector_ids:
            return keyword[:k]

        scores: dict[int, float] = {}
        for rank, fact_id in enumerate(keyword_ids):
            scores[fact_id] = scores.get(fact_id, 0.0) + 1.0 / (RRF_K + rank)
        for rank, fact_id in enumerate(vector_ids):
            scores[fact_id] = scores.get(fact_id, 0.0) + 1.0 / (RRF_K + rank)

        fact_map = {int(f["id"]): f for f in facts}
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        return [fact_map[fact_id] for fact_id, _ in ranked if fact_id in fact_map][:k]

from __future__ import annotations

import logging

import numpy as np

from .embedding import EmbeddingProvider
from .store import Store

log = logging.getLogger(__name__)


class NumpyVectorIndex:
    """全量余弦检索；数据量到几万条以内都够用。"""

    def __init__(self, store: Store, embedder: EmbeddingProvider) -> None:
        self.store = store
        self.embedder = embedder
        self.model = embedder.model
        self.dim = embedder.dim

    async def upsert(self, scope: str, ref_type: str, ref_id: int, text: str) -> None:
        if not text.strip() or not self.embedder.dim:
            return
        try:
            vectors = await self.embedder.embed([text])
        except Exception:
            log.warning("生成 embedding 失败，跳过（scope=%s %s:%s）", scope, ref_type, ref_id)
            return
        if not vectors:
            return
        vec = np.asarray(vectors[0], dtype=np.float32)
        await self.store.upsert_embedding(
            scope, ref_type, ref_id, self.model, self.dim, vec.tobytes()
        )

    async def search(
        self, scope: str, ref_type: str, query: str, k: int
    ) -> list[tuple[int, float]]:
        rows = await self.store.load_embeddings(scope, ref_type, self.model)
        if not rows or not query.strip():
            return []
        try:
            query_vectors = await self.embedder.embed([query])
        except Exception:
            log.warning("query embedding 失败，回退关键词")
            return []
        if not query_vectors:
            return []

        q = np.asarray(query_vectors[0], dtype=np.float32)
        q_norm = np.linalg.norm(q) + 1e-8
        q = q / q_norm

        ids: list[int] = []
        matrix: list[np.ndarray] = []
        for row in rows:
            vec = np.frombuffer(row["vector"], dtype=np.float32)
            if vec.shape[0] != self.dim:
                continue
            ids.append(int(row["ref_id"]))
            matrix.append(vec / (np.linalg.norm(vec) + 1e-8))
        if not ids:
            return []

        scores = np.vstack(matrix) @ q
        order = np.argsort(-scores)[: max(1, k)]
        return [(ids[i], float(scores[i])) for i in order]

    async def rebuild(self, scope: str, ref_type: str, items: list[tuple[int, str]]) -> int:
        await self.store.delete_embeddings(scope, ref_type, self.model)
        count = 0
        for ref_id, text in items:
            await self.upsert(scope, ref_type, ref_id, text)
            count += 1
        return count

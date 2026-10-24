from __future__ import annotations

import json
import logging
from pathlib import Path

from .store import Store
from .vector import NumpyVectorIndex

log = logging.getLogger(__name__)

ALLOWED_SUFFIX = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
STICKER_SCOPE = "sticker:global"


class StickerLibrary:
    """本地表情包库：扫描目录、建索引、语义搜索。"""

    def __init__(self, store: Store, settings, vector: NumpyVectorIndex | None = None):
        self.store = store
        self.settings = settings
        self.vector = vector
        self.dir = Path(settings.sticker_dir)

    def _load_index(self) -> dict:
        path = self.dir / "index.json"
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    async def scan(self) -> int:
        self.dir.mkdir(parents=True, exist_ok=True)
        index = self._load_index()
        count = 0
        for path in sorted(self.dir.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in ALLOWED_SUFFIX:
                continue
            rel = path.relative_to(self.dir).as_posix()
            meta = index.get(rel) or {}
            tags = " ".join(meta.get("tags") or [path.parent.name, path.stem])
            emotion = meta.get("emotion") or path.parent.name
            description = meta.get("description") or f"{path.parent.name} 表情包"
            sticker_id = await self.store.upsert_sticker(
                rel, rel, tags, emotion, description
            )
            if self.vector is not None and sticker_id:
                await self.vector.upsert(
                    STICKER_SCOPE,
                    "sticker",
                    sticker_id,
                    f"{tags} {emotion} {description}",
                )
            count += 1
        if count:
            log.info("表情包索引完成：%s 张", count)
        return count

    async def search(self, query: str, k: int = 3) -> list[dict]:
        query = (query or "").strip()
        if not query:
            return []
        if self.vector is not None:
            try:
                hits = await self.vector.search(STICKER_SCOPE, "sticker", query, k)
                results = []
                for sticker_id, score in hits:
                    row = await self.store.get_sticker(sticker_id)
                    if row is not None:
                        results.append({**row, "score": score})
                if results:
                    return results
            except Exception:
                log.warning("表情包向量搜索失败，回退关键词", exc_info=True)
        return await self.store.search_stickers_keyword(query, k)

    def resolve(self, file: str) -> Path | None:
        """安全解析表情包路径，防止目录穿越。"""
        try:
            path = (self.dir / file).resolve()
            root = self.dir.resolve()
        except OSError:
            return None
        if path != root and root not in path.parents:
            return None
        if path.suffix.lower() not in ALLOWED_SUFFIX:
            return None
        try:
            if path.stat().st_size > self.settings.sticker_max_size_kb * 1024:
                return None
        except OSError:
            return None
        return path

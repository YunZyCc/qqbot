from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path

from .store import Store
from .vector import NumpyVectorIndex

log = logging.getLogger(__name__)

ALLOWED_SUFFIX = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
STICKER_SCOPE = "sticker:global"
AUTO_DIR = "auto"
_MIME_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


class StickerLibrary:
    """本地表情包库：扫描目录、建索引、语义搜索。"""

    def __init__(self, store: Store, settings, vector: NumpyVectorIndex | None = None):
        self.store = store
        self.settings = settings
        self.vector = vector
        self.dir = Path(settings.sticker_dir)
        self._recent: list[int] = []

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
        results: list[dict] = []
        if self.vector is not None:
            try:
                hits = await self.vector.search(STICKER_SCOPE, "sticker", query, k * 3)
                for sticker_id, score in hits:
                    row = await self.store.get_sticker(sticker_id)
                    if row is not None:
                        results.append({**row, "score": score})
            except Exception:
                log.warning("表情包向量搜索失败，回退关键词", exc_info=True)
        if not results:
            results = await self.store.search_stickers_keyword(query, k * 3)

        # 最近发过的往后放，避免连着推同一张
        picked: list[dict] = []
        for row in results:
            if int(row["id"]) in self._recent and len(results) > k:
                continue
            picked.append(row)
            if len(picked) >= k:
                break
        return picked

    def mark_used(self, sticker_id: int) -> None:
        self._recent.append(int(sticker_id))
        self._recent = self._recent[-5:]

    async def import_from_image(
        self, data: bytes, mime: str, description: str, digest: str
    ) -> str | None:
        """把别人发的表情包收进库，以后能拿出来用。

        只收识别成功且不大的图；按 sha256 去重；每天有张数上限。
        """
        if not getattr(self.settings, "sticker_auto_import", True):
            return None
        if not description.strip() or not digest:
            return None
        max_kb = int(getattr(self.settings, "sticker_auto_import_max_kb", 2048))
        if len(data) > max_kb * 1024:
            return None

        ext = _MIME_EXT.get(mime, ".jpg")
        rel = f"{AUTO_DIR}/{digest}{ext}"
        path = self.dir / rel
        if path.exists():
            return None

        daily_max = int(getattr(self.settings, "sticker_auto_import_daily_max", 20))
        today = dt.date.today().isoformat()
        counter_key = f"sticker_import:{today}"
        count = int(await self.store.get_setting(counter_key, "0") or 0)
        if daily_max > 0 and count >= daily_max:
            return None

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except OSError:
            log.warning("表情包入库写文件失败：%s", rel, exc_info=True)
            return None

        sticker_id = await self.store.upsert_sticker(
            rel, rel, "自动入库", "其他", description[:200]
        )
        if self.vector is not None and sticker_id:
            await self.vector.upsert(
                STICKER_SCOPE, "sticker", sticker_id, f"自动入库 {description[:200]}"
            )
        await self.store.set_setting(counter_key, str(count + 1))
        log.info("表情包已入库：%s（%s）", rel, description[:30])
        return rel

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

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

MIME_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
}


class ImageCache:
    """下载、校验、缓存收到的图片，供视觉模型和后续追问使用。"""

    def __init__(self, cache_dir: Path, max_mb: int = 5) -> None:
        self.dir = cache_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_mb * 1024 * 1024

    async def fetch(self, url: str | None, file: str | None = None) -> tuple[bytes, str] | None:
        target = url or (file if file and str(file).startswith("http") else None)
        if not target:
            return None
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(target)
                resp.raise_for_status()
                data = resp.content
        except Exception:
            log.warning("图片下载失败：%s", target[:80], exc_info=True)
            return None

        if not data or len(data) > self.max_bytes:
            log.info("图片为空或超过上限，跳过（%s bytes）", len(data))
            return None

        mime = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip().lower()
        if mime not in MIME_EXT:
            mime = "image/jpeg"
        return data, mime

    def save(self, data: bytes, mime: str) -> tuple[str, Path]:
        digest = hashlib.sha256(data).hexdigest()
        ext = MIME_EXT.get(mime, "jpg")
        path = self.dir / f"{digest}.{ext}"
        if not path.exists():
            path.write_bytes(data)
        return digest, path

    def load(self, sha256: str) -> Path | None:
        for ext in MIME_EXT.values():
            path = self.dir / f"{sha256}.{ext}"
            if path.exists():
                return path
        return None

    def cleanup(self, days: int = 7) -> int:
        import time

        cutoff = time.time() - days * 86400
        removed = 0
        for path in self.dir.glob("*"):
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
                removed += 1
        if removed:
            log.info("清理了 %s 张过期图片缓存", removed)
        return removed

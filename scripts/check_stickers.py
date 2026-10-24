"""手动验证表情包索引与搜索（不需要 NapCat）。"""

from __future__ import annotations

import asyncio
import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from qqbot.config import get_settings  # noqa: E402
from qqbot.memory.embedding import OpenAICompatibleEmbedding  # noqa: E402
from qqbot.memory.stickers import StickerLibrary  # noqa: E402
from qqbot.memory.store import Store  # noqa: E402
from qqbot.memory.vector import NumpyVectorIndex  # noqa: E402

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


async def main() -> None:
    settings = get_settings()
    sticker_dir = settings.sticker_dir
    (sticker_dir / "happy").mkdir(parents=True, exist_ok=True)
    (sticker_dir / "speechless").mkdir(parents=True, exist_ok=True)
    (sticker_dir / "happy" / "开心.png").write_bytes(PNG_1PX)
    (sticker_dir / "speechless" / "无语.png").write_bytes(PNG_1PX)

    store = Store(settings.data_dir / "check_stickers.db", default_scope="private:1")
    await store.init()

    embedder = OpenAICompatibleEmbedding(
        settings.embedding_base_url,
        settings.embedding_api_key,
        settings.embedding_model,
        settings.embedding_dim,
    )
    vector = NumpyVectorIndex(store, embedder)
    library = StickerLibrary(store, settings, vector)

    count = await library.scan()
    print(f"索引数量：{count}")
    for query in ["开心", "无语", "想笑"]:
        hits = await library.search(query, 2)
        print(f"{query} -> {[h['key'] for h in hits]}")

    await embedder.close()
    await store.close()
    (settings.data_dir / "check_stickers.db").unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(main())

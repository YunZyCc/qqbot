from __future__ import annotations

from types import SimpleNamespace

from qqbot.memory.stickers import StickerLibrary
from qqbot.memory.store import Store


async def _library(tmp_path):
    sticker_dir = tmp_path / "stickers"
    (sticker_dir / "happy").mkdir(parents=True)
    (sticker_dir / "happy" / "开心.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    (sticker_dir / "speechless").mkdir()
    (sticker_dir / "speechless" / "无语.jpg").write_bytes(b"\xff\xd8\xff\xe0fake")

    settings = SimpleNamespace(sticker_dir=sticker_dir, sticker_max_size_kb=2048)
    store = Store(tmp_path / "s.db", default_scope="private:1")
    await store.init()
    return store, StickerLibrary(store, settings, vector=None)


async def test_scan_and_keyword_search(tmp_path):
    store, library = await _library(tmp_path)
    assert await library.scan() == 2

    hits = await library.search("开心")
    assert hits and hits[0]["file"] == "happy/开心.png"
    await store.close()


async def test_resolve_blocks_traversal(tmp_path):
    store, library = await _library(tmp_path)
    assert library.resolve("happy/开心.png") is not None
    assert library.resolve("../outside.png") is None
    assert library.resolve("/etc/passwd") is None
    await store.close()


async def test_resolve_rejects_unknown_suffix(tmp_path):
    store, library = await _library(tmp_path)
    (library.dir / "bad.exe").write_bytes(b"x")
    assert library.resolve("bad.exe") is None
    await store.close()

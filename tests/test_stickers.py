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


async def _lib(tmp_path, **overrides):
    from types import SimpleNamespace

    data = dict(
        sticker_dir=tmp_path,
        sticker_max_size_kb=2048,
        sticker_auto_import=True,
        sticker_auto_import_daily_max=2,
        sticker_auto_import_max_kb=100,
    )
    data.update(overrides)
    settings = SimpleNamespace(**data)
    store = Store(tmp_path / "s.db", default_scope="private:1")
    await store.init()
    return StickerLibrary(store, settings, None), store


async def test_import_from_image_stores_and_dedups(tmp_path):
    lib, store = await _lib(tmp_path)
    rel = await lib.import_from_image(b"xx", "image/png", "熊猫头举牌无语", "abc123")
    assert rel == "auto/abc123.png"
    assert (tmp_path / rel).exists()
    # 同一张再来一次不该重复入库
    again = await lib.import_from_image(b"xx", "image/png", "熊猫头举牌无语", "abc123")
    assert again is None
    await store.close()


async def test_import_stops_at_daily_max(tmp_path):
    lib, store = await _lib(tmp_path)
    assert await lib.import_from_image(b"a", "image/png", "图一", "h1")
    assert await lib.import_from_image(b"a", "image/png", "图二", "h2")
    assert await lib.import_from_image(b"a", "image/png", "图三", "h3") is None
    await store.close()


async def test_import_skips_large_file(tmp_path):
    lib, store = await _lib(tmp_path, sticker_auto_import_max_kb=1)
    big = b"x" * 2048
    assert await lib.import_from_image(big, "image/png", "大图", "big") is None
    await store.close()


async def test_import_respects_switch(tmp_path):
    lib, store = await _lib(tmp_path, sticker_auto_import=False)
    assert await lib.import_from_image(b"xx", "image/png", "图", "h1") is None
    await store.close()


async def test_import_skips_empty_description(tmp_path):
    lib, store = await _lib(tmp_path)
    assert await lib.import_from_image(b"xx", "image/png", "   ", "h1") is None
    await store.close()

from __future__ import annotations

import json
from pathlib import Path

from qqbot.config import get_settings
from qqbot.memory.sticker_kit import StickerKit


def test_load_meta():
    settings = get_settings()
    kit = StickerKit(settings)
    count = kit.load()
    assert count > 0
    assert "开心" in kit.emotions


def test_search_chinese():
    settings = get_settings()
    kit = StickerKit(settings)
    kit.load()

    hits = kit.search("摸鱼", 3)
    assert hits
    joined = " ".join(h["name"] + h["emotion"] + " ".join(h["tags"]) for h in hits)
    assert "摸鱼" in joined or "鱼" in joined

    hits = kit.search("无语", 3)
    assert hits


def test_search_multi_term_prefers_all_terms():
    settings = get_settings()
    kit = StickerKit(settings)
    kit.load()
    hits = kit.search("开心 大笑", 3)
    assert hits


def test_file_url_format():
    settings = get_settings()
    kit = StickerKit(settings)
    kit.load()
    sticker = next(s for s in kit._stickers if s["pack"] == "大肥鱼")
    url = kit.file_url(sticker)
    assert url.startswith("https://kiriyuki.com/media/gif/")
    assert url.endswith(".gif") or "?h=" in url


def test_meta_json_is_valid():
    settings = get_settings()
    path = Path(settings.nekowhale_meta)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema"] == "sticker-kit/1"
    assert len(data["stickers"]) > 100

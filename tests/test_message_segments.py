from __future__ import annotations

from qqbot.core.message import (
    build,
    seg_at,
    seg_face,
    seg_image,
    seg_mface,
    seg_record,
    seg_text,
    to_user_text,
)


def test_build_filters_empty():
    assert build([seg_text("a"), None, {}]) == [seg_text("a")]  # type: ignore[list-item]


def test_segment_shapes():
    assert seg_face(14)["type"] == "face"
    assert seg_mface("a.gif")["type"] == "mface"
    assert seg_image("a.png")["data"]["file"] == "a.png"
    assert seg_record("a.mp3")["data"]["file"] == "a.mp3"
    assert seg_at(123)["data"]["qq"] == "123"


def test_to_text_keeps_placeholders():
    text = to_user_text([seg_text("你好"), seg_face(14), seg_image("x.png"), seg_record("v.mp3")])
    assert "你好" in text
    assert "[表情:微笑]" in text
    assert "[图片]" in text
    assert "[语音]" in text

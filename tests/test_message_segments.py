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


def test_unknown_face_has_no_id():
    """未知表情 id 不该露出编号，否则模型只会说「我看不见这个编号」。"""
    text = to_user_text([seg_face(9999)])
    assert text == "[表情:表情]"
    assert "9999" not in text


def test_image_always_single_placeholder():
    """表情包图片和普通图片都先留 [图片]，由视觉描述统一替换。"""
    sticker = {"type": "image", "data": {"file": "a.gif", "sub_type": "1"}}
    photo = {"type": "image", "data": {"file": "b.jpg"}}
    assert to_user_text([sticker]) == "[图片]"
    assert to_user_text([photo, photo]) == "[图片][图片]"


def test_mface_uses_summary_when_present():
    """QQ 收到 mface 时 summary 通常带方括号，去掉再拼，别出现 [表情包:[动画表情]]。"""
    seg = {"type": "mface", "data": {"file": "a.gif", "summary": "[动画表情]"}}
    assert to_user_text([seg]) == "[表情包:动画表情]"


def test_mface_without_summary():
    seg = {"type": "mface", "data": {"file": "a.gif"}}
    assert to_user_text([seg]) == "[表情包]"


def test_attach_image_text_replaces_placeholder():
    from qqbot.modules.chat import _attach_image_text

    assert _attach_image_text("[图片]", ["[图片:熊猫头举牌无语]"]) == "[图片:熊猫头举牌无语]"
    assert (
        _attach_image_text("看看这个[图片]", ["[图片:一只猫]"])
        == "看看这个[图片:一只猫]"
    )


def test_attach_image_text_appends_without_placeholder():
    from qqbot.modules.chat import _attach_image_text

    assert _attach_image_text("hi", ["[图片:猫]"]) == "hi[图片:猫]"


def test_attach_image_text_multiple():
    from qqbot.modules.chat import _attach_image_text

    text = _attach_image_text("[图片][图片]", ["[图片:图一]", "[图片:图二]"])
    assert text == "[图片:图一][图片:图二]"

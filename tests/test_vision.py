from __future__ import annotations

import io

from PIL import Image

from qqbot.vision import _flatten_image


def _make_gif() -> bytes:
    frames = [Image.new("RGB", (8, 8), color) for color in ("red", "blue")]
    buffer = io.BytesIO()
    frames[0].save(
        buffer, format="GIF", save_all=True, append_images=frames[1:], duration=100
    )
    return buffer.getvalue()


def test_static_image_untouched():
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "green").save(buffer, format="PNG")
    raw = buffer.getvalue()

    out, mime = _flatten_image(raw, "image/png")
    assert out is raw
    assert mime == "image/png"


def test_gif_is_flattened_to_jpeg():
    """Ollama 对动图支持不好，GIF 必须转成静帧 JPEG 再送。"""
    out, mime = _flatten_image(_make_gif(), "image/gif")
    assert mime == "image/jpeg"
    with Image.open(io.BytesIO(out)) as opened:
        assert opened.format == "JPEG"


def test_broken_image_falls_back_to_original():
    raw = b"not an image at all"
    out, mime = _flatten_image(raw, "image/gif")
    assert out == raw
    assert mime == "image/gif"


def test_webp_flattened():
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(buffer, format="WEBP")
    out, mime = _flatten_image(buffer.getvalue(), "image/webp")
    assert mime == "image/jpeg"
    with Image.open(io.BytesIO(out)) as opened:
        assert opened.format == "JPEG"

"""生成一批简单的占位表情包，方便先跑通链路。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

STICKERS = {
    "happy/开心.png": ("开心", (255, 214, 102), (80, 60, 20)),
    "speechless/无语.png": ("无语", (180, 190, 200), (40, 40, 50)),
    "comfort/摸摸头.png": ("摸摸头", (255, 183, 197), (90, 40, 60)),
    "night/晚安.png": ("晚安", (120, 140, 220), (240, 240, 255)),
    "cheer/加油.png": ("加油", (140, 220, 160), (20, 70, 40)),
}


def _font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("msyh.ttc", "simhei.ttf", "simsun.ttc"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def main() -> None:
    root = Path("data/stickers")
    for rel, (text, bg, fg) in STICKERS.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", (240, 240), bg)
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((12, 12, 228, 228), radius=24, outline=fg, width=4)
        font = _font(56)
        bbox = draw.textbbox((0, 0), text, font=font)
        x = (240 - (bbox[2] - bbox[0])) / 2 - bbox[0]
        y = (240 - (bbox[3] - bbox[1])) / 2 - bbox[1]
        draw.text((x, y), text, font=font, fill=fg)
        image.save(path)
        print(f"生成 {path}（{path.stat().st_size} bytes）")


if __name__ == "__main__":
    main()

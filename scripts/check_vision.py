"""手动验证视觉模型（需要 Ollama 和 minicpm-v）。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from qqbot.config import get_settings  # noqa: E402
from qqbot.vision import OpenAICompatibleVision  # noqa: E402

DEFAULT_IMAGE = r"C:\Windows\Web\Wallpaper\Windows\img0.jpg"


async def main() -> None:
    settings = get_settings()
    image_path = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_IMAGE)
    vision = OpenAICompatibleVision(
        settings.vision_base_url,
        settings.vision_api_key,
        settings.vision_model,
        settings.vision_timeout,
    )
    print(f"图片: {image_path}")
    description = await vision.describe(image_path.read_bytes(), "image/jpeg")
    print("描述:", description)
    await vision.close()


if __name__ == "__main__":
    asyncio.run(main())

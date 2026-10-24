from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class MediaModule:
    """表情 / 表情包 / 语音。

    发送动作已在 capabilities 注册；表情包检索与 TTS 合成待实现。
    """

    name = "media"

    def setup(self, ctx) -> None:
        self.ctx = ctx
        log.info("media 模块已启用（表情包库与 TTS 待实现）")

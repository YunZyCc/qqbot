from __future__ import annotations

import logging

from ..memory.social import fallback_qzone

log = logging.getLogger(__name__)


class QzoneModule:
    """QQ 空间说说：主路径是 LLM 自己调 post_qzone 工具，这里只做兜底。

    每天到点检查一次，如果当天一条都没发，就补一条。保证「一天 1~3 条」的下限。
    """

    name = "qzone"

    def setup(self, ctx) -> None:
        self.ctx = ctx
        settings = ctx.settings
        if not settings.qzone_enabled:
            log.info("说说功能已关闭")
            return
        ctx.scheduler.cron(
            f"{settings.qzone_fallback_minute} {settings.qzone_fallback_hour} * * *",
            self.daily_fallback,
            name="说说兜底",
            job_id="qzone-fallback",
        )
        log.info(
            "qzone 模块已启用（每天 %02d:%02d 检查是否一条都没发）",
            settings.qzone_fallback_hour,
            settings.qzone_fallback_minute,
        )

    async def daily_fallback(self) -> None:
        try:
            posted = await fallback_qzone(self.ctx)
            if posted:
                log.info("今天一条都没发，兜底补了一条说说")
        except Exception:
            log.exception("说说兜底失败")

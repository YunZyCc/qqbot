from __future__ import annotations

import logging

from ..memory.social import rotate_signature

log = logging.getLogger(__name__)


class ProfileModule:
    """资料维护：每天换一次个性签名。"""

    name = "profile"

    def setup(self, ctx) -> None:
        self.ctx = ctx
        settings = ctx.settings
        if not settings.signature_enabled:
            log.info("签名轮换已关闭")
            return
        ctx.scheduler.cron(
            f"{settings.signature_minute} {settings.signature_hour} * * *",
            self.rotate,
            name="每日签名轮换",
            job_id="signature-daily",
        )
        log.info(
            "profile 模块已启用（每天 %02d:%02d 换签名）",
            settings.signature_hour,
            settings.signature_minute,
        )

    async def rotate(self) -> None:
        try:
            changed = await rotate_signature(self.ctx)
            if changed:
                log.info("签名已更新")
            else:
                log.info("这次没换签名（关闭/超限/内容不合格）")
        except Exception:
            log.exception("换签名失败")

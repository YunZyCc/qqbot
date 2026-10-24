from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class ProfileModule:
    """资料维护：目前只注册签名轮换骨架。"""

    name = "profile"

    def setup(self, ctx) -> None:
        self.ctx = ctx
        ctx.scheduler.cron(
            "0 9 * * *",
            self.rotate_signature,
            name="每日签名轮换",
            job_id="signature-daily",
        )
        log.info("profile 模块已启用（签名轮换待实现）")

    async def rotate_signature(self) -> None:
        log.info("profile: 到点更换签名（待实现）")

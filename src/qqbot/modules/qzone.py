from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class QzoneModule:
    """QQ 空间说说：目前只注册调度骨架，发布逻辑待实现。"""

    name = "qzone"

    def setup(self, ctx) -> None:
        self.ctx = ctx
        ctx.scheduler.cron(
            "0 20 * * *",
            self.generate_draft,
            name="每日说说草稿",
            job_id="qzone-daily",
        )
        log.info("qzone 模块已启用（每日 20:00 生成草稿，业务待实现）")

    async def generate_draft(self) -> None:
        log.info("qzone: 到点生成说说草稿（待实现）")

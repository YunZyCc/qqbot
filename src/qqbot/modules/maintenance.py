from __future__ import annotations

import logging

from ..memory.summary import merge_rolling

log = logging.getLogger(__name__)


class MaintenanceModule:
    """每日维护：合并 rolling 摘要、归档旧事实。"""

    name = "maintenance"

    def setup(self, ctx) -> None:
        self.ctx = ctx
        ctx.scheduler.cron(
            "0 3 * * *",
            self.daily_maintenance,
            name="每日记忆维护",
            job_id="memory-maintenance",
        )
        log.info("maintenance 模块已启用（每日 03:00）")

    async def daily_maintenance(self) -> None:
        ctx = self.ctx
        scope = f"private:{ctx.settings.owner_qq}"
        try:
            await merge_rolling(ctx.store, ctx.llm, scope)
        except Exception:
            log.exception("合并 rolling 摘要失败")

        try:
            await self._archive_old_facts(scope)
        except Exception:
            log.exception("归档旧事实失败")

    async def _archive_old_facts(self, scope: str) -> None:
        import time

        cutoff = time.time() - 90 * 86400
        cur = await self.ctx.store.db.execute(
            "UPDATE facts SET status='archived'"
            " WHERE scope=? AND status IN ('superseded','frozen') AND updated_at < ?",
            (scope, cutoff),
        )
        await self.ctx.store.db.commit()
        if cur.rowcount:
            log.info("归档了 %s 条旧事实（scope=%s）", cur.rowcount, scope)

from __future__ import annotations

import asyncio
import datetime as dt
import logging

from ..memory.plan import generate_plan, today_plan

log = logging.getLogger(__name__)


class ScheduleModule:
    """她的一天：每天定时生成一份日程，聊天天天都在用。"""

    name = "schedule"

    def setup(self, ctx) -> None:
        self.ctx = ctx
        settings = ctx.settings
        if not settings.schedule_enabled:
            log.info("日程功能已关闭")
            return
        ctx.scheduler.cron(
            f"0 {settings.schedule_hour} * * *",
            self.daily,
            name="每日日程生成",
            job_id="schedule-daily",
        )
        # 启动时补跑当天：服务可能昨晚是关着的
        asyncio.create_task(self._bootstrap())
        log.info("schedule 模块已启用（每天 %02d:00 生成日程）", settings.schedule_hour)

    async def _bootstrap(self) -> None:
        await asyncio.sleep(5)
        try:
            if await today_plan(self.ctx.store) is None:
                log.info("今天还没有日程，补一份")
                await generate_plan(self.ctx, dt.date.today())
        except Exception:
            log.exception("补生成日程失败")

    async def daily(self) -> None:
        try:
            plan = await generate_plan(self.ctx, dt.date.today())
            if plan is None:
                log.warning("今天的日程没生成出来，聊天时不会注入")
        except Exception:
            log.exception("每日日程生成失败")

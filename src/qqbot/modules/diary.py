from __future__ import annotations

import asyncio
import datetime as dt
import logging

from ..memory.diary import backfill_diaries, generate_diary

log = logging.getLogger(__name__)


class DiaryModule:
    """每天一篇日记：有对话写回顾，没有写独处；启动后补写前一天。"""

    name = "diary"

    def setup(self, ctx) -> None:
        self.ctx = ctx
        settings = ctx.settings
        if not settings.diary_enabled:
            log.info("日记功能已关闭")
            return

        ctx.scheduler.cron(
            f"{settings.diary_minute} {settings.diary_hour} * * *",
            self.write_yesterday,
            name="每日日记",
            job_id="diary-daily",
        )
        asyncio.create_task(self._bootstrap())
        log.info("diary 模块已启用（每日 %02d:%02d 写日记）", settings.diary_hour, settings.diary_minute)

    async def _bootstrap(self) -> None:
        await asyncio.sleep(3)
        settings = self.ctx.settings
        try:
            written = await backfill_diaries(
                self.ctx.store,
                self.ctx.llm,
                dt.date.today(),
                settings.diary_backfill_days,
            )
            if written:
                log.info("启动补写日记 %s 篇", written)
            else:
                log.info("启动检查完成，没有缺失的日记")
        except Exception:
            log.exception("启动补写日记失败")

    async def write_yesterday(self) -> None:
        day = dt.date.today() - dt.timedelta(days=1)
        try:
            await generate_diary(self.ctx.store, self.ctx.llm, day)
        except Exception:
            log.exception("每日日记生成失败")

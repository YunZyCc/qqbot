from __future__ import annotations

import asyncio
import datetime as dt
import logging

from ..memory.diary import backfill_diaries, generate_diary

log = logging.getLogger(__name__)


async def _activity(ctx, day) -> str:
    """当天她做过什么（只有行为）。不给内容，免得日记里抄说说原文。"""
    try:
        from ..memory.social import activity_summary

        return await activity_summary(ctx.store)
    except Exception:
        log.warning("读取活动摘要失败", exc_info=True)
        return ""


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

    def _targets(self) -> list[tuple[str, str, bool]]:
        """要写日记的 scope：主人必写（含独处），好友只在当天聊过才写。"""
        settings = self.ctx.settings
        targets: list[tuple[str, str, bool]] = [
            (f"private:{settings.owner_qq}", "对方", True)
        ]
        for qq in settings.friend_whitelist_ids:
            targets.append((f"private:{qq}", "对方", False))
        return targets

    async def _bootstrap(self) -> None:
        await asyncio.sleep(3)
        settings = self.ctx.settings
        try:
            written = await backfill_diaries(
                self.ctx.store,
                self.ctx.llm,
                dt.date.today(),
                settings.diary_backfill_days,
                self._targets(),
            )
            if written:
                log.info("启动补写日记 %s 篇", written)
            else:
                log.info("启动检查完成，没有缺失的日记")
        except Exception:
            log.exception("启动补写日记失败")

    async def write_yesterday(self) -> None:
        day = dt.date.today() - dt.timedelta(days=1)
        for scope, who, allow_solo in self._targets():
            try:
                await generate_diary(
                    self.ctx.store,
                    self.ctx.llm,
                    day,
                    scope,
                    who,
                    allow_solo,
                    activity=await _activity(self.ctx, day),
                    vector=self.ctx.vector,
                )
            except Exception:
                log.exception("每日日记生成失败（%s）", scope)

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class ScheduleModule:
    """她的一天。

    日程不再定时生成，改成「第一次聊天时现生成」——
    这样她的一天是从对话开始的，而不是七点整自己凭空醒来。
    对方问「明天干嘛」时由 plan_lookup 工具现生成，也不依赖任何定时任务。
    """

    name = "schedule"

    def setup(self, ctx) -> None:
        self.ctx = ctx
        if not ctx.settings.schedule_enabled:
            log.info("日程功能已关闭")
        else:
            log.info("schedule 模块已启用（首次聊天时生成当天日程）")

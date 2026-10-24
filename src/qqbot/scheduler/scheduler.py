from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

log = logging.getLogger(__name__)


class Scheduler:
    """APScheduler 薄封装：定时说说、签名轮换、主动消息都走这里。"""

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()

    def start(self) -> None:
        if not self._scheduler.running:
            self._scheduler.start()
            log.info("调度器已启动")

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            log.info("调度器已关闭")

    def every(self, seconds: int, fn, *, name: str = "", job_id: str | None = None):
        return self._scheduler.add_job(
            fn,
            IntervalTrigger(seconds=seconds),
            name=name,
            id=job_id,
            replace_existing=True,
            misfire_grace_time=60,
        )

    def cron(self, expr: str, fn, *, name: str = "", job_id: str | None = None):
        return self._scheduler.add_job(
            fn,
            CronTrigger.from_crontab(expr),
            name=name,
            id=job_id,
            replace_existing=True,
            misfire_grace_time=300,
        )

    def once(
        self, delay_seconds: float, fn, *, name: str = "", job_id: str | None = None
    ):
        """延迟执行一次，用于启动后的补跑（服务没开着时错过的定时任务）。"""
        run_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)
        return self._scheduler.add_job(
            fn,
            DateTrigger(run_date=run_at),
            name=name,
            id=job_id,
            replace_existing=True,
            misfire_grace_time=300,
        )

    def jobs(self) -> list:
        return list(self._scheduler.get_jobs())

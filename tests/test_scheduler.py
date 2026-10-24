from __future__ import annotations

from qqbot.scheduler.scheduler import Scheduler


async def test_scheduler_registers_and_lists_job():
    scheduler = Scheduler()
    scheduler.start()
    called: list[int] = []

    def job() -> None:
        called.append(1)

    scheduler.every(60, job, name="测试任务", job_id="test-job")
    jobs = scheduler.jobs()
    assert any(j.id == "test-job" for j in jobs)
    assert called == []
    scheduler.shutdown()

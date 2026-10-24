from __future__ import annotations

import logging

from ..memory.summary import merge_rolling

log = logging.getLogger(__name__)


class MaintenanceModule:
    """每日维护：合并 rolling 摘要、补齐向量、归档旧事实。"""

    name = "maintenance"

    def setup(self, ctx) -> None:
        self.ctx = ctx
        ctx.scheduler.cron(
            "0 3 * * *",
            self.daily_maintenance,
            name="每日记忆维护",
            job_id="memory-maintenance",
        )
        # 服务不一定整晚开着，启动后补跑一次，免得 rolling 摘要和向量长期缺位
        ctx.scheduler.once(
            120,
            self.daily_maintenance,
            name="启动补跑记忆维护",
            job_id="memory-maintenance-boot",
        )
        log.info("maintenance 模块已启用（每日 03:00 + 启动补跑）")

    async def daily_maintenance(self) -> None:
        ctx = self.ctx
        scope = f"private:{ctx.settings.owner_qq}"
        try:
            await merge_rolling(ctx.store, ctx.llm, scope)
        except Exception:
            log.exception("合并 rolling 摘要失败")

        try:
            await self._backfill_embeddings(scope)
        except Exception:
            log.exception("补齐向量失败")

        try:
            await self._archive_old_facts(scope)
        except Exception:
            log.exception("归档旧事实失败")

    async def _backfill_embeddings(self, scope: str) -> None:
        """给没有向量的 episode / 摘要 / 事实补上，历史数据也能被检索到。"""
        vector = getattr(self.ctx, "vector", None)
        if vector is None or not vector.embedder.dim:
            return

        store = self.ctx.store
        cur = await store.db.execute(
            "SELECT ref_type, ref_id FROM embeddings WHERE scope=?", (scope,)
        )
        have = {(row["ref_type"], int(row["ref_id"])) for row in await cur.fetchall()}

        todo: list[tuple[str, int, str]] = []
        for ep in await store.recent_episodes(scope, 200):
            key = ("episode", int(ep["id"]))
            if key not in have and (ep.get("text") or "").strip():
                todo.append(("episode", int(ep["id"]), ep["text"]))
        for fact in await store.active_facts(scope):
            key = ("fact", int(fact["id"]))
            if key not in have:
                todo.append(
                    ("fact", int(fact["id"]), f"{fact['predicate']}: {fact['object']}")
                )

        cur = await store.db.execute(
            "SELECT id, text FROM summaries WHERE scope=? ORDER BY id DESC LIMIT 20",
            (scope,),
        )
        for row in await cur.fetchall():
            key = ("summary", int(row["id"]))
            if key not in have and (row["text"] or "").strip():
                todo.append(("summary", int(row["id"]), row["text"]))

        for ref_type, ref_id, text in todo:
            await vector.upsert(scope, ref_type, ref_id, text)
        if todo:
            log.info("补写 %s 条向量（scope=%s）", len(todo), scope)

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

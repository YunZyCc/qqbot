from __future__ import annotations

import asyncio
import datetime as dt
import logging
import random
import time

from ..core.reply_style import segment_interval, split_reply
from ..prompt.composer import PromptContext

log = logging.getLogger(__name__)

INTENT_HINTS = {
    "morning": "现在是早上。主动跟对方说句早安，可以带一句你今天的打算。",
    "night": "现在是晚上。主动跟对方说句晚安，语气自然点。",
    "miss": "对方已经好几个小时没说话了。主动说一句惦记的话，不要催。",
    "share": "主动分享一件你记得的事，或者你此刻的状态。",
}


class ProactiveModule:
    """主动开口：随机空闲阈值 + 每日额度 + 静默时段 + 概率。"""

    name = "proactive"

    def setup(self, ctx) -> None:
        self.ctx = ctx
        settings = ctx.settings
        if not settings.proactive_enabled:
            log.info("主动开口已关闭")
            return
        ctx.scheduler.every(
            settings.proactive_check_minutes * 60,
            self.tick,
            name="主动开口检查",
            job_id="proactive-tick",
        )
        log.info("proactive 模块已启用（每 %s 分钟检查一次）", settings.proactive_check_minutes)

    async def tick(self) -> None:
        ctx = self.ctx
        settings = ctx.settings
        now = time.time()
        today = dt.date.today().isoformat()
        scope = f"private:{settings.owner_qq}"

        # 服务刚启动时内存里的计时是 0，从库里把最后一条用户消息捞回来
        # 否则 idle 恒为 0，主动消息永远等不到阈值
        if not ctx.last_user_at:
            ctx.last_user_at = await ctx.store.last_message_ts(scope, "user")

        hour = dt.datetime.now().hour
        if settings.proactive_quiet_start <= hour < settings.proactive_quiet_end:
            return

        count = int(await ctx.store.get_setting(f"proactive_count:{today}", "0") or 0)
        if count >= settings.proactive_daily_max:
            return

        last = float(await ctx.store.get_setting("last_proactive_at", "0") or 0)
        if now - last < settings.proactive_min_gap_minutes * 60:
            return

        idle = now - (ctx.last_user_at or last or now)
        threshold = (
            random.uniform(settings.proactive_idle_min, settings.proactive_idle_max) * 60
        )
        if idle < threshold:
            return

        if ctx.last_user_at and now - ctx.last_user_at < 600:
            return

        if ctx.emotion is not None:
            await ctx.emotion.evaluate_ignored()
            await ctx.emotion.fade()

        if random.random() > settings.proactive_probability:
            return

        intent = self._pick_intent(hour, idle, settings)
        text = await self._generate(intent)
        if not text:
            return

        parts = split_reply(
            text,
            2,
            settings.reply_segment_max_chars,
            settings.reply_segment_weight_list,
        )
        for index, part in enumerate(parts):
            if index:
                await asyncio.sleep(segment_interval(settings))
            try:
                await ctx.api.send_private_msg(settings.owner_qq, part)
            except Exception:
                log.exception("主动消息发送失败")
                break

        await ctx.store.add_message(
            scope, settings.bot_qq, "assistant", text, source="proactive"
        )
        await ctx.store.set_setting("last_proactive_at", str(now))
        await ctx.store.set_setting(f"proactive_count:{today}", str(count + 1))
        if ctx.emotion is not None:
            await ctx.emotion.on_proactive_sent(text)
        log.info("已主动开口（%s）：%s", intent, text[:40])

    def _pick_intent(self, hour: int, idle: float, settings) -> str:
        if 6 <= hour < 9:
            return "morning"
        if 22 <= hour < 24:
            return "night"
        if idle >= settings.proactive_miss_hours * 3600:
            return "miss"
        return "share"

    async def _generate(self, intent: str) -> str:
        ctx = self.ctx
        settings = ctx.settings
        scope = f"private:{settings.owner_qq}"

        self_state = await ctx.self_memory.get_state()
        emotion = await ctx.emotion.prompt_text() if ctx.emotion is not None else ""
        diaries = await ctx.store.recent_diaries(1)
        diary_text = diaries[-1]["text"][:300] if diaries else ""
        facts = await ctx.retriever.recall(scope, INTENT_HINTS[intent], 3)
        summary_row = await ctx.store.latest_summary(scope, "session")
        summary = summary_row["text"] if summary_row else ""

        messages = ctx.prompt.compose(
            PromptContext(
                persona=ctx.persona,
                summary=summary,
                facts=facts,
                self_state=self_state,
                emotion=emotion,
                diary=diary_text,
                history=[],
            )
        )
        messages[0]["content"] += (
            "\n\n现在轮到你主动开口。对方有一阵没说话了。"
            "\n" + INTENT_HINTS[intent]
            + "\n说 1~2 句自然的话，不要问「在吗」，不要连续追问。"
        )

        text, _ = await ctx.runtime.run(messages, scope=scope)
        return (text or "").strip()

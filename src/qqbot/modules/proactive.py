from __future__ import annotations

import asyncio
import datetime as dt
import logging
import random
import time

from ..core.reply_style import segment_interval, split_reply
from ..prompt.composer import PromptContext

log = logging.getLogger(__name__)

# 每种都要带「想找他」的底色，不能只是汇报行程
INTENT_HINTS = {
    "morning": "现在是早上。跟他说句早安，顺带让他知道醒来就想到他了。",
    "night": "现在是晚上。跟他说句晚安，语气软一点，像舍不得挂。",
    "miss": "对方好几个小时没说话了。说一句你想他，别催、别怨、别问「在不在」。",
    "share": "说一件你刚想起的事，落点是「想跟你讲」。",
    "wander": "说一句你此刻看到的小事，然后自然把话头递给他。",
    "idle_chat": "没什么正事，就是忽然想他了，说一句。",
}

# 平时随机挑的几种，避免每次都走同一个套路
CASUAL_INTENTS = ("share", "wander", "idle_chat")


class ProactiveModule:
    """主动开口：空闲阈值 + 最小间隔 + 静默时段 + 概率。不限条数。"""

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
        log.info(
            "proactive 模块已启用（每 %s 分钟检查，空闲 %s~%s 分钟可能开口）",
            settings.proactive_check_minutes,
            settings.proactive_idle_min,
            settings.proactive_idle_max,
        )

    async def tick(self) -> None:
        ctx = self.ctx
        settings = ctx.settings
        now = time.time()
        scope = f"private:{settings.owner_qq}"

        # 服务刚启动时内存里的计时是 0，从库里把最后一条用户消息捞回来
        # 否则 idle 恒为 0，主动消息永远等不到阈值
        if not ctx.last_user_at:
            ctx.last_user_at = await ctx.store.last_message_ts(scope, "user")

        hour = dt.datetime.now().hour
        if settings.proactive_quiet_start <= hour < settings.proactive_quiet_end:
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

        cooldown = int(getattr(settings, "proactive_cooldown_seconds", 300))
        if ctx.last_user_at and now - ctx.last_user_at < cooldown:
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

        today = dt.date.today().isoformat()
        await ctx.store.add_message(
            scope, settings.bot_qq, "assistant", text, source="proactive"
        )
        await ctx.store.set_setting("last_proactive_at", str(now))
        await ctx.store.set_setting(
            f"proactive_count:{today}", str(await self._today_count() + 1)
        )
        if ctx.emotion is not None:
            await ctx.emotion.on_proactive_sent(text)
        log.info("已主动开口（%s）：%s", intent, text[:40])

    async def _today_count(self) -> int:
        today = dt.date.today().isoformat()
        return int(
            await self.ctx.store.get_setting(f"proactive_count:{today}", "0") or 0
        )

    def _pick_intent(self, hour: int, idle: float, settings) -> str:
        if 6 <= hour < 9:
            return "morning"
        if 22 <= hour < 24:
            return "night"
        if idle >= settings.proactive_miss_hours * 3600:
            return "miss"
        return random.choice(CASUAL_INTENTS)

    async def _generate(self, intent: str) -> str:
        ctx = self.ctx
        settings = ctx.settings
        scope = f"private:{settings.owner_qq}"

        self_state = await ctx.self_memory.get_state()
        emotion = await ctx.emotion.prompt_text() if ctx.emotion is not None else ""
        facts = await ctx.retriever.recall(scope, INTENT_HINTS[intent], 3)
        summary_row = await ctx.store.latest_summary(scope, "session")
        summary = summary_row["text"] if summary_row else ""

        plan_text = ""
        try:
            from ..memory.plan import describe, today_plan

            plan_text = describe(await today_plan(ctx.store))
        except Exception:
            log.warning("读取当天日程失败（主动消息）", exc_info=True)

        messages = ctx.prompt.compose(
            PromptContext(
                persona=ctx.persona,
                summary=summary,
                facts=facts,
                self_state=self_state,
                emotion=emotion,
                plan=plan_text,
                history=[],
            )
        )
        messages[0]["content"] += (
            "\n\n现在轮到你主动找他说话。"
            "\n" + INTENT_HINTS[intent]
            + "\n\n要求："
            "\n- 短。一句话，最多两句，三十个字以内。"
            "\n- 要能听出来你是想找他聊，不是单纯汇报你在干嘛。"
            "\n- 可以带一句你现在在哪、刚做什么，但落点要是他。"
            "\n- 别问「在吗」，别连发好几条，也别解释为什么要找他。"
        )

        text, _ = await ctx.runtime.run(messages, scope=scope)
        return (text or "").strip()

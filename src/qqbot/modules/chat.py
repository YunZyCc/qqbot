from __future__ import annotations

import asyncio
import logging

from ..core.events import Event, EventKind
from ..core.session import SessionContext, session_from_event
from ..core.splitter import split_message
from ..memory.episodes import maybe_create_episode
from ..memory.facts import extract_facts, has_signal
from ..memory.summary import maybe_update_summary
from ..prompt.composer import PromptContext

log = logging.getLogger(__name__)


class ChatModule:
    """单用户私聊对话模块，行为与改造前一致。"""

    name = "chat"

    def setup(self, ctx) -> None:
        self.ctx = ctx
        ctx.bus.on(EventKind.MESSAGE, self.handle, priority=100, name="chat")

    async def handle(self, ev: Event) -> None:
        ctx = self.ctx
        if not await ctx.policy.should_respond(ev):
            if ev.kind is EventKind.MESSAGE:
                log.info("忽略消息 sender=%s type=%s", ev.sender_id, ev.message_type)
            return

        if not ev.text:
            return

        key = session_from_event(ev)
        if key is None:
            return

        sctx = ctx.sessions.get(key)
        async with sctx.lock:
            await self._reply(ev, sctx)

    async def _reply(self, ev: Event, sctx: SessionContext) -> None:
        ctx = self.ctx
        settings = ctx.settings
        scope = ctx.policy.memory_scope(ev)
        sender = ev.sender_id or settings.owner_qq

        log.info("收到消息（scope=%s）：%s", scope, ev.text[:50])
        await ctx.store.add_message(scope, sender, "user", ev.text, ev.message_id)

        history = await ctx.store.recent_messages(scope, settings.max_context_messages)
        facts = await ctx.retriever.recall(scope, ev.text, settings.retrieve_top_k)

        relations = await ctx.contacts.relations_of(sender)
        self_state = await ctx.self_memory.get_state()

        rolling = await ctx.store.latest_summary(scope, "rolling")
        session = await ctx.store.latest_summary(scope, "session")
        summary_parts = []
        if rolling:
            summary_parts.append("长期印象：" + rolling["text"])
        if session:
            summary_parts.append("最近：" + session["text"])
        summary = "\n".join(summary_parts)

        diaries = await ctx.store.recent_diaries(settings.diary_prompt_days)
        diary_text = "\n\n".join(f"{d['date']}：{d['text'][:200]}" for d in diaries)

        messages = ctx.prompt.compose(
            PromptContext(
                persona=ctx.persona,
                summary=summary,
                facts=facts,
                relations=relations,
                self_state=self_state,
                diary=diary_text,
                history=history,
            )
        )
        reply_text, _ = await ctx.runtime.run(messages, scope=scope)
        reply_text = (reply_text or "").strip() or "……我卡了一下，再说一遍？"

        parts = split_message(reply_text, settings.reply_max_chars)
        for part in parts:
            try:
                await ctx.api.send_private_msg(sender, part)
            except Exception:
                log.exception("发送消息失败")
                break

        await ctx.store.add_message(scope, settings.bot_qq, "assistant", reply_text)
        sctx.turns += 1
        log.info("已回复 %s 段，共 %s 字", len(parts), len(reply_text))

        # 信号词命中立即抽；否则每 N 轮兜底
        if has_signal(ev.text) or sctx.turns % settings.facts_every == 0:
            recent = await ctx.store.recent_messages(scope, 8)
            asyncio.create_task(
                extract_facts(
                    ctx.store,
                    ctx.llm,
                    scope,
                    recent,
                    ev.message_id,
                    vector=ctx.vector,
                )
            )
        asyncio.create_task(
            maybe_update_summary(
                ctx.store,
                ctx.llm,
                scope,
                settings.summary_every,
                settings.summary_token_budget,
            )
        )
        asyncio.create_task(
            maybe_create_episode(ctx.store, ctx.llm, scope, settings.episode_every)
        )

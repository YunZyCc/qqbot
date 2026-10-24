from __future__ import annotations

import asyncio
import logging

from ..core.events import Event, EventKind
from ..core.session import SessionContext, session_from_event
from ..core.splitter import split_message
from ..memory.facts import extract_facts
from ..memory.retrieve import retrieve
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
        facts = retrieve(ev.text, await ctx.store.active_facts(scope), settings.retrieve_top_k)
        summary_row = await ctx.store.latest_summary(scope)
        summary = summary_row["text"] if summary_row else ""

        messages = ctx.prompt.compose(
            PromptContext(
                persona=ctx.persona,
                summary=summary,
                facts=facts,
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

        if sctx.turns % settings.facts_every == 0:
            recent = await ctx.store.recent_messages(scope, 12)
            asyncio.create_task(
                extract_facts(ctx.store, ctx.llm, scope, recent, ev.message_id)
            )
        asyncio.create_task(
            maybe_update_summary(ctx.store, ctx.llm, scope, settings.summary_every)
        )

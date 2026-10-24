from __future__ import annotations

import asyncio
import datetime as dt
import logging
import random
import re
import time

from ..core.events import Event, EventKind
from ..core.message import image_segments, to_user_text
from ..core.reply_style import reply_delay, segment_interval, split_reply
from ..core.session import SessionContext, session_from_event
from ..memory.episodes import maybe_create_episode
from ..memory.facts import extract_facts, has_signal
from ..memory.summary import maybe_update_summary
from ..prompt.composer import PromptContext

log = logging.getLogger(__name__)

# 只有「祈使句式」的要图才 100% 触发，避免「表情包好可爱」也发
_WANTS_STICKER = re.compile(r"(发|来|给|整|上|要)\s*[个张条套]?\s*(表情|表情包|图)")
_WANTS_AGAIN = re.compile(r"再(发|来)一?[个张条]")


class ChatModule:
    """私聊对话：表情可识别、多段回复、思考延迟。"""

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

        user_text = ev.text or to_user_text(ev.segments)
        scope = ctx.policy.memory_scope(ev)
        image_parts = await self._describe_images(ev, scope)
        if image_parts:
            user_text = (user_text + "".join(image_parts)).strip()
        if not user_text:
            return

        ctx.last_user_at = time.time()

        key = session_from_event(ev)
        if key is None:
            return

        sctx = ctx.sessions.get(key)
        async with sctx.lock:
            await self._reply(ev, sctx, user_text)

    async def _describe_images(self, ev: Event, scope: str) -> list[str]:
        ctx = self.ctx
        if ctx.vision is None or ctx.images is None:
            return []
        parts: list[str] = []
        for seg in image_segments(ev.segments)[:2]:
            data = seg.get("data") or {}
            fetched = await ctx.images.fetch(data.get("url"), data.get("file"))
            if not fetched:
                parts.append("[图片]")
                continue
            raw, mime = fetched
            digest, path = ctx.images.save(raw, mime)
            description = ""
            try:
                description = await ctx.vision.describe(raw, mime)
            except Exception:
                log.warning("图片描述失败", exc_info=True)
            if description:
                await ctx.store.add_image_ref(
                    scope, ev.message_id, digest, mime, str(path), description
                )
                parts.append(f"[图片:{description}]")
            else:
                parts.append("[图片]")
        return parts

    async def _reply(self, ev: Event, sctx: SessionContext, user_text: str) -> None:
        ctx = self.ctx
        settings = ctx.settings
        scope = ctx.policy.memory_scope(ev)
        sender = ev.sender_id or settings.owner_qq

        log.info("收到消息（scope=%s）：%s", scope, user_text[:50])
        await ctx.store.add_message(
            scope, sender, "user", user_text, ev.message_id, source="user"
        )

        if ctx.emotion is not None:
            await ctx.emotion.on_user_message(user_text)

        history = await ctx.store.recent_messages(scope, settings.max_context_messages)
        facts = await ctx.retriever.recall(scope, user_text, settings.retrieve_top_k)

        relations = await ctx.contacts.relations_of(sender)
        self_state = await ctx.self_memory.get_state()
        emotion_text = (
            await ctx.emotion.prompt_text() if ctx.emotion is not None else ""
        )

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

        recent_images = await ctx.store.recent_images(scope, 3)
        images_text = "\n".join(
            f"- {img['description']}（hash={img['sha256'][:12]}）" for img in recent_images
        )

        tools_hint = ""
        kit = getattr(ctx, "sticker_kit", None)
        if kit is not None and kit.emotions:
            tools_hint = (
                "可用表情情绪：" + "、".join(kit.emotions) + "。"
                "想发表情包时调用 send_sticker，传情绪或场景词。"
            )

        messages = ctx.prompt.compose(
            PromptContext(
                persona=ctx.persona,
                summary=summary,
                facts=facts,
                relations=relations,
                self_state=self_state,
                emotion=emotion_text,
                diary=diary_text,
                images=images_text,
                tools_hint=tools_hint,
                history=history,
            )
        )
        reply_text, _ = await ctx.runtime.run(messages, scope=scope)
        reply_text = (reply_text or "").strip() or "……我卡了一下，再说一遍？"

        if settings.reply_delay_enabled:
            await asyncio.sleep(reply_delay(settings))

        parts = split_reply(reply_text, settings.reply_segments_max, settings.reply_max_chars)
        for index, part in enumerate(parts):
            if index > 0 and settings.reply_delay_enabled:
                await asyncio.sleep(segment_interval(settings))
            try:
                await ctx.api.send_private_msg(sender, part)
            except Exception:
                log.exception("发送消息失败")
                break

        await ctx.store.add_message(
            scope, settings.bot_qq, "assistant", reply_text, source="reply"
        )
        sctx.turns += 1
        log.info("已回复 %s 段，共 %s 字", len(parts), len(reply_text))

        await self._maybe_auto_sticker(sender, user_text, reply_text, sctx)

        # 信号词命中立即抽；否则每 N 轮兜底
        if has_signal(user_text) or sctx.turns % settings.facts_every == 0:
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

    async def _maybe_auto_sticker(
        self, sender: int, user_text: str, reply_text: str, sctx: SessionContext
    ) -> None:
        """显式要图时必发；否则按概率补一张，带冷却和每日上限。"""
        ctx = self.ctx
        settings = ctx.settings
        if not settings.sticker_enabled or ctx.stickers is None:
            return

        # 模型已经发过表情包就不再补
        if "send_sticker" in getattr(ctx.runtime, "last_tools", []):
            return

        # 冷却：两次表情包之间至少隔若干轮
        if sctx.turns - sctx.last_sticker_turn < settings.sticker_min_turns_gap:
            return

        wants = bool(_WANTS_STICKER.search(user_text)) or bool(_WANTS_AGAIN.search(user_text))
        if not wants and random.random() >= settings.sticker_auto_rate:
            return

        today = dt.date.today().isoformat()
        count = int(await ctx.store.get_setting(f"sticker_count:{today}", "0") or 0)
        if count >= settings.sticker_daily_max:
            return

        query = (reply_text or user_text)[:40]
        result = await ctx.tools.run("send_sticker", {"query": query})
        if result.startswith("已发送"):
            sctx.last_sticker_turn = sctx.turns
            await ctx.store.set_setting(f"sticker_count:{today}", str(count + 1))
            log.info("自动表情包：%s", result)

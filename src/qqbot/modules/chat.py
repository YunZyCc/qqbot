from __future__ import annotations

import asyncio
import datetime as dt
import logging
import random
import re
import time

from ..core.events import Event, EventKind
from ..core.message import image_segments, to_user_text
from ..core.reply_style import (
    pick_segment_count,
    reply_delay,
    segment_interval,
    split_reply,
)
from ..core.session import SessionContext, session_from_event
from ..memory.context import current_scope
from ..memory.episodes import maybe_create_episode
from ..memory.facts import extract_facts, has_signal
from ..memory.growth import active_traits, collect_signals
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
        if ev.is_group:
            await self._handle_group(ev)
            return

        if not await ctx.policy.should_respond(ev):
            if ev.kind is EventKind.MESSAGE:
                log.info("忽略消息 sender=%s type=%s", ev.sender_id, ev.message_type)
            return

        # 不要用 ev.text 兜底：它只提取纯文本，会把表情丢掉。to_user_text 会保留 [表情:xx]
        user_text = to_user_text(ev.segments) or ev.text
        scope = ctx.policy.memory_scope(ev)
        image_parts = await self._describe_images(ev, scope)
        if image_parts:
            user_text = _attach_image_text(user_text, image_parts)
        if not user_text:
            return

        ctx.last_user_at = time.time()

        key = session_from_event(ev)
        if key is None:
            return

        sctx = ctx.sessions.get(key)
        async with sctx.lock:
            await self._reply(ev, sctx, user_text)

    # ---------- 群聊 ----------

    async def _handle_group(self, ev: Event) -> None:
        """群消息：先记录，再决定回不回。记录是必须的，她得知道群里聊过什么。"""
        ctx = self.ctx
        gid = ev.group_id
        if not gid:
            return
        if not ctx.policy.group_allowed(gid):
            log.info("群消息 group=%s 不在白名单，已忽略", gid)
            return

        scope = f"group:{gid}"
        # 不要用 ev.text 兜底：它只提取纯文本，会把表情丢掉。to_user_text 会保留 [表情:xx]
        user_text = to_user_text(ev.segments) or ev.text
        image_parts = await self._describe_images(ev, scope)
        if image_parts:
            user_text = _attach_image_text(user_text, image_parts)
        if not user_text:
            return

        await ctx.store.touch_group_member(
            gid, ev.sender_id or 0, ev.sender_name, ev.sender_card
        )
        speaker = ev.sender_card or ev.sender_name or str(ev.sender_id or "")
        stored = f"{speaker}：{user_text}" if speaker else user_text
        await ctx.store.add_message(
            scope, ev.sender_id or 0, "user", stored, ev.message_id, source="group"
        )

        ctx.last_user_at = time.time()
        if not await self._should_reply_in_group(ev, user_text):
            return

        key = session_from_event(ev)
        if key is None:
            return
        sctx = ctx.sessions.get(key)
        async with sctx.lock:
            await self._reply(ev, sctx, user_text, store_user_message=False)
        await self._open_active_window(gid)

    async def _should_reply_in_group(self, ev: Event, user_text: str) -> bool:
        """四级触发：@ > 叫名字 > 活跃期 > 概率。"""
        ctx = self.ctx
        settings = ctx.settings
        gid = ev.group_id or 0

        if ctx.policy.is_at_bot(ev):
            return True

        for name in settings.group_trigger_name_list:
            if name and name in user_text:
                return True

        if await self._in_active_window(gid):
            return True

        if len(user_text.strip()) < settings.group_min_chars:
            return False
        if await self._in_cooldown(gid):
            return False
        return random.random() < settings.group_reply_chance

    async def _in_active_window(self, gid: int) -> bool:
        until = float(
            await self.ctx.store.get_setting(f"group_active_until:{gid}", "0") or 0
        )
        return time.time() < until

    async def _in_cooldown(self, gid: int) -> bool:
        last = float(
            await self.ctx.store.get_setting(f"group_last_reply:{gid}", "0") or 0
        )
        return time.time() - last < self.ctx.settings.group_reply_cooldown

    async def _open_active_window(self, gid: int) -> None:
        """回过了就继续聊：这段时间内群里说话她都接。"""
        settings = self.ctx.settings
        now = time.time()
        await self.ctx.store.set_setting(
            f"group_active_until:{gid}", str(now + settings.group_active_minutes * 60)
        )
        await self.ctx.store.set_setting(f"group_last_reply:{gid}", str(now))

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
                # 表情包图片顺手收进图库，以后她也能拿出来用
                if ctx.stickers is not None and str(data.get("sub_type") or "") == "1":
                    await ctx.stickers.import_from_image(
                        raw, mime, description, digest
                    )
                parts.append(f"[图片:{description}]")
            else:
                parts.append("[图片]")
        return parts

    async def _reply(
        self,
        ev: Event,
        sctx: SessionContext,
        user_text: str,
        store_user_message: bool = True,
    ) -> None:
        ctx = self.ctx
        settings = ctx.settings
        scope = ctx.policy.memory_scope(ev)
        sender = ev.sender_id or settings.owner_qq

        log.info("收到消息（scope=%s）：%s", scope, user_text[:50])
        if store_user_message:
            await ctx.store.add_message(
                scope, sender, "user", user_text, ev.message_id, source="user"
            )

        if ctx.emotion is not None:
            await ctx.emotion.on_user_message(user_text)

        # 群消息更碎，回放条数比私聊多
        context_limit = (
            settings.group_max_context
            if scope.startswith("group:")
            else settings.max_context_messages
        )
        history = await ctx.store.recent_messages(scope, context_limit)
        # 先按权重抽这一轮发几条，写进 prompt 让模型按量输出
        slots = pick_segment_count(
            settings.reply_segment_weight_list, settings.reply_segments_max
        )
        messages = await build_reply_messages(
            ctx,
            scope,
            sender,
            user_text,
            history,
            reply_slots=slots,
            reply_slot_chars=settings.reply_segment_max_chars,
        )
        reply_text, _ = await ctx.runtime.run(messages, scope=scope)
        reply_text = (reply_text or "").strip() or "……我卡了一下，再说一遍？"

        if settings.reply_delay_enabled:
            await asyncio.sleep(reply_delay(settings))

        diary_texts = [
            row["text"] for row in await ctx.store.recent_diaries(3)
        ]
        verbatim = _looks_verbatim(reply_text, diary_texts)
        if verbatim:
            log.info("检测到原文输出（日记/代码），不按字数切分")
        parts = split_reply(
            reply_text,
            settings.reply_segments_max,
            settings.reply_segment_max_chars,
            settings.reply_segment_weight_list,
            verbatim=verbatim,
            target_segments=slots,
        )
        for index, part in enumerate(parts):
            if index > 0 and settings.reply_delay_enabled:
                await asyncio.sleep(segment_interval(settings))
            try:
                if ev.is_group and ev.group_id:
                    await ctx.api.send_group_msg(ev.group_id, part)
                else:
                    await ctx.api.send_private_msg(sender, part)
            except Exception:
                log.exception("发送消息失败")
                break

        await ctx.store.add_message(
            scope, settings.bot_qq, "assistant", reply_text, source="reply"
        )
        sctx.turns += 1
        log.info("已回复 %s 段，共 %s 字", len(parts), len(reply_text))

        await self._maybe_auto_sticker(sender, user_text, reply_text, sctx, scope)

        # 信号词命中立即抽；否则每 N 轮兜底。只抽上次之后的新消息，避免重复抽取浪费 token
        if has_signal(user_text) or sctx.turns % settings.facts_every == 0:
            since = float(await ctx.store.get_setting(f"facts_since:{scope}", "0") or 0)
            pending = await ctx.store.messages_after(scope, since)
            recent = pending[-20:]
            if not recent:
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
                vector=ctx.vector,
            )
        )
        asyncio.create_task(
            maybe_create_episode(
                ctx.store, ctx.llm, scope, settings.episode_every, vector=ctx.vector
            )
        )

        # 人格成长：低频观察，攒够证据才会真正改变她
        if settings.growth_enabled and sctx.turns % settings.growth_every == 0:
            recent_growth = await ctx.store.recent_messages(scope, 20)
            asyncio.create_task(
                collect_signals(
                    ctx.store,
                    ctx.llm,
                    recent_growth,
                    promote_after=settings.growth_promote_after,
                    vector=ctx.vector,
                )
            )

    async def _maybe_auto_sticker(
        self,
        sender: int,
        user_text: str,
        reply_text: str,
        sctx: SessionContext,
        scope: str = "",
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
        # 工具靠 current_scope 判断发私聊还是发群，这里要显式带上
        token = current_scope.set(scope) if scope else None
        try:
            result = await ctx.tools.run("send_sticker", {"query": query})
        finally:
            if token is not None:
                current_scope.reset(token)
        if result.startswith("已发送"):
            sctx.last_sticker_turn = sctx.turns
            await ctx.store.set_setting(f"sticker_count:{today}", str(count + 1))
            log.info("自动表情包：%s", result)


def _attach_image_text(user_text: str, parts: list[str]) -> str:
    """把视觉描述填回 [图片] 占位符，没有占位就追加在后面。"""
    text = user_text
    for part in parts:
        if "[图片]" in text:
            text = text.replace("[图片]", part, 1)
        else:
            text = (text + part).strip()
    return text.strip()


async def build_reply_messages(
    ctx,
    scope: str,
    sender: int,
    user_text: str,
    history: list[dict],
    *,
    reply_slots: int = 0,
    reply_slot_chars: int = 20,
) -> list[dict]:
    """拼这次回复要发的完整 prompt；print_prompt 脚本也走这里，保证调试看到的就是真实内容。"""
    settings = ctx.settings

    recalled = await ctx.retriever.recall_all(scope, user_text, settings.retrieve_top_k)
    facts = recalled["facts"]
    episodes = recalled["episodes"]

    # focus（最近在忙什么）有时效，按 TTL 过滤后补进去
    cutoff = time.time() - settings.focus_ttl_days * 86400
    seen = {f["id"] for f in facts}
    for row in await ctx.store.recent_facts(scope, "focus", 5):
        if float(row.get("updated_at") or 0) >= cutoff and row["id"] not in seen:
            facts.append(row)

    relations = await ctx.contacts.relations_of(sender)
    self_state = await ctx.self_memory.get_state()
    emotion_text = await ctx.emotion.prompt_text() if ctx.emotion is not None else ""
    evolution = (
        await active_traits(ctx.store) if settings.growth_enabled else []
    )
    chatroom = await _build_chatroom(ctx, scope, sender)

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

    hints: list[str] = []
    kit = getattr(ctx, "sticker_kit", None)
    if kit is not None and kit.emotions:
        hints.append(
            "可用表情情绪：" + "、".join(kit.emotions) + "。"
            "想发表情包时调用 send_sticker，传情绪或场景词。"
        )
    search = getattr(ctx, "search", None)
    if search is not None and getattr(search, "available", False):
        hints.append(
            "你现在**有**联网能力：凡是实时信息（价格、新闻、比分、天气、最近发生的事）"
            "或你没把握的事实，先调用 web_search 查完再回答，不要说「我没联网」「查不了」。"
            "如果你在对话历史里说过自己不能联网，那是升级前的旧状态，别当真。"
            "对方发链接让你看，用 web_fetch 抓正文。"
        )
    if getattr(settings, "qzone_enabled", False):
        hints.append(
            "想发 QQ 空间说说就调用 post_qzone 工具，内容直接写在参数里一次发出去。"
            "想换个性签名就调用 update_signature。两个都是想用就用，没有次数限制。"
            "对方让你发说说时，必须真的调用，不能嘴上答应或者先念内容。"
        )
    tools_hint = "\n".join(hints)

    return ctx.prompt.compose(
        PromptContext(
            persona=ctx.persona,
            evolution=evolution,
            chatroom=chatroom,
            summary=summary,
            facts=facts,
            episodes=episodes,
            relations=relations,
            self_state=self_state,
            emotion=emotion_text,
            diary=diary_text,
            images=images_text,
            tools_hint=tools_hint,
            reply_slots=reply_slots,
            reply_slot_chars=reply_slot_chars,
            history=history,
        )
    )


def _looks_verbatim(reply_text: str, diary_texts: list[str]) -> bool:
    """念日记 / 贴代码这类原文不切碎，整条发出去。"""
    if "```" in reply_text:
        return True
    if not diary_texts:
        return False
    joined = "\n".join(diary_texts)
    window = 20
    if len(reply_text) < window:
        return False
    for index in range(len(reply_text) - window + 1):
        if reply_text[index:index + window] in joined:
            return True
    return False


async def _build_chatroom(ctx, scope: str, sender: int) -> dict | None:
    """群聊时组装「当前在哪个群、谁在说话、群里认识谁」；私聊返回 None。"""
    if not scope.startswith("group:"):
        return None
    try:
        group_id = int(scope.split(":", 1)[1])
    except (IndexError, ValueError):
        return None

    settings = ctx.settings
    members = await ctx.store.list_group_members(group_id, settings.group_member_limit)
    speaker_name = str(sender)
    for member in members:
        if int(member["qq"]) == int(sender):
            speaker_name = member["card"] or member["nickname"] or str(sender)
            break

    is_owner = False
    policy = getattr(ctx, "policy", None)
    if policy is not None and hasattr(policy, "is_owner"):
        is_owner = policy.is_owner(sender)

    return {
        "group_id": group_id,
        "speaker_qq": sender,
        "speaker_name": speaker_name,
        "is_owner": is_owner,
        "members": members,
    }

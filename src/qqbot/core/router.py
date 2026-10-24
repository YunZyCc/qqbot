from __future__ import annotations

import asyncio
import logging

from ..config import get_settings
from ..llm.client import ChatClient
from ..llm.prompt import build_messages
from ..memory.facts import extract_facts
from ..memory.retrieve import retrieve
from ..memory.store import Store
from ..memory.summary import maybe_update_summary
from ..onebot.api import OneBotAPI
from ..onebot.events import OneBotEvent, extract_text
from .splitter import split_message

log = logging.getLogger(__name__)


class Bot:
    def __init__(self, api: OneBotAPI, chat: ChatClient, store: Store, persona: str) -> None:
        self.api = api
        self.chat = chat
        self.store = store
        self.persona = persona
        self.lock = asyncio.Lock()
        self.turns = 0

    async def handle_event(self, raw: dict) -> None:
        try:
            ev = OneBotEvent.model_validate(raw)
        except Exception:
            log.debug("事件解析失败，已忽略")
            return

        if ev.post_type != "message" or ev.message_type != "private":
            return

        settings = get_settings()
        if ev.user_id != settings.owner_qq:
            log.info("忽略非白名单用户 %s", ev.user_id)
            return

        text = extract_text(ev.message)
        if not text:
            return

        async with self.lock:
            await self._reply(text, ev.message_id)

    async def _reply(self, text: str, message_id: int | None) -> None:
        settings = get_settings()
        log.info("收到消息：%s", text[:50])
        await self.store.add_message(settings.owner_qq, "user", text, message_id)

        history = await self.store.recent_messages(settings.max_context_messages)
        facts = retrieve(text, await self.store.active_facts(), settings.retrieve_top_k)
        summary_row = await self.store.latest_summary()
        summary = summary_row["text"] if summary_row else ""

        messages = build_messages(self.persona, summary, facts, history)
        reply_text, _ = await self.chat.complete(messages)
        reply_text = (reply_text or "").strip() or "……我卡了一下，再说一遍？"

        parts = split_message(reply_text, settings.reply_max_chars)
        for part in parts:
            try:
                await self.api.send_private_msg(settings.owner_qq, part)
            except Exception:
                log.exception("发送消息失败")
                break

        await self.store.add_message(settings.bot_qq, "assistant", reply_text)
        self.turns += 1
        log.info("已回复 %s 段，共 %s 字", len(parts), len(reply_text))

        # 记忆维护不阻塞回复
        if self.turns % settings.facts_every == 0:
            recent = await self.store.recent_messages(12)
            asyncio.create_task(extract_facts(self.store, self.chat, recent, message_id))
        asyncio.create_task(maybe_update_summary(self.store, self.chat, settings.summary_every))

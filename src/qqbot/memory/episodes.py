from __future__ import annotations

import logging
import time

from ..llm.client import ChatClient
from .store import Store

log = logging.getLogger(__name__)

EPISODE_PROMPT = """把下面这段对话压缩成一段「事件记录」，用于长期记忆。
要求：
- 客观描述：谁、做了什么、聊到了什么、结果如何。
- 100~200 字，不要评价，不要建议，不要编造。
- 如果这段对话没有值得长期记住的事件，只输出 NONE。
只输出正文。"""


async def maybe_create_episode(
    store: Store, chat: ChatClient, scope: str, every: int
) -> int:
    """每积累 every 条消息，生成一段事件记录。返回 1 表示写入了一条。"""
    since = await store.latest_episode_end(scope)
    messages = await store.messages_after(scope, since)
    if len(messages) < every:
        return 0

    lines = [f"{m['role']}: {m['content']}" for m in messages]
    try:
        text, _ = await chat.complete(
            [
                {"role": "system", "content": EPISODE_PROMPT},
                {"role": "user", "content": "\n".join(lines)[-6000:]},
            ],
            max_tokens=400,
            temperature=0.3,
        )
    except Exception:
        log.exception("生成 episode 失败（scope=%s）", scope)
        return 0

    text = (text or "").strip()
    if not text or text.upper() == "NONE":
        log.info("本期没有值得记录的事件（scope=%s）", scope)
        return 0

    end_ts = float(messages[-1].get("ts") or time.time())
    start_ts = since or float(messages[0].get("ts") or end_ts)
    await store.add_episode(scope, start_ts, end_ts, text[:800])
    log.info("已写入事件记录（scope=%s，%s 字）", scope, len(text))
    return 1

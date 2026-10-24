from __future__ import annotations

import logging
import time

from ..llm.client import ChatClient
from .store import Store

log = logging.getLogger(__name__)

SUMMARY_PROMPT = """你在维护一段长期对话的记忆摘要。
要求：
1. 保留事实：对方说过的重要信息、喜好、经历、承诺、情绪状态。
2. 保留关系状态：熟络程度、最近的相处氛围、未完成的话题。
3. 不要编造，不要评价，不要写建议。
4. 用第三人称，控制在 400 字以内。
只输出摘要正文。"""


async def maybe_update_summary(
    store: Store, chat: ChatClient, scope: str, every: int
) -> None:
    latest = await store.latest_summary(scope)
    since_ts = float(latest["end_ts"]) if latest else 0.0
    new_msgs = await store.messages_after(scope, since_ts)
    if len(new_msgs) < every:
        return

    lines = [f"{m['role']}: {m['content']}" for m in new_msgs]
    previous = latest["text"] if latest else "（无）"
    user_content = f"上一版摘要：\n{previous}\n\n新增对话：\n" + "\n".join(lines)[-6000:]

    try:
        text, _ = await chat.complete(
            [
                {"role": "system", "content": SUMMARY_PROMPT},
                {"role": "user", "content": user_content},
            ],
            max_tokens=700,
            temperature=0.3,
        )
    except Exception:
        log.exception("生成摘要失败")
        return

    text = text.strip()
    if not text:
        return
    version = (int(latest["version"]) + 1) if latest else 1
    end_ts = time.time()
    await store.add_summary(
        scope, start_ts=since_ts, end_ts=end_ts, text=text[:800], version=version
    )
    log.info("摘要已更新到 v%s（scope=%s，%s 字）", version, scope, len(text))

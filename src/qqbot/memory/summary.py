from __future__ import annotations

import logging
import time

from ..llm.client import ChatClient
from .store import Store

log = logging.getLogger(__name__)

SUMMARY_PROMPT = """你在维护一段长期对话的会话摘要。
要求：
1. 保留事实：对方说过的重要信息、喜好、经历、承诺、情绪状态。
2. 保留关系状态：熟络程度、最近的相处氛围、未完成的话题。
3. 不要编造，不要评价，不要写建议。
4. 用第三人称，控制在 400 字以内。
只输出摘要正文。"""

ROLLING_PROMPT = """把「旧长期印象」和「今天的会话摘要」合并成一段新的长期印象。
要求：
- 保留仍然有效的事实和关系状态，淡化一次性的情绪。
- 不要编造，不要评价。
- 600 字以内，只输出正文。"""


async def maybe_update_summary(
    store: Store,
    chat: ChatClient,
    scope: str,
    every: int,
    token_budget: int = 6000,
    vector=None,
) -> bool:
    """三个触发条件任一满足就更新 session 摘要。"""
    latest = await store.latest_summary(scope, "session")
    since_ts = float(latest["end_ts"]) if latest else 0.0
    new_msgs = await store.messages_after(scope, since_ts)
    if not new_msgs:
        return False

    chars = sum(len(str(m.get("content") or "")) for m in new_msgs)
    count_trigger = len(new_msgs) >= every
    size_trigger = chars >= token_budget
    daily_trigger = (time.time() - since_ts) >= 86400 and len(new_msgs) >= 3
    if not (count_trigger or size_trigger or daily_trigger):
        return False

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
        return False

    text = (text or "").strip()
    if not text:
        return False
    version = (int(latest["version"]) + 1) if latest else 1
    end_ts = time.time()
    summary_id = await store.add_summary(
        scope, start_ts=since_ts, end_ts=end_ts, text=text[:800], version=version,
        kind="session",
    )
    if vector is not None and summary_id:
        await vector.upsert(scope, "summary", summary_id, text[:800])
    log.info("session 摘要更新到 v%s（scope=%s，%s 字）", version, scope, len(text))
    return True


async def merge_rolling(store: Store, chat: ChatClient, scope: str) -> bool:
    """把最新 session 摘要合并进 rolling 长期印象（每日跑一次）。"""
    session = await store.latest_summary(scope, "session")
    if session is None:
        return False

    rolling = await store.latest_summary(scope, "rolling")
    # 这份 session 已经合并过就不再合并：启动补跑会重复调用这里，别白花 token
    merged_session = await store.get_setting(f"rolling_session:{scope}", "0")
    if merged_session == str(session["id"]):
        log.info("rolling 摘要已包含最新 session，跳过（scope=%s）", scope)
        return False

    previous = rolling["text"] if rolling else "（无）"
    user_content = (
        f"旧长期印象：\n{previous}\n\n今天的会话摘要：\n{session['text']}"
    )
    try:
        text, _ = await chat.complete(
            [
                {"role": "system", "content": ROLLING_PROMPT},
                {"role": "user", "content": user_content},
            ],
            max_tokens=900,
            temperature=0.3,
        )
    except Exception:
        log.exception("合并 rolling 摘要失败")
        return False

    text = (text or "").strip()
    if not text:
        return False
    version = (int(rolling["version"]) + 1) if rolling else 1
    await store.add_summary(
        scope,
        start_ts=float(session.get("start_ts") or 0.0),
        end_ts=float(session["end_ts"]),
        text=text[:900],
        version=version,
        kind="rolling",
    )
    await store.set_setting(f"rolling_session:{scope}", str(session["id"]))
    log.info("rolling 摘要更新到 v%s（scope=%s）", version, scope)
    return True

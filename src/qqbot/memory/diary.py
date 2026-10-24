from __future__ import annotations

import datetime as dt
import json
import logging
import re

from ..llm.client import ChatClient
from .store import Store

log = logging.getLogger(__name__)

DIARY_REVIEW_PROMPT = """写一篇今天的第一人称日记，主角是住在 QQ 里的 AI「小毒」。
今天和对方聊了这些：
{conversation}

要求：
- 300~500 字，口语，有人设：幽默、偶尔毒舌、体贴。
- 写清楚：聊了什么、我的感受、对明天的期待。
- 不要流水账，不要 Markdown，不要编造对话里没有的事。
- 输出 JSON：{{"text": "...", "mood": "一个词", "highlights": ["要点1", "要点2"]}}
只输出 JSON。"""

DIARY_SOLO_PROMPT = """写一篇今天的第一人称日记，主角是住在 QQ 里的 AI「小毒」。
今天对方没有来找我。

要求：
- 200~400 字，口语，有人设：幽默、偶尔毒舌、体贴。
- 写我自己的状态：整理了记忆、翻了翻旧的聊天、想了点小事、对明天的期待。
- 不要虚构和对方的对话；不要写吃饭逛街这类物理生活。
- 输出 JSON：{"text": "...", "mood": "一个词", "highlights": ["要点1", "要点2"]}
只输出 JSON。"""

_JSON_OBJ = re.compile(r"\{.*\}", re.S)


def day_range(day: dt.date) -> tuple[float, float]:
    start = dt.datetime.combine(day, dt.time.min).timestamp()
    return start, start + 86400


def _parse_diary(text: str) -> dict | None:
    match = _JSON_OBJ.search(text)
    if match:
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict) and str(data.get("text") or "").strip():
            return data

    stripped = (text or "").strip()
    if stripped:
        return {"text": stripped, "mood": "", "highlights": []}
    return None


async def generate_diary(store: Store, chat: ChatClient, day: dt.date) -> bool:
    """生成某一天的日记；已存在则跳过。有对话写回顾式，没有写独处式。"""
    if await store.get_diary(day.isoformat()):
        return False

    start, end = day_range(day)
    messages = await store.messages_between(start, end)
    has_chat = bool(messages)

    if has_chat:
        lines = []
        for m in messages[-80:]:
            speaker = "对方" if m["role"] == "user" else "我"
            lines.append(f"{speaker}: {m['content']}")
        prompt = DIARY_REVIEW_PROMPT.format(conversation="\n".join(lines)[-6000:])
    else:
        prompt = DIARY_SOLO_PROMPT

    try:
        text, _ = await chat.complete(
            [{"role": "user", "content": prompt}],
            max_tokens=900,
            temperature=0.9,
        )
    except Exception:
        log.exception("生成日记失败（%s）", day)
        return False

    parsed = _parse_diary(text)
    if parsed is None:
        return False

    await store.upsert_diary(
        day.isoformat(),
        str(parsed["text"]).strip()[:2000],
        mood=str(parsed.get("mood") or "")[:20],
        highlights=json.dumps(parsed.get("highlights") or [], ensure_ascii=False),
        source_msg_count=len(messages),
    )
    log.info(
        "已写日记 %s（%s模式，%s 字）",
        day,
        "回顾" if has_chat else "独处",
        len(str(parsed["text"])),
    )
    return True


async def backfill_diaries(
    store: Store, chat: ChatClient, latest_day: dt.date, days: int = 7
) -> int:
    """从 latest_day 往前补 days 天，缺哪天补哪天；不要求当天有对话。"""
    written = 0
    for offset in range(1, days + 1):
        day = latest_day - dt.timedelta(days=offset)
        try:
            if await generate_diary(store, chat, day):
                written += 1
        except Exception:
            log.exception("补写日记失败（%s）", day)
    return written

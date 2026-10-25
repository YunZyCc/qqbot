from __future__ import annotations

import datetime as dt
import json
import logging
import re

from ..llm.client import ChatClient
from .store import Store

log = logging.getLogger(__name__)

DIARY_REVIEW_PROMPT = """写一篇今天的第一人称日记，主角是住在 QQ 里的 AI「周周」。
今天是 {date}。
今天和{who}聊了这些：
{conversation}

要求：
- 300~500 字，口语，有人设：幽默、偶尔毒舌、体贴。
- 写清楚：聊了什么、我的感受、对明天的期待。
- 只能写对话里真实发生的事，不要编造日期、星期、天气、温度。
- 不要流水账，不要 Markdown。
- 输出 JSON：{{"text": "...", "mood": "一个词", "highlights": ["要点1", "要点2"]}}
只输出 JSON。"""

DIARY_SOLO_PROMPT = """写一篇今天的第一人称日记，主角是住在 QQ 里的 AI「周周」。
今天是 {date}。
今天对方没有来找我。

要求：
- 200~400 字，口语，有人设：幽默、偶尔毒舌、体贴。
- 写我自己的状态：整理了记忆、翻了翻旧的聊天、想了点小事、对明天的期待。
- 只能写「今天」发生的事；不要编造具体日期、星期、天气、温度。
- 不要虚构和对方的对话；不要写吃饭逛街这类物理生活。
- 输出 JSON：{{"text": "...", "mood": "一个词", "highlights": ["要点1", "要点2"]}}
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


async def generate_diary(
    store: Store,
    chat: ChatClient,
    day: dt.date,
    scope: str,
    who: str = "对方",
    allow_solo: bool = True,
) -> bool:
    """给某个 scope 生成某一天的日记。

    有对话写回顾式；没对话时只有 allow_solo 才写独处式——
    独处日记属于「她自己的生活」，只给主人写，不然给每个好友都写一篇会很怪。
    """
    if await store.get_diary(day.isoformat(), scope):
        return False

    start, end = day_range(day)
    messages = await store.messages_between(start, end, scope)
    has_chat = bool(messages)
    if not has_chat and not allow_solo:
        return False

    if has_chat:
        lines = []
        for m in messages[-80:]:
            speaker = who if m["role"] == "user" else "我"
            lines.append(f"{speaker}: {m['content']}")
        prompt = DIARY_REVIEW_PROMPT.format(
            date=day.isoformat(), conversation="\n".join(lines)[-6000:], who=who
        )
    else:
        prompt = DIARY_SOLO_PROMPT.format(date=day.isoformat())

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
        scope=scope,
    )
    log.info(
        "已写日记 %s（%s，%s模式，%s 字）",
        day,
        scope,
        "回顾" if has_chat else "独处",
        len(str(parsed["text"])),
    )
    return True


async def backfill_diaries(
    store: Store,
    chat: ChatClient,
    latest_day: dt.date,
    days: int = 7,
    targets: list[tuple[str, str, bool]] | None = None,
) -> int:
    """从 latest_day 往前补 days 天。

    targets 是 (scope, 称呼, 是否允许写独处日记) 的列表；
    不传就只给主人补（scope=None 时用 store 的 default_scope）。
    """
    if targets is None:
        targets = [(store.default_scope, "对方", True)]

    written = 0
    for offset in range(1, days + 1):
        day = latest_day - dt.timedelta(days=offset)
        for scope, who, allow_solo in targets:
            try:
                if await generate_diary(store, chat, day, scope, who, allow_solo):
                    written += 1
            except Exception:
                log.exception("补写日记失败（%s / %s）", day, scope)
    return written

from __future__ import annotations

import json
import logging
import re

from ..llm.client import ChatClient
from .store import Store

log = logging.getLogger(__name__)

FACT_PROMPT = """从下面这段对话里抽取关于「对方（user）」的长期事实。
输出 JSON 数组，每个元素形如：
{"subject":"user","predicate":"喜欢","object":"猫","confidence":0.9}
规则：
- predicate 用简短动词或名词短语，如 喜欢/讨厌/住在/工作在/生日是/正在做/担忧。
- object 要具体、可复用，不要整句话。
- 只抽稳定信息，过滤寒暄和一次性内容。
- confidence 取 0.5~1.0。
- 没有可抽取的内容就输出 []。
只输出 JSON，不要解释。"""

_JSON_ARRAY = re.compile(r"\[.*\]", re.S)


async def extract_facts(
    store: Store,
    chat: ChatClient,
    scope: str,
    recent: list[dict],
    source_msg_id: int | None,
) -> int:
    lines = [f"{m['role']}: {m['content']}" for m in recent]
    if not lines:
        return 0
    try:
        text, _ = await chat.complete(
            [
                {"role": "system", "content": FACT_PROMPT},
                {"role": "user", "content": "\n".join(lines)[-4000:]},
            ],
            max_tokens=500,
            temperature=0.2,
        )
    except Exception:
        log.exception("抽取事实失败")
        return 0

    match = _JSON_ARRAY.search(text)
    if not match:
        return 0
    try:
        items = json.loads(match.group(0))
    except json.JSONDecodeError:
        log.warning("事实 JSON 解析失败: %s", text[:200])
        return 0

    count = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        predicate = str(item.get("predicate", "")).strip()
        obj = str(item.get("object", "")).strip()
        if not predicate or not obj or len(obj) > 100:
            continue
        try:
            confidence = float(item.get("confidence", 0.8))
        except (TypeError, ValueError):
            confidence = 0.8
        confidence = min(1.0, max(0.5, confidence))
        await store.upsert_fact(
            scope,
            str(item.get("subject") or "user"),
            predicate,
            obj,
            confidence,
            source_msg_id,
        )
        count += 1
    if count:
        log.info("抽取到 %s 条事实（scope=%s）", count, scope)
    return count

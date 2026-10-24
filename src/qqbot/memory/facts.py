from __future__ import annotations

import json
import logging
import re

from ..llm.client import ChatClient
from .store import Store

log = logging.getLogger(__name__)

# 命中这些词就立即抽取，不等满 6 轮
SIGNAL_WORDS = (
    "喜欢",
    "讨厌",
    "不爱",
    "爱吃",
    "受不了",
    "住在",
    "老家",
    "生日",
    "工作",
    "上班",
    "上学",
    "专业",
    "我妈",
    "我爸",
    "朋友",
    "同事",
    "对象",
    "女朋友",
    "男朋友",
    "猫",
    "狗",
    "答应",
    "说好",
    "打算",
    "计划",
    "下周",
    "明天要",
    "怕",
    "担心",
    "烦",
    "累",
    "难过",
    "开心",
)

# 把口头表达收敛到固定谓词，提高关键词检索命中率
PREDICATE_VOCAB = {
    "喜欢": "喜欢",
    "爱": "喜欢",
    "偏爱": "喜欢",
    "最爱": "喜欢",
    "讨厌": "讨厌",
    "不喜欢": "讨厌",
    "受不了": "讨厌",
    "住在": "住在",
    "住": "住在",
    "老家": "住在",
    "生日": "生日是",
    "在": "在做",
    "正在": "在做",
    "最近在": "在做",
    "怕": "担忧",
    "担心": "担忧",
    "害怕": "担忧",
    "答应": "承诺",
    "说好": "承诺",
    "承诺": "承诺",
    "朋友": "关系",
    "同事": "关系",
    "对象": "关系",
}

FACT_PROMPT = """从下面这段对话里抽取关于「对方（user）」的长期事实。
输出 JSON 数组，每个元素形如：
{"subject":"user","predicate":"喜欢","object":"猫","confidence":0.9}

可以抽取的内容：
- 偏好：喜欢/讨厌的食物、动物、活动
- 经历：住过哪、做过什么、发生过什么
- 关系：家人、朋友、同事、恋人的存在
- 计划与承诺：打算做什么、答应过什么
- 稳定状态：工作、上学、健康、情绪基调

不要抽取：
- 寒暄、天气、一次性闲聊
- 对方的提问本身（除非问题里包含事实）
- 无法复用的整句话

规则：
- predicate 用简短动词或名词短语：喜欢/讨厌/住在/生日是/在做/担忧/承诺/关系。
- object 要具体、可复用，不超过 30 字。
- confidence 取 0.5~1.0；模糊猜测给 0.5~0.6。
- 没有可抽取的内容就输出 []。
只输出 JSON，不要解释。"""

_JSON_ARRAY = re.compile(r"\[.*\]", re.S)
_JSON_OBJECT = re.compile(r"\{[^{}]*\}", re.S)


def has_signal(text: str) -> bool:
    return any(word in text for word in SIGNAL_WORDS)


def normalize_predicate(predicate: str) -> str:
    p = predicate.strip()
    if not p:
        return p
    for key, value in PREDICATE_VOCAB.items():
        if key in p:
            return value
    return p


def _parse_items(text: str) -> list[dict] | None:
    """先按数组解析；失败再逐个对象宽松提取。返回 None 表示完全无法解析。"""
    match = _JSON_ARRAY.search(text)
    if match:
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            data = None
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]

    items: list[dict] = []
    for obj_text in _JSON_OBJECT.findall(text):
        try:
            data = json.loads(obj_text)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            items.append(data)
    return items or None


async def extract_facts(
    store: Store,
    chat: ChatClient,
    scope: str,
    recent: list[dict],
    source_msg_id: int | None,
    vector=None,
) -> int:
    await store.incr_counter(f"facts_attempt:{scope}")

    lines = [f"{m['role']}: {m['content']}" for m in recent]
    if not lines:
        return 0

    response = ""
    items: list[dict] | None = None
    for attempt in range(2):
        try:
            response, _ = await chat.complete(
                [
                    {"role": "system", "content": FACT_PROMPT},
                    {"role": "user", "content": "\n".join(lines)[-4000:]},
                ],
                max_tokens=500,
                temperature=0.2,
            )
        except Exception:
            log.exception("抽取事实调用失败（scope=%s）", scope)
            return 0

        items = _parse_items(response)
        if items is not None:
            break
        log.warning(
            "事实抽取解析失败（第 %s 次，scope=%s）：%s",
            attempt + 1,
            scope,
            response[:200],
        )

    if items is None:
        await store.incr_counter(f"facts_parse_error:{scope}")
        return 0

    if not items:
        await store.incr_counter(f"facts_empty:{scope}")
        log.info("事实抽取为空（scope=%s）", scope)
        return 0

    count = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        predicate = normalize_predicate(str(item.get("predicate", "")))
        obj = str(item.get("object", "")).strip()
        if not predicate or not obj or len(obj) > 100:
            continue
        try:
            confidence = float(item.get("confidence", 0.8))
        except (TypeError, ValueError):
            confidence = 0.8
        confidence = min(1.0, max(0.5, confidence))
        fact_id = await store.upsert_fact(
            scope,
            str(item.get("subject") or "user"),
            predicate,
            obj,
            confidence,
            source_msg_id,
        )
        if vector is not None and fact_id:
            await vector.upsert(scope, "fact", fact_id, f"{predicate}: {obj}")
        count += 1

    if count:
        await store.incr_counter(f"facts_written:{scope}", count)
        log.info("抽取到 %s 条事实（scope=%s）", count, scope)
    else:
        await store.incr_counter(f"facts_empty:{scope}")
        log.info("事实抽取无有效条目（scope=%s）", scope)
    return count

from __future__ import annotations

import json
import logging
import re
import time

from ..llm.client import ChatClient
from .store import Store

log = logging.getLogger(__name__)

# 命中这些词就立即抽取，不等满 N 轮
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
    # 近期关注类
    "正在",
    "最近",
    "在看",
    "在玩",
    "在等",
    "在调试",
    "在忙",
    "比赛",
    "游戏",
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
    "最近": "最近在",
    "在看": "最近在",
    "在玩": "最近在",
    "在等": "最近在",
    "在忙": "最近在",
}

FACT_PROMPT = """从下面这段对话里抽取关于「对方（user）」的记忆，分成两类。

A. kind="fact" —— 稳定、可长期复用的事实
   偏好（喜欢/讨厌什么）、经历（住过哪、做过什么）、关系（家人/朋友/同事）、
   稳定状态（工作、上学、健康）、明确答应过的事。
   例：喜欢猫 / 住在杭州 / 在做前端 / 答应周末一起看比赛

B. kind="focus" —— 近期关注点，几天到几周就过期
   最近在看的、在玩的、在等的、在忙的事，以及这几天的情绪基调。
   例：最近在看 CS 比赛 / 在调试一个 AI 机器人 / 这几天加班很累

输出 JSON 数组，每项形如：
{"kind":"fact","subject":"user","predicate":"喜欢","object":"猫","confidence":0.9}
{"kind":"focus","subject":"user","predicate":"最近在","object":"看 CS 比赛","confidence":0.7}

规则：
- predicate 用短词，优先从这些里选：喜欢/讨厌/住在/生日是/在做/担忧/承诺/关系/最近在。
- object 要具体、可复用，不超过 30 字。
- fact 的 confidence 给 0.7~1.0；focus 给 0.6~0.8。
- 对方表达对「助手」的偏好时（嫌你说话油、不喜欢你的口头禅），subject 填 user，
  object 里用「你」指代助手，例：{"kind":"fact","predicate":"讨厌","object":"你说行吧"}
- 寒暄、纯情绪感叹（「哈哈哈」「好累啊」）、对方对助手的提问本身，不要抽。
- 两人在闲聊天气、吃饭、寒暄，没有可复用信息时就输出 []。
- 宁可少抽，也别把一次性的玩笑话记成事实。
只输出 JSON，不要解释。"""

_JSON_ARRAY = re.compile(r"\[.*\]", re.S)
_JSON_OBJECT = re.compile(r"\{[^{}]*\}", re.S)

VALID_KINDS = ("fact", "focus")


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


def _normalize_kind(value: str, confidence: float) -> str:
    kind = (value or "").strip().lower()
    if kind in VALID_KINDS:
        return kind
    # 没给 kind 时按置信度猜：高置信度当长期事实
    return "fact" if confidence >= 0.75 else "focus"


_OBJECT_REWRITES = (
    ("对方", "你"),
    ("助手", "你"),
    ("机器人", "你"),
    ("小毒", "你"),
)


_QUOTE_PAIRS = (("「", "」"), ("“", "”"), ('"', '"'), ("'", "'"))


def _clean_object(value: str) -> str:
    """把「对方/助手」统一成「你」：站在机器人视角，「讨厌：你说行吧」才读得顺。"""
    obj = value.strip()
    # 只剥掉整句被引号整个包住的情况，别把句中的引号一起吃掉
    for left, right in _QUOTE_PAIRS:
        if len(obj) >= 2 and obj.startswith(left) and obj.endswith(right):
            obj = obj[1:-1].strip()
            break
    for src, dst in _OBJECT_REWRITES:
        obj = obj.replace(src, dst)
    # 「助手」变成「你」之后留下的引号读起来别扭
    for wrapped in ("「你」", "“你”", '"你"'):
        obj = obj.replace(wrapped, "你")
    return obj.strip()


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
                    {"role": "user", "content": "\n".join(lines)[-6000:]},
                ],
                max_tokens=600,
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
        raw_predicate = str(item.get("predicate", "")).strip()
        obj = _clean_object(str(item.get("object", "")))
        if not raw_predicate or not obj or len(obj) > 100:
            continue
        try:
            confidence = float(item.get("confidence", 0.8))
        except (TypeError, ValueError):
            confidence = 0.8
        confidence = min(1.0, max(0.5, confidence))
        kind = _normalize_kind(str(item.get("kind", "")), confidence)
        # focus 不收敛谓词：收敛会把「最近在看比赛」和「最近在调机器人」压成同一条
        predicate = raw_predicate if kind == "focus" else normalize_predicate(raw_predicate)
        fact_id = await store.upsert_fact(
            scope,
            str(item.get("subject") or "user"),
            predicate,
            obj,
            confidence,
            source_msg_id,
            source=kind,
        )
        if vector is not None and fact_id:
            await vector.upsert(scope, "fact", fact_id, f"{predicate}: {obj}")
        count += 1

    await store.set_setting(f"facts_since:{scope}", str(time.time()))

    if count:
        await store.incr_counter(f"facts_written:{scope}", count)
        log.info("抽取到 %s 条记忆（scope=%s）", count, scope)
    else:
        await store.incr_counter(f"facts_empty:{scope}")
        log.info("事实抽取无有效条目（scope=%s）", scope)
    return count

from __future__ import annotations

import random
import re

DEFAULT_WEIGHTS = (30.0, 22.0, 18.0, 18.0, 12.0)


def pick_segment_count(weights: list[float] | None, max_segments: int) -> int:
    """按权重抽要发几条。权重越靠前越大，所以短回复常见、连发少见。"""
    pool = list((weights or DEFAULT_WEIGHTS)[:max_segments])
    total = sum(pool)
    if total <= 0:
        return max_segments
    roll = random.uniform(0, total)
    acc = 0.0
    for index, weight in enumerate(pool):
        acc += weight
        if roll < acc:
            return index + 1
    return len(pool)


_PUNCT_TAIL = "。！？!?，,、；;：:…~～"
# 右边以这些词开头，说明是同一句话的续接，用逗号
_CONNECTIVES = (
    "但", "不过", "可是", "然后", "而且", "所以", "因为", "其实",
    "就是", "还", "也", "再", "又", "才", "就", "而且",
)
# 左边以这些字收尾，说明已经是一个完整的句子，用句号
_SENTENCE_TAILS = ("吧", "了", "呢", "啊", "哦", "嘛", "呀", "哈", "啦")


def _join_pieces(left: str, right: str) -> str:
    """把两条待合并的消息接起来，按语义补标点，避免「A，B」硬连成一句。

    - 左句已经收尾（吧/了/呢…）或是独立的疑问句 → 用句号断开
    - 右边是连接词起头的续接 → 用逗号
    """
    if not left:
        return right
    if not right:
        return left
    if left[-1] in _PUNCT_TAIL:
        return left + right
    if "？" in right or "?" in right:
        return left + "。" + right
    if right.startswith(_CONNECTIVES):
        return left + "，" + right
    if left.endswith(_SENTENCE_TAILS):
        return left + "。" + right
    return left + "，" + right


def _merge_tail(parts: list[str], target: int, limit: int) -> list[str]:
    """把超出目标条数的尾部并进最后一条；并进去太长就宁可多发几条。"""
    if len(parts) <= target:
        return parts
    head = parts[: target - 1]
    merged = ""
    for piece in parts[target - 1:]:
        merged = _join_pieces(merged, piece)
    if len(merged) <= limit:
        return head + [merged]

    out = list(head)
    buffer = ""
    for piece in parts[target - 1:]:
        if not buffer:
            buffer = piece
        elif len(_join_pieces(buffer, piece)) <= limit:
            buffer = _join_pieces(buffer, piece)
        else:
            out.append(buffer)
            buffer = piece
    if buffer:
        out.append(buffer)
    return out


def split_reply(
    text: str,
    max_segments: int = 5,
    segment_max_chars: int = 0,
    weights: list[float] | None = None,
    delimiter: str = "|||",
    verbatim: bool = False,
    target_segments: int = 0,
) -> list[str]:
    """把 LLM 输出拆成 1~5 条消息。

    条数由权重决定（30,22,18,18,12）：一条最常见，五条连发最少见。
    segment_max_chars <= 0 表示单条不限字数，只按分隔符拆。
    verbatim=True 用于「念日记 / 贴代码」这类原文，同样不切。
    """
    from .splitter import split_message

    text = (text or "").strip()
    if not text:
        return []

    parts = [p.strip() for p in text.split(delimiter) if p.strip()]
    if not parts:
        parts = [text]

    # 原文输出：绝不切碎，按原样分段
    if verbatim:
        return parts[:max_segments] if parts else [text]

    # 模型没按 ||| 输出时，按句末标点切，模拟连发
    if len(parts) == 1 and max_segments > 1:
        sentences = [s.strip() for s in re.split(r"(?<=[。！？!?])", parts[0]) if s.strip()]
        sentences = [s for s in sentences if len(s) >= 2]
        if 1 < len(sentences) <= max_segments:
            parts = sentences

    # 单条限长时才切；不限长就直接用原段
    if segment_max_chars > 0:
        expanded: list[str] = []
        for part in parts:
            expanded.extend(split_message(part, segment_max_chars))
        merge_limit = segment_max_chars
    else:
        expanded = list(parts)
        merge_limit = 10_000

    # 条数：外部抽好了就用外部的，避免 prompt 和发送各抽一次导致不一致
    target = target_segments if 0 < target_segments <= max_segments else pick_segment_count(
        weights, max_segments
    )
    if len(expanded) > target:
        expanded = _merge_tail(expanded, target, merge_limit)

    # 硬上限：宁可最后一条长一点，也不能发出去 9 条（之前 max_segments 被 _merge_tail 绕过了）
    if len(expanded) > max_segments:
        head = expanded[: max_segments - 1]
        merged_tail = ""
        for piece in expanded[max_segments - 1:]:
            merged_tail = _join_pieces(merged_tail, piece)
        expanded = head + ([merged_tail] if merged_tail else [])

    return [piece for piece in expanded if piece.strip()]


def reply_delay(settings) -> float:
    return random.uniform(settings.reply_delay_min, settings.reply_delay_max)


def segment_interval(settings) -> float:
    return random.uniform(settings.segment_interval_min, settings.segment_interval_max)

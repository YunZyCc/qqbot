from __future__ import annotations

import random
import re

DEFAULT_WEIGHTS = (65.0, 22.0, 8.0, 3.0, 2.0)


def _pick_segment_count(weights: list[float] | None, max_segments: int) -> int:
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


def _join_pieces(left: str, right: str) -> str:
    """拼接两条消息；前一条没有标点收尾就补个逗号，避免「电子茶说真的」这种粘连。"""
    if not left:
        return right
    if not right:
        return left
    if left[-1] in _PUNCT_TAIL:
        return left + right
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
    segment_max_chars: int = 40,
    weights: list[float] | None = None,
    delimiter: str = "|||",
) -> list[str]:
    """把 LLM 输出拆成 1~5 条短消息，每条不超过 segment_max_chars 字。

    发几条由权重决定：一条最常见，四五条连发很少出现。
    """
    from .splitter import split_message

    text = (text or "").strip()
    if not text:
        return []

    parts = [p.strip() for p in text.split(delimiter) if p.strip()]
    if not parts:
        parts = [text]

    # 模型没按 ||| 输出时，按句末标点切，模拟连发
    if len(parts) == 1 and max_segments > 1:
        sentences = [s.strip() for s in re.split(r"(?<=[。！？!?])", parts[0]) if s.strip()]
        sentences = [s for s in sentences if len(s) >= 2]
        if 1 < len(sentences) <= max_segments:
            parts = sentences

    # 先保证每段不超长
    expanded: list[str] = []
    for part in parts:
        expanded.extend(split_message(part, segment_max_chars))

    # 按权重决定发几条；多出来的并进最后一条
    target = _pick_segment_count(weights, max_segments)
    if len(expanded) > target:
        expanded = _merge_tail(expanded, target, segment_max_chars)

    # 兜底：合并后仍可能超过硬上限
    if len(expanded) > max_segments:
        expanded = _merge_tail(expanded, max_segments, segment_max_chars)

    return [piece for piece in expanded if piece.strip()]


def reply_delay(settings) -> float:
    return random.uniform(settings.reply_delay_min, settings.reply_delay_max)


def segment_interval(settings) -> float:
    return random.uniform(settings.segment_interval_min, settings.segment_interval_max)

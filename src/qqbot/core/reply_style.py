from __future__ import annotations

import random
import re


def split_reply(
    text: str,
    max_segments: int = 3,
    max_chars: int = 500,
    delimiter: str = "|||",
) -> list[str]:
    """把 LLM 输出拆成 1~3 条短消息；没有分隔符时退回单条。"""
    from .splitter import split_message

    text = (text or "").strip()
    if not text:
        return []

    parts = [p.strip() for p in text.split(delimiter) if p.strip()]
    if not parts:
        parts = [text]

    # 模型没按 ||| 输出时，按句末标点切一两句，模拟连发
    if len(parts) == 1 and max_segments > 1:
        sentences = [s.strip() for s in re.split(r"(?<=[。！？!?])", parts[0]) if s.strip()]
        sentences = [s for s in sentences if len(s) >= 8]
        if 1 < len(sentences) <= max_segments:
            parts = sentences

    # 太短的段并入前一段，避免「嗯」「好」单独刷屏
    merged: list[str] = []
    for part in parts:
        if merged and len(part) < 10:
            merged[-1] = merged[-1] + part
        else:
            merged.append(part)

    if len(merged) > max_segments:
        merged = merged[: max_segments - 1] + ["".join(merged[max_segments - 1:])]

    out: list[str] = []
    for part in merged:
        if len(part) <= max_chars:
            out.append(part)
        else:
            out.extend(split_message(part, max_chars))
    return out


def reply_delay(settings) -> float:
    return random.uniform(settings.reply_delay_min, settings.reply_delay_max)


def segment_interval(settings) -> float:
    return random.uniform(settings.segment_interval_min, settings.segment_interval_max)

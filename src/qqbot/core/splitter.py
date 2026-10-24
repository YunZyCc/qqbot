from __future__ import annotations

import re

_SENTENCE_END = re.compile(r"(?<=[。！？!?；;\.\n])")


def split_message(text: str, limit: int = 500) -> list[str]:
    """把长回复切成不超过 limit 字的若干段，优先按段落/句末标点切。"""
    text = text.strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    pieces: list[str] = []
    for para in text.split("\n"):
        para = para.rstrip()
        if not para:
            continue
        if len(para) <= limit:
            pieces.append(para)
            continue
        # 按句末标点切，再按长度兜底
        buf = ""
        for sentence in _SENTENCE_END.split(para):
            if not sentence:
                continue
            while len(sentence) > limit:
                pieces.append(sentence[:limit])
                sentence = sentence[limit:]
            if len(buf) + len(sentence) <= limit:
                buf += sentence
            else:
                if buf:
                    pieces.append(buf)
                buf = sentence
        if buf:
            pieces.append(buf)

    # 合并过短的碎片，避免刷屏
    merged: list[str] = []
    for p in pieces:
        if merged and len(merged[-1]) + len(p) + 1 <= limit:
            merged[-1] = merged[-1] + "\n" + p
        else:
            merged.append(p)
    return merged

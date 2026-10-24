"""OneBot 11 消息段构造与解析。

统一入口都走这里，避免各处手写 {"type": ...} 字典。
"""

from __future__ import annotations


def seg_text(text: str) -> dict:
    return {"type": "text", "data": {"text": text}}


def seg_face(face_id: int) -> dict:
    return {"type": "face", "data": {"id": str(face_id)}}


def seg_mface(file: str) -> dict:
    """表情包（市场表情/收藏表情），file 为本地路径或 http(s) URL。"""
    return {"type": "mface", "data": {"summary": "[表情包]", "file": file}}


def seg_image(file: str) -> dict:
    return {"type": "image", "data": {"file": file}}


def seg_record(file: str) -> dict:
    return {"type": "record", "data": {"file": file}}


def seg_at(qq: int | str) -> dict:
    return {"type": "at", "data": {"qq": str(qq)}}


def seg_reply(message_id: int) -> dict:
    return {"type": "reply", "data": {"id": str(message_id)}}


def build(segments: list[dict]) -> list[dict]:
    """过滤空段并原样返回，作为发送消息的统一入口。"""
    return [s for s in segments if s]


def to_text(segments: list[dict]) -> str:
    """把消息段里的文本拼出来；表情/图片/语音用占位符表示。"""
    chunks: list[str] = []
    for seg in segments or []:
        if not isinstance(seg, dict):
            continue
        data = seg.get("data") or {}
        kind = seg.get("type")
        if kind == "text":
            chunks.append(str(data.get("text", "")))
        elif kind == "face":
            chunks.append(f"[表情:{data.get('id', '')}]")
        elif kind == "mface":
            chunks.append("[表情包]")
        elif kind == "image":
            chunks.append("[图片]")
        elif kind == "record":
            chunks.append("[语音]")
        elif kind == "at":
            chunks.append(f"@{data.get('qq', '')}")
    return "".join(chunks).strip()

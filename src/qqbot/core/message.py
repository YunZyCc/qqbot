"""OneBot 11 消息段构造与解析。

统一入口都走这里，避免各处手写 {"type": ...} 字典。
"""

from __future__ import annotations

from ..onebot.face_map import face_name


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


def image_segments(segments: list[dict]) -> list[dict]:
    """取出消息里的图片段（含表情包图片）。"""
    return [
        seg
        for seg in segments or []
        if isinstance(seg, dict) and seg.get("type") == "image"
    ]


def to_user_text(segments: list[dict]) -> str:
    """把用户发来的消息段转成可读文本，表情/图片用描述占位。"""
    parts: list[str] = []
    for seg in segments or []:
        if not isinstance(seg, dict):
            continue
        data = seg.get("data") or {}
        kind = seg.get("type")
        if kind == "text":
            parts.append(str(data.get("text", "")))
        elif kind == "face":
            parts.append(f"[表情:{face_name(data.get('id'))}]")
        elif kind == "mface":
            parts.append(f"[表情包:{data.get('summary') or '表情包'}]")
        elif kind == "image":
            sub = str(data.get("sub_type") or "")
            parts.append("[表情包]" if sub == "1" else "[图片]")
        elif kind == "record":
            parts.append("[语音]")
        elif kind == "at":
            parts.append(f"@{data.get('qq', '')}")
    return "".join(parts).strip()

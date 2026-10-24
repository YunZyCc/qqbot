from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Sender(BaseModel):
    user_id: int | None = None
    nickname: str | None = None
    card: str | None = None


class OneBotEvent(BaseModel):
    """只保留本程序用得到的字段，其余忽略。"""

    post_type: str = ""
    message_type: str = ""
    sub_type: str = ""
    message_id: int | None = None
    user_id: int | None = None
    group_id: int | None = None
    target_id: int | None = None
    message: Any = None
    raw_message: str = ""
    sender: Sender = Field(default_factory=Sender)


def extract_text(message: Any) -> str:
    """把 OneBot 消息（字符串或消息段数组）里的纯文本拼出来。"""
    if isinstance(message, str):
        return message
    if not isinstance(message, list):
        return ""
    chunks: list[str] = []
    for seg in message:
        if not isinstance(seg, dict):
            continue
        if seg.get("type") == "text":
            data = seg.get("data") or {}
            chunks.append(str(data.get("text", "")))
    return "".join(chunks).strip()

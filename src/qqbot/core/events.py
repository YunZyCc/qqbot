from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from ..onebot.events import OneBotEvent, extract_text


class EventKind(StrEnum):
    MESSAGE = "message"
    NOTICE = "notice"
    REQUEST = "request"
    META = "meta"


@dataclass(slots=True)
class Event:
    kind: EventKind
    raw: dict
    segments: list[dict] = field(default_factory=list)
    text: str = ""
    sender_id: int | None = None
    sender_name: str = ""
    sender_card: str = ""
    message_type: str = ""
    sub_type: str = ""
    group_id: int | None = None
    message_id: int | None = None
    session_scope: str | None = None

    @property
    def is_private(self) -> bool:
        return self.message_type == "private"

    @property
    def is_group(self) -> bool:
        return self.message_type == "group"


_KIND_MAP = {
    "message": EventKind.MESSAGE,
    "notice": EventKind.NOTICE,
    "request": EventKind.REQUEST,
    "meta_event": EventKind.META,
}


def normalize(raw: dict) -> Event | None:
    """把 OneBot 原始事件规范化成内部 Event；不认识的事件返回 None。"""
    try:
        ev = OneBotEvent.model_validate(raw)
    except Exception:
        return None

    kind = _KIND_MAP.get(ev.post_type)
    if kind is None:
        return None

    segments = ev.message if isinstance(ev.message, list) else []
    return Event(
        kind=kind,
        raw=raw,
        segments=segments,
        text=extract_text(ev.message),
        sender_id=ev.user_id,
        sender_name=(ev.sender.nickname or "").strip(),
        sender_card=(ev.sender.card or "").strip(),
        message_type=ev.message_type,
        sub_type=ev.sub_type,
        group_id=ev.group_id,
        message_id=ev.message_id,
    )

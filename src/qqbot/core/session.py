from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Protocol

from .events import Event, EventKind


@dataclass(frozen=True, slots=True)
class SessionKey:
    chat_type: str  # private | group
    chat_id: int

    @property
    def scope(self) -> str:
        return f"{self.chat_type}:{self.chat_id}"


def session_from_event(ev: Event) -> SessionKey | None:
    if ev.kind is not EventKind.MESSAGE:
        return None
    if ev.message_type == "private" and ev.sender_id:
        return SessionKey("private", ev.sender_id)
    if ev.message_type == "group" and ev.group_id:
        return SessionKey("group", ev.group_id)
    return None


class SessionPolicy(Protocol):
    async def should_respond(self, ev: Event) -> bool: ...

    def memory_scope(self, ev: Event) -> str: ...


class OwnerOnlyPolicy:
    """当前行为：只回应 owner 的私聊，记忆落在 private:<owner>。"""

    def __init__(self, owner_qq: int) -> None:
        self.owner_qq = owner_qq

    async def should_respond(self, ev: Event) -> bool:
        return (
            ev.kind is EventKind.MESSAGE
            and ev.message_type == "private"
            and ev.sender_id == self.owner_qq
        )

    def memory_scope(self, ev: Event) -> str:
        return f"private:{self.owner_qq}"


@dataclass
class SessionContext:
    key: SessionKey
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    turns: int = 0
    last_sticker_turn: int = -10


class SessionRegistry:
    def __init__(self) -> None:
        self._items: dict[str, SessionContext] = {}

    def get(self, key: SessionKey) -> SessionContext:
        ctx = self._items.get(key.scope)
        if ctx is None:
            ctx = SessionContext(key=key)
            self._items[key.scope] = ctx
        return ctx

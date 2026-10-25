from __future__ import annotations

import asyncio
from collections.abc import Iterable
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
    """只回应 owner 的私聊。保留给老配置用；群聊请用 OwnerAndGroupPolicy。"""

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


class OwnerAndGroupPolicy:
    """私聊只回应 owner；群聊只接白名单群。

    群的「回不回」细判（@ / 叫名字 / 活跃期 / 概率）放在 chat 层，
    因为那需要读 store 里的活跃期时间戳。这里只负责身份和 scope。
    """

    def __init__(
        self,
        owner_qq: int,
        bot_qq: int = 0,
        groups: Iterable[int] = (),
        friends: Iterable[int] = (),
    ) -> None:
        self.owner_qq = owner_qq
        self.bot_qq = bot_qq
        self.groups = {int(g) for g in groups if g}
        self.friends = {int(f) for f in friends if f and int(f) != owner_qq}

    async def should_respond(self, ev: Event) -> bool:
        if ev.kind is not EventKind.MESSAGE:
            return False
        if ev.message_type == "private":
            return (
                ev.sender_id == self.owner_qq or ev.sender_id in self.friends
            )
        if ev.message_type == "group":
            return self.group_allowed(ev.group_id)
        return False

    def memory_scope(self, ev: Event) -> str:
        if ev.is_group and ev.group_id:
            return f"group:{ev.group_id}"
        return f"private:{ev.sender_id or self.owner_qq}"

    def group_allowed(self, group_id: int | None) -> bool:
        if not group_id:
            return False
        return int(group_id) in self.groups

    def is_at_bot(self, ev: Event) -> bool:
        if not self.bot_qq:
            return False
        for seg in ev.segments or []:
            if not isinstance(seg, dict) or seg.get("type") != "at":
                continue
            data = seg.get("data") or {}
            if str(data.get("qq", "")) == str(self.bot_qq):
                return True
        return False

    def is_owner(self, qq: int | None) -> bool:
        return bool(qq) and int(qq) == int(self.owner_qq)


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

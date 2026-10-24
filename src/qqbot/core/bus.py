from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from .events import Event, EventKind, normalize
from .session import session_from_event

log = logging.getLogger(__name__)

Handler = Callable[[Event], Awaitable[None]]


@dataclass(slots=True)
class Subscription:
    kind: EventKind | None
    handler: Handler
    priority: int = 100
    name: str = ""


class EventBus:
    """按事件类型分发，priority 小的先执行。"""

    def __init__(self) -> None:
        self._subs: list[Subscription] = []

    def on(
        self,
        kind: EventKind | None,
        handler: Handler,
        *,
        priority: int = 100,
        name: str = "",
    ) -> None:
        self._subs.append(Subscription(kind=kind, handler=handler, priority=priority, name=name))

    async def dispatch(self, raw: dict) -> None:
        ev = normalize(raw)
        if ev is None:
            log.debug("无法识别的事件，已忽略")
            return

        key = session_from_event(ev)
        if key is not None:
            ev.session_scope = key.scope

        for sub in sorted(self._subs, key=lambda s: s.priority):
            if sub.kind is not None and sub.kind is not ev.kind:
                continue
            try:
                await sub.handler(ev)
            except Exception:
                log.exception("事件处理器 %s 出错", sub.name or sub.handler.__name__)

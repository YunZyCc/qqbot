from __future__ import annotations

import logging

from ..core.events import Event, EventKind

log = logging.getLogger(__name__)


class FriendsModule:
    """好友请求：目前只记录事件，审批流待实现。"""

    name = "friends"

    def setup(self, ctx) -> None:
        self.ctx = ctx
        ctx.bus.on(EventKind.REQUEST, self.handle, priority=100, name="friends")
        log.info("friends 模块已启用（好友审批待实现）")

    async def handle(self, ev: Event) -> None:
        raw = ev.raw or {}
        log.info(
            "friends: 收到请求 request_type=%s user=%s flag=%s（审批流待实现）",
            raw.get("request_type"),
            raw.get("user_id"),
            raw.get("flag"),
        )

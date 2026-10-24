from __future__ import annotations

import logging

from ..core.events import Event, EventKind

log = logging.getLogger(__name__)


class GroupModule:
    """群聊：目前只记录群消息，触发与回复逻辑待实现。"""

    name = "group"

    def setup(self, ctx) -> None:
        self.ctx = ctx
        ctx.bus.on(EventKind.MESSAGE, self.handle, priority=90, name="group")
        log.info("group 模块已启用（群聊回复待实现）")

    async def handle(self, ev: Event) -> None:
        if not ev.is_group:
            return
        log.info(
            "group: 群消息 group=%s sender=%s（群聊待实现）", ev.group_id, ev.sender_id
        )

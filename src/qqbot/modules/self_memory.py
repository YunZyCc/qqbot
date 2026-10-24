from __future__ import annotations

import logging

from pydantic import BaseModel

from ..tools.registry import Tool

log = logging.getLogger(__name__)


class RememberSelfParams(BaseModel):
    predicate: str
    object: str


class RecallSelfParams(BaseModel):
    query: str


class SelfMemoryModule:
    """机器人自我记忆：心情、关注、承诺、关于自己的事实。"""

    name = "self_memory"

    def setup(self, ctx) -> None:
        self.ctx = ctx

        async def remember_self(predicate: str, object: str) -> str:
            await ctx.self_memory.remember(predicate, object)
            return f"记住了关于自己的事：{predicate} {object}"

        async def recall_self(query: str) -> str:
            picked = await ctx.self_memory.recall(query, 5)
            if not picked:
                return "没有找到关于自己的相关记忆"
            return "\n".join(f"- {f['predicate']}: {f['object']}" for f in picked)

        ctx.tools.register(
            Tool(
                name="remember_self",
                description="记下一条关于你自己的事",
                params=RememberSelfParams,
                handler=remember_self,
            )
        )
        ctx.tools.register(
            Tool(
                name="recall_self",
                description="回忆关于你自己的事",
                params=RecallSelfParams,
                handler=recall_self,
            )
        )
        log.info("self_memory 模块已启用（自我记忆工具已注册）")

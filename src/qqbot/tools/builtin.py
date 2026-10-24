from __future__ import annotations

from pydantic import BaseModel

from ..memory.context import current_scope
from ..memory.retrieve import retrieve
from .registry import Tool, ToolRegistry


class MemorySearchParams(BaseModel):
    query: str
    k: int = 5


class MemoryWriteParams(BaseModel):
    predicate: str
    object: str
    confidence: float = 0.8


class StickerParams(BaseModel):
    key: str


def register_builtin_tools(registry: ToolRegistry, ctx) -> None:
    async def memory_search(query: str, k: int) -> str:
        scope = current_scope.get() or f"private:{ctx.settings.owner_qq}"
        facts = await ctx.store.active_facts(scope)
        picked = retrieve(query, facts, k)
        if not picked:
            return "没有找到相关记忆"
        return "\n".join(f"- {f['predicate']}: {f['object']}" for f in picked)

    async def memory_write(predicate: str, object: str, confidence: float) -> str:
        scope = current_scope.get() or f"private:{ctx.settings.owner_qq}"
        await ctx.store.upsert_fact(scope, "user", predicate, object, confidence)
        return f"记住了：{predicate} {object}"

    async def send_sticker(key: str) -> str:
        # 表情包库在 media 模块实现；这里先占位，避免模型调用后无响应
        return f"表情包库尚未配置，无法发送 {key!r}"

    registry.register(
        Tool(
            name="memory_search",
            description="搜索你记得的、关于对方的长期事实",
            params=MemorySearchParams,
            handler=memory_search,
        )
    )
    registry.register(
        Tool(
            name="memory_write",
            description="记下一条关于对方的长期事实",
            params=MemoryWriteParams,
            handler=memory_write,
        )
    )
    registry.register(
        Tool(
            name="send_sticker",
            description="按关键词发送一个表情包",
            params=StickerParams,
            handler=send_sticker,
        )
    )

from __future__ import annotations

import logging

from pydantic import BaseModel

from ..memory.context import current_scope
from ..memory.retrieve import retrieve
from .registry import Tool, ToolRegistry

log = logging.getLogger(__name__)


class MemorySearchParams(BaseModel):
    query: str
    k: int = 5


class MemoryWriteParams(BaseModel):
    predicate: str
    object: str
    confidence: float = 0.8


class StickerParams(BaseModel):
    query: str


class LookAtImageParams(BaseModel):
    sha256: str
    question: str = ""


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

    async def _send_image(path, sub_type: str | None) -> bool:
        data: dict = {"file": str(path)}
        if sub_type:
            data["sub_type"] = str(sub_type)
        try:
            await ctx.api.call(
                "send_private_msg",
                user_id=ctx.settings.owner_qq,
                message=[{"type": "image", "data": data}],
            )
            return True
        except Exception:
            log.warning("表情包发送失败", exc_info=True)
            return False

    async def send_sticker(query: str) -> str:
        kit = getattr(ctx, "sticker_kit", None)
        if kit is not None:
            for hit in kit.search(query, 3):
                path = await kit.ensure_file(hit)
                if path is None:
                    continue
                if await _send_image(path, ctx.settings.sticker_sub_type):
                    return f"已发送表情包：{hit['name']}（{hit['emotion']}）"

        if ctx.stickers is not None:
            for hit in await ctx.stickers.search(query, 3):
                path = ctx.stickers.resolve(hit["file"])
                if path is None:
                    continue
                if await _send_image(path, None):
                    return f"已发送表情包：{hit['key']}"

        return "没有找到合适的表情包"

    async def look_at_image(sha256: str, question: str) -> str:
        if ctx.vision is None or ctx.images is None:
            return "视觉功能未启用"
        ref = await ctx.store.get_image_by_hash(sha256)
        if ref is None:
            return "找不到这张图"
        path = ctx.images.load(sha256)
        if path is None:
            return "图片缓存已过期"
        try:
            description = await ctx.vision.describe(
                path.read_bytes(), ref["mime"], question
            )
        except Exception:
            return "图片识别失败了"
        return description or "看不清"

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
            description="按语义搜索并发送一个表情包，例如「开心」「无语」「摸摸头」",
            params=StickerParams,
            handler=send_sticker,
        )
    )
    registry.register(
        Tool(
            name="look_at_image",
            description="针对对方最近发的图片追问细节（用描述里给的 hash）",
            params=LookAtImageParams,
            handler=look_at_image,
        )
    )

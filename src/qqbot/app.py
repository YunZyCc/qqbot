from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Protocol

from .capabilities.builtin import register_builtin_actions
from .capabilities.registry import ActionRegistry
from .config import Settings, get_settings
from .core.bus import EventBus
from .core.session import (
    OwnerAndGroupPolicy,
    OwnerOnlyPolicy,
    SessionPolicy,
    SessionRegistry,
)
from .llm.client import ChatClient
from .media import ImageCache
from .memory.contacts import ContactStore
from .memory.embedding import NullEmbedding, OpenAICompatibleEmbedding
from .memory.emotion import EmotionTracker
from .memory.hybrid import HybridRetriever
from .memory.self_memory import SelfMemory
from .memory.sticker_kit import StickerKit
from .memory.stickers import StickerLibrary
from .memory.store import Store
from .memory.vector import NumpyVectorIndex
from .ollama import ensure_ollama
from .onebot.api import OneBotAPI
from .persona.loader import load_persona
from .prompt.sections import build_default_composer
from .runtime.simple import SimpleRuntime
from .scheduler.scheduler import Scheduler
from .search import build_search
from .tools.builtin import register_builtin_tools
from .tools.mcp import load_mcp_tools
from .tools.registry import ToolRegistry
from .vision import NullVision, OpenAICompatibleVision

log = logging.getLogger(__name__)


class Module(Protocol):
    name: str

    def setup(self, ctx: AppContext) -> None: ...


@dataclass
class AppContext:
    settings: Settings
    store: Store
    persona: str
    api: OneBotAPI
    llm: ChatClient
    bus: EventBus
    policy: SessionPolicy
    sessions: SessionRegistry
    # 以下在后续阶段填充
    actions: object | None = None
    tools: object | None = None
    runtime: object | None = None
    scheduler: object | None = None
    memory: object | None = None
    contacts: object | None = None
    self_memory: object | None = None
    prompt: object | None = None
    embedder: object | None = None
    vector: object | None = None
    retriever: object | None = None
    vision: object | None = None
    search: object | None = None
    stickers: object | None = None
    sticker_kit: object | None = None
    images: object | None = None
    emotion: object | None = None
    last_user_at: float = 0.0
    modules: list = field(default_factory=list)


def build_policy(settings: Settings) -> SessionPolicy:
    """群聊关掉时退回纯私聊策略，行为和以前完全一致。"""
    if not settings.group_enabled:
        log.info("群聊未启用，只回应主人私聊")
        return OwnerOnlyPolicy(settings.owner_qq)
    groups = settings.group_whitelist_ids
    if not groups:
        log.warning("群聊已启用但白名单为空，收到群消息只打日志不回复")
    else:
        log.info("群聊已启用，白名单群：%s", "、".join(str(g) for g in groups))
    friends = settings.friend_whitelist_ids
    if friends:
        log.info("好友白名单：%s", "、".join(str(f) for f in friends))
    return OwnerAndGroupPolicy(
        settings.owner_qq, settings.bot_qq, groups, friends
    )


async def build_embedding(settings: Settings):
    """探测 embedding 服务；不可用时返回 NullEmbedding，聊天照常。"""
    if not settings.memory_vector_enabled:
        log.info("向量记忆未启用")
        return NullEmbedding()

    provider = OpenAICompatibleEmbedding(
        base_url=settings.embedding_base_url,
        api_key=settings.embedding_api_key,
        model=settings.embedding_model,
        dim=settings.embedding_dim,
        timeout=settings.embedding_timeout,
    )
    try:
        vectors = await provider.embed(["ping"])
        if vectors and len(vectors[0]) == settings.embedding_dim:
            log.info("embedding 服务可用：%s（%s 维）", settings.embedding_model, settings.embedding_dim)
            return provider
        log.warning("embedding 返回维度不符，降级为纯关键词")
    except Exception as exc:  # noqa: BLE001
        log.warning("embedding 探测失败（%s），降级为纯关键词", exc)
    await provider.close()
    return NullEmbedding()


async def build_context(settings: Settings | None = None) -> AppContext:
    settings = settings or get_settings()
    if settings.owner_qq <= 0:
        raise SystemExit("OWNER_QQ 未配置：请把 .env 里的 OWNER_QQ 改成你自己的 QQ 号")
    if not settings.deepseek_api_key:
        raise SystemExit("DEEPSEEK_API_KEY 未配置")

    store = Store(
        settings.data_dir / "qqbot.db",
        default_scope=f"private:{settings.owner_qq}",
    )
    await store.init()

    # 先确认本地模型服务在跑，否则图片识别和向量检索会静默降级
    await ensure_ollama(settings)

    ctx = AppContext(
        settings=settings,
        store=store,
        persona=load_persona(settings.persona_file),
        api=OneBotAPI(),
        llm=ChatClient(store),
        bus=EventBus(),
        policy=build_policy(settings),
        sessions=SessionRegistry(),
    )

    # 搜索要在工具注册前构建：不可用时工具不注册
    ctx.search = build_search(settings)

    actions = ActionRegistry()
    tools = ToolRegistry()
    register_builtin_actions(actions, ctx)
    register_builtin_tools(tools, ctx)
    await load_mcp_tools(tools, settings.mcp_server_list)

    ctx.actions = actions
    ctx.tools = tools
    ctx.contacts = ContactStore(store)
    ctx.self_memory = SelfMemory(store)
    ctx.emotion = EmotionTracker(ctx.self_memory, settings)
    ctx.prompt = build_default_composer()
    ctx.scheduler = Scheduler()
    ctx.scheduler.start()

    embedder = await build_embedding(settings)
    ctx.embedder = embedder
    ctx.vector = NumpyVectorIndex(store, embedder) if not isinstance(embedder, NullEmbedding) else None
    ctx.retriever = HybridRetriever(store, ctx.vector)

    if settings.vision_enabled:
        if settings.vision_provider == "deepseek":
            # DeepSeek 原生支持图片输入，接口和 OpenAI 完全一致，只是换了 base/key/model
            ctx.vision = OpenAICompatibleVision(
                settings.deepseek_base_url,
                settings.deepseek_api_key,
                settings.deepseek_vision_model,
                settings.vision_timeout,
                flatten_dynamic=False,
                disable_thinking=True,
            )
            log.info("视觉模型：DeepSeek %s", settings.deepseek_vision_model)
        else:
            ctx.vision = OpenAICompatibleVision(
                settings.vision_base_url,
                settings.vision_api_key,
                settings.vision_model,
                settings.vision_timeout,
            )
            log.info("视觉模型：本地 %s", settings.vision_model)
    else:
        ctx.vision = NullVision()
    ctx.images = ImageCache(
        settings.data_dir / "images", settings.vision_max_image_mb
    )
    ctx.stickers = StickerLibrary(store, settings, ctx.vector)
    try:
        await ctx.stickers.scan()
    except Exception:
        log.exception("构建表情包索引失败")

    if settings.nekowhale_enabled:
        ctx.sticker_kit = StickerKit(settings, store, ctx.vector)
        ctx.sticker_kit.load()
        # 322 张建向量要几十秒，放到后台跑，期间搜索走关键词
        if ctx.vector is not None:
            asyncio.create_task(ctx.sticker_kit.ensure_vectors())
    else:
        ctx.sticker_kit = None

    ctx.runtime = SimpleRuntime(
        ctx.llm,
        tools,
        enabled=settings.tools_enabled,
        max_rounds=settings.tool_max_rounds,
    )

    # 延迟导入，避免 modules 反向依赖 app
    from .modules import MODULES

    enabled = settings.enabled_module_list
    for module in MODULES:
        if module.name not in enabled:
            log.info("模块 %s 未启用", module.name)
            continue
        module.setup(ctx)
        ctx.modules.append(module)
        log.info("模块 %s 已加载", module.name)

    return ctx


async def shutdown(ctx: AppContext) -> None:
    if ctx.scheduler is not None:
        ctx.scheduler.shutdown()
    if ctx.sticker_kit is not None:
        await ctx.sticker_kit.close()
    if ctx.vision is not None:
        await ctx.vision.close()
    if ctx.search is not None:
        await ctx.search.close()
    if ctx.embedder is not None:
        await ctx.embedder.close()
    await ctx.api.close()
    await ctx.llm.close()
    await ctx.store.close()

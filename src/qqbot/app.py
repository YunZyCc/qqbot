from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

from .capabilities.builtin import register_builtin_actions
from .capabilities.registry import ActionRegistry
from .config import Settings, get_settings
from .core.bus import EventBus
from .core.session import OwnerOnlyPolicy, SessionPolicy, SessionRegistry
from .llm.client import ChatClient
from .memory.contacts import ContactStore
from .memory.self_memory import SelfMemory
from .memory.store import Store
from .onebot.api import OneBotAPI
from .persona.loader import load_persona
from .prompt.sections import build_default_composer
from .runtime.simple import SimpleRuntime
from .scheduler.scheduler import Scheduler
from .tools.builtin import register_builtin_tools
from .tools.mcp import load_mcp_tools
from .tools.registry import ToolRegistry

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
    modules: list = field(default_factory=list)


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

    ctx = AppContext(
        settings=settings,
        store=store,
        persona=load_persona(settings.persona_file),
        api=OneBotAPI(),
        llm=ChatClient(),
        bus=EventBus(),
        policy=OwnerOnlyPolicy(settings.owner_qq),
        sessions=SessionRegistry(),
    )

    actions = ActionRegistry()
    tools = ToolRegistry()
    register_builtin_actions(actions, ctx)
    register_builtin_tools(tools, ctx)
    await load_mcp_tools(tools, settings.mcp_server_list)

    ctx.actions = actions
    ctx.tools = tools
    ctx.contacts = ContactStore(store)
    ctx.self_memory = SelfMemory(store)
    ctx.prompt = build_default_composer()
    ctx.scheduler = Scheduler()
    ctx.scheduler.start()
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
    await ctx.api.close()
    await ctx.llm.close()
    await ctx.store.close()

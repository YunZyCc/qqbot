# 扩展指南

底座的目标：加功能只写一个模块，不改核心。

## 分层

```
NapCat WS
  └─ core/ws → core/bus.py（事件分发，按 kind + priority）
       └─ modules/*  （业务模块，注册事件订阅 / 定时任务 / 工具 / 动作）
            ├─ prompt/composer.py   （system 拼装，section 可插拔）
            ├─ memory/*             （scope 隔离的记忆、联系人、关系、自我状态）
            ├─ runtime/simple.py    （LLM + 工具调用循环）
            ├─ tools/registry.py    （给模型用的工具）
            └─ capabilities/registry.py（平台动作，如发消息/签名/说说）
```

## 加一个工具

1. 在 `src/qqbot/tools/builtin.py`（或你自己的模块里）定义一个 pydantic 参数模型和 handler：

```python
from pydantic import BaseModel
from ..tools.registry import Tool

class WeatherParams(BaseModel):
    city: str

async def weather(city: str) -> str:
    return f"{city}：晴，25 度"  # 真实实现里调 API

registry.register(Tool(
    name="weather",
    description="查询天气",
    params=WeatherParams,
    handler=weather,
))
```

2. 在 `.env` 里打开工具：

```
TOOLS_ENABLED=true
```

工具会自动出现在 `openai_schemas()` 里，模型可以调用。工具执行失败会返回错误字符串，不会中断对话。

## 加一个模块

以「群聊回复」为例：

```python
# src/qqbot/modules/group_reply.py
from ..core.events import Event, EventKind

class GroupReplyModule:
    name = "group_reply"

    def setup(self, ctx) -> None:
        self.ctx = ctx
        ctx.bus.on(EventKind.MESSAGE, self.handle, priority=50, name="group_reply")

    async def handle(self, ev: Event) -> None:
        if not ev.is_group or not ev.text:
            return
        # 这里调用 ctx.runtime.run(...) 和 ctx.api.send_private_msg(...)
        ...
```

然后在 `modules/__init__.py` 的 `MODULES` 里加 `GroupReplyModule()`，在 `.env` 里 `ENABLED_MODULES=chat,group_reply`。

模块可以做的事：

- `ctx.bus.on(kind, handler)`：订阅事件
- `ctx.scheduler.every(seconds, fn)` / `ctx.scheduler.cron("0 20 * * *", fn)`：定时任务
- `ctx.actions.register(...)`：新增平台动作
- `ctx.tools.register(...)`：新增模型工具
- `ctx.store` / `ctx.contacts` / `ctx.self_memory`：读写记忆

## 加一种消息类型

发送端在 `core/message.py` 加一个构造函数：

```python
def seg_video(file: str) -> dict:
    return {"type": "video", "data": {"file": file}}
```

接收端在 `core/message.py` 的 `to_text()` 里加占位符（如 `[视频]`），否则纯文本提取会把它丢掉。

## 加一个平台动作

```python
from pydantic import BaseModel
from ..capabilities.registry import Action

class LikeParams(BaseModel):
    user_id: int
    times: int = 1

async def send_like(user_id: int, times: int):
    return await ctx.api.call("send_like", user_id=user_id, times=times)

ctx.actions.register(Action("send_like", "给好友点赞", LikeParams, send_like))
```

`expose_as_tool=True` 的动作后续可以自动转成工具（当前版本还没做自动转换，需要手动注册 Tool）。

## 记忆 scope 约定

| scope | 用途 |
|---|---|
| `private:<qq>` | 私聊会话消息和摘要 |
| `group:<gid>` | 群聊会话消息和摘要 |
| `user:<qq>` | 这个好友的长期事实 |
| `bot:self` | 机器人自己的记忆（`SelfMemory`） |
| `social:global` | 好友间关系（`relations` 表） |

工具里取当前会话 scope 用：

```python
from ..memory.context import current_scope
scope = current_scope.get()
```

## 配置项

| 变量 | 默认 | 说明 |
|---|---|---|
| `ENABLED_MODULES` | `chat` | 逗号分隔的模块名 |
| `TOOLS_ENABLED` | `false` | 是否把工具暴露给模型 |
| `TOOL_MAX_ROUNDS` | `4` | 工具调用最大轮数 |
| `MCP_SERVERS` | 空 | JSON 数组，MCP server 配置 |

## 迁移

数据库 `schema_version` 存在 `settings` 表。新版本加列时在 `memory/store.py` 的 `_migrate()` 里用 `_ensure_column()`，迁移会自动回填旧数据到 `private:<owner>`。

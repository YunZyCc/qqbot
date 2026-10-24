from __future__ import annotations

import json
import logging

from ..llm.client import ChatClient
from ..memory.context import current_scope
from ..tools.registry import ToolRegistry

log = logging.getLogger(__name__)


class SimpleRuntime:
    """默认运行时：无工具时直接对话，有工具时走 tool_calls 循环。"""

    def __init__(
        self,
        llm: ChatClient,
        tools: ToolRegistry,
        *,
        enabled: bool = False,
        max_rounds: int = 4,
    ) -> None:
        self.llm = llm
        self.tools = tools
        self.enabled = enabled
        self.max_rounds = max_rounds

    async def run(
        self,
        messages: list[dict],
        *,
        scope: str = "",
        max_rounds: int | None = None,
    ) -> tuple[str, int]:
        if not self.enabled or not self.tools.all():
            content, usage = await self.llm.complete(messages)
            return content, usage

        token = current_scope.set(scope)
        try:
            return await self._tool_loop(messages, scope=scope, max_rounds=max_rounds)
        finally:
            current_scope.reset(token)

    async def _tool_loop(
        self,
        messages: list[dict],
        *,
        scope: str,
        max_rounds: int | None,
    ) -> tuple[str, int]:
        schemas = self.tools.openai_schemas()
        rounds = max_rounds or self.max_rounds
        total = 0
        content = ""
        work = list(messages)

        for _ in range(rounds):
            content, usage, tool_calls = await self.llm.complete_with_tools(
                work, tools=schemas
            )
            total += usage
            if not tool_calls:
                return content, total

            work.append(
                {
                    "role": "assistant",
                    "content": content or None,
                    "tool_calls": tool_calls,
                }
            )
            for call in tool_calls:
                fn = call.get("function", {}) or {}
                name = fn.get("name", "")
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = await self.tools.run(name, args)
                work.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", ""),
                        "content": result,
                    }
                )
                log.info("工具 %s 执行完成（scope=%s）", name, scope)

        log.warning("工具调用达到上限 %s 轮，返回当前结果", rounds)
        return content, total

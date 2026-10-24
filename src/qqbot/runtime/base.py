from __future__ import annotations

from typing import Protocol


class AgentRuntime(Protocol):
    """LLM 执行器协议。

    默认用 SimpleRuntime；将来复杂任务可以换成 LangGraph / deepagents 适配器，
    聊天主循环不需要改。
    """

    async def run(
        self,
        messages: list[dict],
        *,
        scope: str = "",
        max_rounds: int | None = None,
    ) -> tuple[str, int]: ...

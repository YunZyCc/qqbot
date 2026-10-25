from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(slots=True)
class PromptContext:
    persona: str = ""
    evolution: list[dict] = field(default_factory=list)
    chatroom: dict | None = None
    dm_identity: dict | None = None
    summary: str = ""
    facts: list[dict] = field(default_factory=list)
    episodes: list[dict] = field(default_factory=list)
    relations: list[dict] = field(default_factory=list)
    self_state: dict = field(default_factory=dict)
    emotion: str = ""
    diary: str = ""
    images: str = ""
    tools_hint: str = ""
    rules: str = ""
    # 这一轮打算发几条、每条最多几个字（由权重先抽好，写进 prompt 让模型按量输出）
    reply_slots: int = 0
    reply_slot_chars: int = 20
    history: list[dict] = field(default_factory=list)


Section = Callable[[PromptContext], str]


class PromptComposer:
    """按注册顺序拼 system；返回空字符串的 section 自动跳过。"""

    def __init__(self) -> None:
        self._sections: list[tuple[str, Section]] = []

    def register(self, name: str, fn: Section) -> None:
        self._sections.append((name, fn))

    def sections(self) -> list[str]:
        return [name for name, _ in self._sections]

    def compose(self, ctx: PromptContext) -> list[dict]:
        parts = []
        for _, fn in self._sections:
            text = (fn(ctx) or "").strip()
            if text:
                parts.append(text)
        system = {"role": "system", "content": "\n\n".join(parts)}

        history = list(ctx.history)
        while history and history[0].get("role") != "user":
            history.pop(0)

        return [system, *history]

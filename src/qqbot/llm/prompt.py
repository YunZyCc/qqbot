from __future__ import annotations

from ..prompt.composer import PromptContext
from ..prompt.sections import build_default_composer

__all__ = ["build_messages", "REPLY_RULES"]

from ..prompt.sections import REPLY_RULES  # noqa: E402


def build_messages(
    persona: str,
    summary: str,
    facts: list[dict],
    history: list[dict],
) -> list[dict]:
    """兼容旧接口；实际拼装交给 PromptComposer。"""
    composer = build_default_composer()
    return composer.compose(
        PromptContext(
            persona=persona,
            summary=summary,
            facts=facts,
            history=history,
        )
    )

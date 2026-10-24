from __future__ import annotations

from .composer import PromptComposer, PromptContext

REPLY_RULES = """输出要求：
- 像微信聊天一样自然，短句、口语。
- 不要 Markdown、不要列表、不要标题、不要加粗。
- 默认 120 字以内，对方认真问事情时可以稍长。
- 不要每句都反问，不要客服腔。"""


def persona_section(ctx: PromptContext) -> str:
    return ctx.persona


def self_section(ctx: PromptContext) -> str:
    state = ctx.self_state or {}
    mood = state.get("mood") or ""
    focus = state.get("focus") or ""
    commitments = state.get("commitments") or []
    if not (mood or focus or commitments):
        return ""
    lines = ["你现在的状态："]
    if mood:
        lines.append(f"- 心情：{mood}")
    if focus:
        lines.append(f"- 正在关注：{focus}")
    if commitments:
        lines.append("- 你答应过的事：" + "；".join(commitments))
    return "\n".join(lines)


def facts_section(ctx: PromptContext) -> str:
    if not ctx.facts:
        return ""
    lines = [f"- 对方{f['predicate']}：{f['object']}" for f in ctx.facts]
    return "你记得的关于对方的信息：\n" + "\n".join(lines)


def relations_section(ctx: PromptContext) -> str:
    if not ctx.relations:
        return ""
    lines = [
        f"- {r['a_qq']} 和 {r['b_qq']} 是{r['relation_type']}（{r.get('evidence', '')}）"
        for r in ctx.relations
    ]
    return "你记得的人际关系：\n" + "\n".join(lines)


def summary_section(ctx: PromptContext) -> str:
    if not ctx.summary.strip():
        return ""
    return "你们之前的对话摘要：\n" + ctx.summary.strip()


def tools_hint_section(ctx: PromptContext) -> str:
    return ctx.tools_hint.strip()


def rules_section(ctx: PromptContext) -> str:
    return ctx.rules or REPLY_RULES


def build_default_composer() -> PromptComposer:
    composer = PromptComposer()
    composer.register("persona", persona_section)
    composer.register("self", self_section)
    composer.register("facts", facts_section)
    composer.register("relations", relations_section)
    composer.register("summary", summary_section)
    composer.register("tools", tools_hint_section)
    composer.register("rules", rules_section)
    return composer

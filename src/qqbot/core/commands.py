from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def list_personas(ctx) -> str:
    personas = getattr(ctx, "personas", {}) or {}
    unique: dict[str, object] = {}
    for persona in personas.values():
        unique.setdefault(str(persona.path), persona)
    if not unique:
        return "没有可用人设"

    lines = ["可用人设："]
    current_name = getattr(ctx, "current_persona", "") or ""
    for persona in unique.values():
        mark = "（当前）" if persona.name == current_name else ""
        tags = "、".join(persona.tags)
        lines.append(f"- {persona.name}{mark}：{persona.description or tags}")
    lines.append("用 /persona 名字 切换，例如 /persona 阿宁")
    return "\n".join(lines)


async def switch_persona(ctx, name: str) -> str:
    personas = getattr(ctx, "personas", {}) or {}
    persona = personas.get(name.lower())
    if persona is None:
        return f"没有叫「{name}」的人设。用 /persona 看看有哪些。"

    ctx.persona = persona.text
    ctx.current_persona = persona.name
    await ctx.store.set_setting("current_persona", persona.name)
    log.info("人设切换为：%s", persona.name)
    return f"好，现在我是「{persona.name}」。{persona.description}"


async def handle_command(ctx, text: str) -> str | None:
    """处理管理员命令；不是命令返回 None。"""
    text = (text or "").strip()
    if not text.startswith("/"):
        return None
    parts = text[1:].split()
    if not parts:
        return None

    command = parts[0].lower()
    if command in ("persona", "personas"):
        if len(parts) == 1:
            return list_personas(ctx)
        return await switch_persona(ctx, parts[1])
    return None

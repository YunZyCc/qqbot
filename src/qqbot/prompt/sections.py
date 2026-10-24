from __future__ import annotations

import datetime as dt
import time

from .composer import PromptComposer, PromptContext

REPLY_RULES = """输出要求：
- 像微信聊天一样自然，短句、口语，每条 1~40 字，别一条塞太多。
- **能一句说完就只发一句。** 默认就发一条，不要习惯性地拆成「主观点 + 补充」两条。
- 真的还有话要说、或者想换个语气补一句，才用 ||| 再加一条。
- 偶尔连发 3~4 条，连发五条很少见——别每次都炸一串。
- 不要 Markdown、不要列表、不要标题、不要加粗。
- 不要每句都反问，不要客服腔。
- 对方要表情包、或者你想用表情包回应时，调用 send_sticker 工具直接发，不要只说「给你发一个」。"""


def chatroom_section(ctx: PromptContext) -> str:
    """群聊场景：告诉她这是群、谁在说话、群里认识谁、什么不能说。"""
    info = ctx.chatroom or {}
    if not info:
        return ""

    speaker = info.get("speaker_name") or "有人"
    speaker_qq = info.get("speaker_qq") or ""
    is_owner = bool(info.get("is_owner"))
    group_id = info.get("group_id") or ""
    identity = "是你的主人" if is_owner else "不是你的主人"

    lines = [
        "你现在在一个 QQ 群里聊天。",
        "",
        "在这个群里，你的名字就是「大肥鱼」，也只认这一个名字。",
        "- 有人问你是谁、叫什么，就答大肥鱼。",
        "- 说到自己的时候，也用大肥鱼。",
        "- 「周周」这个名字在这个群不适用，一句都别提。",
        "",
        f"当前说话的是「{speaker}」（QQ {speaker_qq}），{identity}。",
        f"群号 {group_id}，群里还有别人在看。",
    ]

    members = info.get("members") or []
    others = [
        m for m in members
        if int(m.get("qq") or 0) != int(speaker_qq or 0)
    ]
    if others:
        lines.append("")
        lines.append("你在这个群里还认识这些人：")
        for member in others:
            name = member.get("card") or member.get("nickname") or member.get("qq")
            lines.append(f"- {name}")

    lines.append("")
    lines.append("群聊规矩：")
    lines.append("- 只接当前说话的人，别把别人的话当成对你说的。")
    lines.append("- 你正在跟他们聊着，就接着聊；聊完这阵子再自然停下。")
    lines.append("- 不要提你和主人私聊里的事，一个字都别提。")
    lines.append("- 不要提你在别的群、别的私聊里说过什么。")
    lines.append("- 不确定的就不说，别替别人补充。")
    lines.append("- 称呼用群名片，别用私聊里的叫法。")
    return "\n".join(lines)


def persona_section(ctx: PromptContext) -> str:
    return ctx.persona


_WEEKDAYS = "一二三四五六日"


def evolution_section(ctx: PromptContext) -> str:
    """人格成长层：她自己长出来的变化，跟骨架分开放。"""
    if not ctx.evolution:
        return ""
    lines = [f"- {row['content']}" for row in ctx.evolution if row.get("content")]
    if not lines:
        return ""
    return (
        "你最近的变化（这是你自己长出来的，已经是你的一部分，"
        "自然地用，别当清单念）：\n" + "\n".join(lines)
    )


def time_section(ctx: PromptContext) -> str:
    """模型不知道今天是几号，就理解不了「最近」「今天」，搜索结果的时效也判断不了。"""
    now = dt.datetime.now()
    return f"现在是 {now:%Y-%m-%d} 周{_WEEKDAYS[now.weekday()]} {now:%H:%M}。"


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


def emotion_section(ctx: PromptContext) -> str:
    if not ctx.emotion.strip():
        return ""
    return "你心里那点事：\n" + ctx.emotion.strip()


def facts_section(ctx: PromptContext) -> str:
    if not ctx.facts:
        return ""
    stable = [f for f in ctx.facts if (f.get("source") or "fact") != "focus"]
    focus = [f for f in ctx.facts if (f.get("source") or "") == "focus"]

    blocks: list[str] = []
    if stable:
        lines = [f"- 对方{f['predicate']}：{f['object']}" for f in stable]
        blocks.append("你记得的关于对方的信息：\n" + "\n".join(lines))
    if focus:
        lines = [f"- {f['predicate']}：{f['object']}" for f in focus]
        blocks.append("对方最近在忙/关注的事（可能已经变了，别当成永久设定）：\n" + "\n".join(lines))
    return "\n\n".join(blocks)


def episodes_section(ctx: PromptContext) -> str:
    if not ctx.episodes:
        return ""
    lines = []
    for ep in ctx.episodes:
        text = (ep.get("text") or "").strip()
        if not text:
            continue
        ts = float(ep.get("end_ts") or 0)
        when = time.strftime("%m-%d", time.localtime(ts)) if ts else ""
        lines.append(f"- {when}：{text[:160]}" if when else f"- {text[:160]}")
    if not lines:
        return ""
    return "你们之间真实发生过的事（按需引用，别每次全翻出来）：\n" + "\n".join(lines)


def relations_section(ctx: PromptContext) -> str:
    if not ctx.relations:
        return ""
    lines = [
        f"- {r['a_qq']} 和 {r['b_qq']} 是{r['relation_type']}（{r.get('evidence', '')}）"
        for r in ctx.relations
    ]
    return "你记得的人际关系：\n" + "\n".join(lines)


def images_section(ctx: PromptContext) -> str:
    if not ctx.images.strip():
        return ""
    return (
        "最近对方发的图片（需要细节时用 look_at_image 工具追问）：\n"
        + ctx.images.strip()
    )


def diary_section(ctx: PromptContext) -> str:
    if not ctx.diary.strip():
        return ""
    return "你最近几天的日记：\n" + ctx.diary.strip()


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
    composer.register("chatroom", chatroom_section)
    composer.register("evolution", evolution_section)
    composer.register("time", time_section)
    composer.register("self", self_section)
    composer.register("emotion", emotion_section)
    composer.register("facts", facts_section)
    composer.register("episodes", episodes_section)
    composer.register("relations", relations_section)
    composer.register("images", images_section)
    composer.register("diary", diary_section)
    composer.register("summary", summary_section)
    composer.register("tools", tools_hint_section)
    composer.register("rules", rules_section)
    return composer

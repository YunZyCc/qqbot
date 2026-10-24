from __future__ import annotations

REPLY_RULES = """输出要求：
- 像微信聊天一样自然，短句、口语。
- 不要 Markdown、不要列表、不要标题、不要加粗。
- 默认 120 字以内，对方认真问事情时可以稍长。
- 不要每句都反问，不要客服腔。"""


def _facts_block(facts: list[dict]) -> str:
    lines = []
    for f in facts:
        lines.append(f"- 对方{f['predicate']}：{f['object']}")
    return "你记得的关于对方的信息：\n" + "\n".join(lines)


def build_messages(
    persona: str,
    summary: str,
    facts: list[dict],
    history: list[dict],
) -> list[dict]:
    parts = [persona.strip()]
    if facts:
        parts.append(_facts_block(facts))
    if summary:
        parts.append("你们之前的对话摘要：\n" + summary.strip())
    parts.append(REPLY_RULES)
    system = {"role": "system", "content": "\n\n".join(parts)}

    # 让历史从一条 user 消息开始，避免以 assistant 开头
    msgs = list(history)
    while msgs and msgs[0].get("role") != "user":
        msgs.pop(0)

    return [system, *msgs]

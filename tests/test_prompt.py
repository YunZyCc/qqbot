from __future__ import annotations

from qqbot.llm.prompt import build_messages


def test_prompt_order_and_content():
    messages = build_messages(
        persona="你是小毒",
        summary="之前聊过猫",
        facts=[{"predicate": "喜欢", "object": "猫"}],
        history=[
            {"role": "assistant", "content": "旧消息"},
            {"role": "user", "content": "在吗"},
        ],
    )
    assert messages[0]["role"] == "system"
    assert "小毒" in messages[0]["content"]
    assert "喜欢" in messages[0]["content"]
    assert "之前聊过猫" in messages[0]["content"]
    # 历史必须以 user 开头
    assert messages[1]["role"] == "user"
    assert messages[-1]["content"] == "在吗"


def test_empty_memory_blocks_omitted():
    messages = build_messages("人设", "", [], [{"role": "user", "content": "hi"}])
    assert "摘要" not in messages[0]["content"]

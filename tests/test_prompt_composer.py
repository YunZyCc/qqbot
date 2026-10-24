from __future__ import annotations

from qqbot.llm.prompt import build_messages
from qqbot.prompt.composer import PromptContext
from qqbot.prompt.sections import build_default_composer


def test_section_order():
    composer = build_default_composer()
    assert composer.sections() == [
        "persona",
        "self",
        "emotion",
        "facts",
        "relations",
        "images",
        "diary",
        "summary",
        "tools",
        "rules",
    ]


def test_empty_sections_skipped():
    composer = build_default_composer()
    messages = composer.compose(
        PromptContext(persona="人设", history=[{"role": "user", "content": "hi"}])
    )
    content = messages[0]["content"]
    assert content.startswith("人设")
    assert "输出要求" in content
    assert "你记得的关于对方" not in content
    assert "对话摘要" not in content
    assert messages[1]["content"] == "hi"


def test_self_state_rendered():
    composer = build_default_composer()
    messages = composer.compose(
        PromptContext(
            persona="人设",
            self_state={"mood": "平静", "focus": "聊天", "commitments": ["问他睡没睡"]},
            history=[{"role": "user", "content": "hi"}],
        )
    )
    assert "心情：平静" in messages[0]["content"]
    assert "问他睡没睡" in messages[0]["content"]


def test_relations_rendered():
    composer = build_default_composer()
    messages = composer.compose(
        PromptContext(
            persona="人设",
            relations=[{"a_qq": 1, "b_qq": 2, "relation_type": "同事", "evidence": "他说过"}],
            history=[{"role": "user", "content": "hi"}],
        )
    )
    assert "同事" in messages[0]["content"]


def test_matches_legacy_build_messages():
    facts = [{"predicate": "喜欢", "object": "猫"}]
    history = [{"role": "user", "content": "hi"}]
    legacy = build_messages("人设", "摘要", facts, history)
    composer = build_default_composer()
    new = composer.compose(
        PromptContext(persona="人设", summary="摘要", facts=facts, history=history)
    )
    assert legacy == new

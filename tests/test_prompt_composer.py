from __future__ import annotations

from qqbot.llm.prompt import build_messages
from qqbot.prompt.composer import PromptContext
from qqbot.prompt.sections import build_default_composer


def test_section_order():
    composer = build_default_composer()
    assert composer.sections() == [
        "persona",
        "chatroom",
        "evolution",
        "time",
        "self",
        "emotion",
        "facts",
        "episodes",
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


def test_focus_rendered_separately():
    composer = build_default_composer()
    messages = composer.compose(
        PromptContext(
            persona="人设",
            facts=[
                {"id": 1, "predicate": "喜欢", "object": "猫", "source": "fact"},
                {"id": 2, "predicate": "最近在", "object": "看 CS 比赛", "source": "focus"},
            ],
            history=[{"role": "user", "content": "hi"}],
        )
    )
    content = messages[0]["content"]
    assert "喜欢：猫" in content
    assert "最近在：看 CS 比赛" in content
    assert "可能已经变了" in content


def test_episodes_rendered():
    composer = build_default_composer()
    messages = composer.compose(
        PromptContext(
            persona="人设",
            episodes=[{"id": 1, "text": "用户在看 CS 比赛", "end_ts": 0.0}],
            history=[{"role": "user", "content": "hi"}],
        )
    )
    assert "用户在看 CS 比赛" in messages[0]["content"]


def test_legacy_fact_without_source_still_renders():
    composer = build_default_composer()
    messages = composer.compose(
        PromptContext(
            persona="人设",
            facts=[{"predicate": "喜欢", "object": "猫"}],
            history=[{"role": "user", "content": "hi"}],
        )
    )
    assert "喜欢：猫" in messages[0]["content"]


def test_evolution_rendered():
    composer = build_default_composer()
    messages = composer.compose(
        PromptContext(
            persona="人设",
            evolution=[
                {"kind": "style", "content": "你正在戒掉「行吧」"},
                {"kind": "address", "content": "你叫他「老板」"},
            ],
            history=[{"role": "user", "content": "hi"}],
        )
    )
    content = messages[0]["content"]
    assert "你正在戒掉「行吧」" in content
    assert "你叫他「老板」" in content
    assert "你自己长出来的" in content


def test_evolution_empty_skipped():
    composer = build_default_composer()
    messages = composer.compose(
        PromptContext(persona="人设", history=[{"role": "user", "content": "hi"}])
    )
    assert "你自己长出来的" not in messages[0]["content"]


def test_reply_slots_injected_into_rules():
    composer = build_default_composer()
    messages = composer.compose(
        PromptContext(
            persona="人设",
            reply_slots=3,
            reply_slot_chars=20,
            history=[{"role": "user", "content": "hi"}],
        )
    )
    content = messages[0]["content"]
    assert "这一轮你会发 3 条消息" in content
    assert "每条不超过 20 字" in content
    assert "总共别超过 60 字" in content
    # 有 slots 时不能再出现「默认就发一条」这种反向指令
    assert "默认就发一条" not in content


def test_no_slot_hint_when_zero():
    composer = build_default_composer()
    messages = composer.compose(
        PromptContext(persona="人设", history=[{"role": "user", "content": "hi"}])
    )
    assert "这一轮你发" not in messages[0]["content"]

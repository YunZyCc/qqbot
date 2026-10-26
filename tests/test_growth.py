from __future__ import annotations

from qqbot.memory.growth import (
    MAX_ACTIVE,
    MAX_CHARACTER_ACTIVE,
    TRAIT_SCOPE,
    active_traits,
    collect_signals,
)
from qqbot.memory.store import Store


class FakeChat:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = 0

    async def complete(self, messages, max_tokens=0, temperature=0):
        self.calls += 1
        return self.response, 1


async def _store(tmp_path) -> Store:
    store = Store(tmp_path / "growth.db", default_scope="private:1")
    await store.init()
    return store


MESSAGES = [{"role": "user", "content": "少说行吧，不好听"}]


async def test_signal_needs_evidence_before_active(tmp_path):
    store = await _store(tmp_path)
    chat = FakeChat(
        '[{"kind":"character","content":"你正在戒掉「行吧」，改说「成」","confidence":0.8}]'
    )
    await collect_signals(store, chat, MESSAGES, promote_after=3)
    rows = await store.list_traits(TRAIT_SCOPE)
    assert rows[0]["status"] == "candidate"
    assert rows[0]["evidence_count"] == 1

    # 再出现两次才生效
    await collect_signals(store, chat, MESSAGES, promote_after=3)
    await collect_signals(store, chat, MESSAGES, promote_after=3)
    rows = await store.list_traits(TRAIT_SCOPE)
    assert rows[0]["status"] == "active"
    assert rows[0]["evidence_count"] == 3
    assert rows[0]["confidence"] > 0.5
    await store.close()


async def test_same_signal_merges_instead_of_duplicating(tmp_path):
    store = await _store(tmp_path)
    chat = FakeChat(
        '[{"kind":"character","content":"你正在戒掉「行吧」","confidence":0.8}]'
    )
    for _ in range(4):
        await collect_signals(store, chat, MESSAGES, promote_after=3)
    rows = await store.list_traits(TRAIT_SCOPE)
    assert len(rows) == 1
    assert rows[0]["evidence_count"] == 4
    await store.close()


async def test_content_must_start_with_you(tmp_path):
    store = await _store(tmp_path)
    chat = FakeChat(
        '[{"kind":"character","content":"今天聊了CS比赛","confidence":0.8}]'
    )
    await collect_signals(store, chat, MESSAGES, promote_after=3)
    assert await store.list_traits(TRAIT_SCOPE) == []
    await store.close()


async def test_unknown_kind_rejected(tmp_path):
    store = await _store(tmp_path)
    chat = FakeChat('[{"kind":"weird","content":"你说得对","confidence":0.8}]')
    await collect_signals(store, chat, MESSAGES, promote_after=3)
    assert await store.list_traits(TRAIT_SCOPE) == []
    await store.close()


async def test_empty_response_is_fine(tmp_path):
    store = await _store(tmp_path)
    chat = FakeChat("[]")
    assert await collect_signals(store, chat, MESSAGES, promote_after=3) == 0
    assert await store.list_traits(TRAIT_SCOPE) == []
    await store.close()


async def test_broken_json_does_not_crash(tmp_path):
    store = await _store(tmp_path)
    chat = FakeChat("我觉得没什么变化")
    assert await collect_signals(store, chat, MESSAGES, promote_after=3) == 0
    await store.close()


async def test_active_traits_limits_character_rows(tmp_path):
    store = await _store(tmp_path)

    class FixedChat:
        def __init__(self, payload):
            self.payload = payload

        async def complete(self, messages, max_tokens=0, temperature=0):
            return self.payload, 1

    payloads = [
        '[{"kind":"character","content":"你变得更主动了"}]',
        '[{"kind":"character","content":"你的毒舌收敛了"}]',
        '[{"kind":"character","content":"你更爱撒娇了"}]',
        '[{"kind":"character","content":"你开始说「成」"}]',
    ]
    for payload in payloads:
        for _ in range(3):
            await collect_signals(store, FixedChat(payload), MESSAGES, promote_after=3)

    picked = await active_traits(store)
    characters = [row for row in picked if row["kind"] == "character"]
    assert len(characters) == MAX_CHARACTER_ACTIVE
    assert any(row["kind"] == "character" for row in picked)
    await store.close()


async def test_prune_keeps_active_under_limit(tmp_path):
    store = await _store(tmp_path)
    for index in range(MAX_ACTIVE + 4):
        await store.record_trait_signal(
            TRAIT_SCOPE, "character", f"你开始说第{index}句话", promote_after=1
        )
    active = await store.list_traits(TRAIT_SCOPE, "active", limit=200)
    await store.prune_traits(TRAIT_SCOPE, MAX_ACTIVE)
    active_after = await store.list_traits(TRAIT_SCOPE, "active", limit=200)
    assert len(active) == MAX_ACTIVE + 4
    assert len(active_after) == MAX_ACTIVE
    await store.close()


async def test_clear_traits_resets_to_baseline(tmp_path):
    store = await _store(tmp_path)
    await store.record_trait_signal(TRAIT_SCOPE, "character", "你开始说「成」", 1)
    assert await store.clear_traits(TRAIT_SCOPE) == 1
    assert await store.list_traits(TRAIT_SCOPE) == []
    await store.close()


async def test_no_messages_skips_llm(tmp_path):
    store = await _store(tmp_path)
    chat = FakeChat("[]")
    assert await collect_signals(store, chat, [], promote_after=3) == 0
    assert chat.calls == 0
    await store.close()


async def test_similar_wording_merges_via_bigram(tmp_path):
    """措辞漂移：同一件事换三种说法，应该合成一条而不是三条候选。"""
    store = await _store(tmp_path)

    class DriftChat:
        def __init__(self, payloads):
            self.payloads = payloads
            self.index = 0

        async def complete(self, messages, max_tokens=0, temperature=0):
            payload = self.payloads[self.index % len(self.payloads)]
            self.index += 1
            return payload, 1

    payloads = [
        '[{"kind":"address","content":"你叫他「老板」，他闹着让你叫爸爸，你不从"}]',
        '[{"kind":"address","content":"你叫他「老板」，他闹着让你叫爸爸，你不從"}]',
        '[{"kind":"address","content":"你叫他「老板」，他闹着让你叫爸爸，你不从"}]',
        '[{"kind":"address","content":"你叫他「老板」，他闹着让你叫爸爸，你不从"}]',
        '[{"kind":"address","content":"你叫他「老板」，他闹着让你叫爸爸，你不从"}]',
    ]
    chat = DriftChat(payloads)
    for _ in range(5):
        await collect_signals(store, chat, MESSAGES, promote_after=3)

    rows = await store.list_traits(TRAIT_SCOPE)
    assert len(rows) <= 2
    assert max(row["evidence_count"] for row in rows) >= 3
    await store.close()


async def test_static_description_rejected_by_prompt_contract(tmp_path):
    """静态描述不该成为人格（这里是代码层兜底：内容必须以「你」开头）。"""
    store = await _store(tmp_path)
    chat = FakeChat('[{"kind":"character","content":"爱用行吧接话"}]')
    await collect_signals(store, chat, MESSAGES, promote_after=3)
    assert await store.list_traits(TRAIT_SCOPE) == []
    await store.close()

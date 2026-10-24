from __future__ import annotations

import time
from types import SimpleNamespace

from qqbot.memory.emotion import EmotionTracker
from qqbot.memory.self_memory import SelfMemory
from qqbot.memory.store import Store


async def _tracker(tmp_path):
    store = Store(tmp_path / "e.db", default_scope="private:1")
    await store.init()
    settings = SimpleNamespace(
        emotion_ignored_sulk_after=2,
        emotion_sulk_hours=2.0,
        emotion_relief_minutes=30,
        emotion_fade_hours=3.0,
    )
    return store, EmotionTracker(SelfMemory(store), settings)


async def test_is_ack_patterns(tmp_path):
    store, tracker = await _tracker(tmp_path)
    assert tracker.is_ack("嗯", "在吗")
    assert tracker.is_ack("你刚才说的那个", "在吗")
    assert not tracker.is_ack("我今天考试没过", "在吗")
    await store.close()


async def test_proactive_then_ignored(tmp_path):
    store, tracker = await _tracker(tmp_path)
    await tracker.on_proactive_sent("在吗")
    state = await store_self_state(store)
    assert state["last_proactive"] == "在吗"

    # 把发送时间往前拨，超过 30 分钟窗口
    await tracker.memory.update_state(last_proactive_at=time.time() - 31 * 60)
    await tracker.evaluate_ignored()
    state = await tracker.memory.get_state()
    assert state["ignored_count"] == 1
    await store.close()


async def test_two_ignores_start_sulk(tmp_path):
    store, tracker = await _tracker(tmp_path)
    for _ in range(2):
        await tracker.memory.update_state(
            ignored_count=(await tracker.memory.get_state())["ignored_count"],
            last_proactive="在吗",
            last_proactive_at=time.time() - 31 * 60,
        )
        await tracker.evaluate_ignored()

    state = await tracker.memory.get_state()
    assert state["ignored_count"] == 2
    assert state["sulk_until"] > time.time()
    text = await tracker.prompt_text()
    assert "堵着" in text
    await store.close()


async def test_ack_relieves(tmp_path):
    store, tracker = await _tracker(tmp_path)
    await tracker.memory.update_state(
        ignored_count=2,
        sulk_until=time.time() + 3600,
        last_proactive="在吗",
        last_proactive_at=time.time() - 60,
    )
    assert await tracker.on_user_message("嗯") is True
    state = await tracker.memory.get_state()
    assert state["ignored_count"] == 1
    assert state["relief_until"] > time.time()
    await store.close()


async def store_self_state(store: Store) -> dict:
    memory = SelfMemory(store)
    return await memory.get_state()

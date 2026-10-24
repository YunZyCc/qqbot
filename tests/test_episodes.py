from __future__ import annotations

import time

from qqbot.memory.episodes import maybe_create_episode
from qqbot.memory.store import Store


class FakeChat:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = 0

    async def complete(self, messages, max_tokens=600, temperature=0.85):
        self.calls += 1
        return self.response, 1


async def _store(tmp_path) -> Store:
    store = Store(tmp_path / "e.db", default_scope="private:1")
    await store.init()
    return store


async def test_episode_created_after_threshold(tmp_path):
    store = await _store(tmp_path)
    for i in range(3):
        await store.db.execute(
            "INSERT INTO messages(scope, sender_id, role, content, msg_id, ts)"
            " VALUES(?,?,?,?,?,?)",
            ("private:1", 1, "user", f"消息{i}", None, time.time() + i),
        )
    await store.db.commit()

    chat = FakeChat("他今天说要搬家。")
    assert await maybe_create_episode(store, chat, "private:1", every=3) == 1
    episodes = await store.recent_episodes("private:1")
    assert episodes and "搬家" in episodes[-1]["text"]
    await store.close()


async def test_episode_skips_when_none(tmp_path):
    store = await _store(tmp_path)
    for i in range(2):
        await store.db.execute(
            "INSERT INTO messages(scope, sender_id, role, content, msg_id, ts)"
            " VALUES(?,?,?,?,?,?)",
            ("private:1", 1, "user", f"闲聊{i}", None, time.time() + i),
        )
    await store.db.commit()

    chat = FakeChat("NONE")
    assert await maybe_create_episode(store, chat, "private:1", every=2) == 0
    assert await store.recent_episodes("private:1") == []
    await store.close()


async def test_episode_waits_for_threshold(tmp_path):
    store = await _store(tmp_path)
    await store.db.execute(
        "INSERT INTO messages(scope, sender_id, role, content, msg_id, ts)"
        " VALUES(?,?,?,?,?,?)",
        ("private:1", 1, "user", "只有一条", None, time.time()),
    )
    await store.db.commit()

    chat = FakeChat("事件")
    assert await maybe_create_episode(store, chat, "private:1", every=20) == 0
    assert chat.calls == 0
    await store.close()

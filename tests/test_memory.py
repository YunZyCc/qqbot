from __future__ import annotations

import sqlite3

from qqbot.memory.contacts import ContactStore
from qqbot.memory.self_memory import SelfMemory
from qqbot.memory.store import Store


async def _store(tmp_path, scope: str = "private:1") -> Store:
    store = Store(tmp_path / "t.db", default_scope=scope)
    await store.init()
    return store


async def test_message_scope_isolation(tmp_path):
    store = await _store(tmp_path)
    await store.add_message("private:1", 1, "user", "喜欢猫")
    await store.add_message("private:2", 2, "user", "喜欢狗")
    assert [m["content"] for m in await store.recent_messages("private:1", 10)] == ["喜欢猫"]
    assert [m["content"] for m in await store.recent_messages("private:2", 10)] == ["喜欢狗"]
    await store.close()


async def test_fact_scope_isolation(tmp_path):
    store = await _store(tmp_path)
    await store.upsert_fact("user:1", "user", "喜欢", "猫", 0.9)
    await store.upsert_fact("user:2", "user", "喜欢", "狗", 0.9)
    assert [f["object"] for f in await store.active_facts("user:1")] == ["猫"]
    assert [f["object"] for f in await store.active_facts("user:2")] == ["狗"]
    await store.close()


async def test_upsert_supersedes_old_value(tmp_path):
    store = await _store(tmp_path)
    await store.upsert_fact("user:1", "user", "喜欢", "猫", 0.9)
    await store.upsert_fact("user:1", "user", "喜欢", "狗", 0.9)
    active = await store.active_facts("user:1")
    assert [(f["object"], f["status"]) for f in active] == [("狗", "active")]
    await store.close()


async def test_migration_from_legacy_db(tmp_path):
    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            msg_id INTEGER,
            ts REAL NOT NULL
        );
        """
    )
    conn.execute(
        "INSERT INTO messages(sender_id, role, content, ts) VALUES (1,'user','旧消息',0)"
    )
    conn.commit()
    conn.close()

    store = Store(db, default_scope="private:9")
    await store.init()
    rows = await store.recent_messages("private:9", 10)
    assert rows[0]["content"] == "旧消息"
    assert await store.get_setting("schema_version") == "7"
    await store.close()


async def test_contacts_and_relations(tmp_path):
    store = await _store(tmp_path)
    contacts = ContactStore(store)
    await contacts.upsert_contact(1, nickname="小明")
    await contacts.upsert_relation(1, 2, "同事", 0.8, "他说过")
    assert (await contacts.get_contact(1))["nickname"] == "小明"
    rels = await contacts.relations_of(2)
    assert rels and rels[0]["relation_type"] == "同事"
    await store.close()


async def test_self_memory(tmp_path):
    store = await _store(tmp_path)
    memory = SelfMemory(store)
    await memory.update_state(mood="平静", focus="聊天", commitments=["明天问他睡没睡"])
    state = await memory.get_state()
    assert state["mood"] == "平静"
    assert state["commitments"] == ["明天问他睡没睡"]

    await memory.remember("设定", "住在 QQ 里")
    picked = await memory.recall("住在哪里")
    assert picked and picked[0]["object"] == "住在 QQ 里"
    await store.close()


async def test_facts_split_into_fact_and_focus(tmp_path):
    store = await _store(tmp_path)
    await store.upsert_fact("private:1", "user", "喜欢", "猫", 0.9, source="fact")
    await store.upsert_fact("private:1", "user", "最近在", "看 CS 比赛", 0.7, source="focus")
    stable = await store.active_facts("private:1", source="fact")
    focus = await store.active_facts("private:1", source="focus")
    assert [f["object"] for f in stable] == ["猫"]
    assert [f["object"] for f in focus] == ["看 CS 比赛"]
    # 不过滤时两类都在
    assert len(await store.active_facts("private:1")) == 2
    await store.close()


async def test_focus_and_fact_do_not_collide(tmp_path):
    store = await _store(tmp_path)
    await store.upsert_fact("private:1", "user", "在做", "前端", 0.9, source="fact")
    await store.upsert_fact("private:1", "user", "在做", "看比赛", 0.7, source="focus")
    assert [f["object"] for f in await store.active_facts("private:1", "fact")] == ["前端"]
    assert [f["object"] for f in await store.active_facts("private:1", "focus")] == ["看比赛"]
    await store.close()


async def test_recent_facts_ordered(tmp_path):
    store = await _store(tmp_path)
    await store.upsert_fact("private:1", "user", "在看", "CS 比赛", 0.7, source="focus")
    await store.upsert_fact("private:1", "user", "在调试", "机器人", 0.7, source="focus")
    rows = await store.recent_facts("private:1", "focus", 5)
    assert [r["object"] for r in rows] == ["CS 比赛", "机器人"]
    await store.close()


async def test_episodes_persisted(tmp_path):
    store = await _store(tmp_path)
    await store.add_episode("private:1", 0.0, 10.0, "聊了 CS 比赛")
    await store.add_episode("private:1", 10.0, 20.0, "聊了表情包")
    eps = await store.recent_episodes("private:1", 5)
    assert [e["text"] for e in eps] == ["聊了 CS 比赛", "聊了表情包"]
    assert await store.latest_episode_end("private:1") == 20.0
    await store.close()


def test_clean_object_rewrites_self_reference():
    from qqbot.memory.facts import _clean_object

    assert _clean_object("对方说“行吧”") == "你说“行吧”"
    assert _clean_object("「助手」话太多") == "你话太多"
    assert _clean_object("猫") == "猫"


def test_normalize_kind_falls_back_on_confidence():
    from qqbot.memory.facts import _normalize_kind

    assert _normalize_kind("focus", 0.9) == "focus"
    assert _normalize_kind("fact", 0.6) == "fact"
    assert _normalize_kind("", 0.9) == "fact"
    assert _normalize_kind("", 0.6) == "focus"


async def test_merge_rolling_is_idempotent(tmp_path):
    from qqbot.memory.summary import merge_rolling

    class FakeChat:
        def __init__(self):
            self.calls = 0

        async def complete(self, messages, max_tokens=0, temperature=0):
            self.calls += 1
            return "长期印象正文", 1

    store = await _store(tmp_path)
    chat = FakeChat()
    await store.add_summary("private:1", 0.0, 10.0, "第一版会话摘要", 1, kind="session")

    assert await merge_rolling(store, chat, "private:1") is True
    assert chat.calls == 1
    # 同一份 session 再合并一次应该直接跳过，不烧 token
    assert await merge_rolling(store, chat, "private:1") is False
    assert chat.calls == 1
    await store.close()

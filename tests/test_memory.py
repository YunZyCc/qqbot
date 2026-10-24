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
    assert await store.get_setting("schema_version") == "4"
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

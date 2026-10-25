from __future__ import annotations

import datetime as dt

from qqbot.memory.diary import backfill_diaries, day_range, generate_diary
from qqbot.memory.store import Store


class FakeChat:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[list[dict]] = []

    async def complete(self, messages, max_tokens=600, temperature=0.85):
        self.calls.append(messages)
        return self.response, 1


DIARY_JSON = '{"text": "今天聊了名字的事，有点意思。", "mood": "轻松", "highlights": ["起名"]}'


async def _store(tmp_path) -> Store:
    store = Store(tmp_path / "d.db", default_scope="private:1")
    await store.init()
    return store


async def _seed_message(store: Store, scope: str, ts: float, content: str) -> None:
    await store.db.execute(
        "INSERT INTO messages(scope, sender_id, role, content, msg_id, ts)"
        " VALUES(?,?,?,?,?,?)",
        (scope, 1, "user", content, None, ts),
    )
    await store.db.commit()


async def test_review_diary_with_messages(tmp_path):
    store = await _store(tmp_path)
    yesterday = dt.date.today() - dt.timedelta(days=1)
    start, _ = day_range(yesterday)
    await _seed_message(store, "private:1", start + 3600, "在吗")

    chat = FakeChat(DIARY_JSON)
    assert await generate_diary(store, chat, yesterday, 'private:1') is True

    diary = await store.get_diary(yesterday.isoformat())
    assert diary is not None
    assert diary["source_msg_count"] == 1
    assert "起名" in diary["highlights"]
    await store.close()


async def test_solo_diary_without_messages(tmp_path):
    store = await _store(tmp_path)
    yesterday = dt.date.today() - dt.timedelta(days=1)
    chat = FakeChat(DIARY_JSON)

    assert await generate_diary(store, chat, yesterday, 'private:1') is True
    diary = await store.get_diary(yesterday.isoformat())
    assert diary is not None
    assert diary["source_msg_count"] == 0
    # 独处模式不应包含对话内容
    assert "和对方聊了" not in str(chat.calls[0])
    await store.close()


async def test_generate_is_idempotent(tmp_path):
    store = await _store(tmp_path)
    yesterday = dt.date.today() - dt.timedelta(days=1)
    chat = FakeChat(DIARY_JSON)

    assert await generate_diary(store, chat, yesterday, 'private:1') is True
    assert await generate_diary(store, chat, yesterday, 'private:1') is False
    await store.close()


async def test_backfill_writes_missing_days(tmp_path):
    store = await _store(tmp_path)
    chat = FakeChat(DIARY_JSON)
    written = await backfill_diaries(store, chat, dt.date.today(), days=3)
    assert written == 3
    await store.close()

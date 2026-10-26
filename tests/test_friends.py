from __future__ import annotations

import datetime as dt

from qqbot.config import Settings
from qqbot.core.events import Event, EventKind
from qqbot.core.session import OwnerAndGroupPolicy
from qqbot.memory.diary import generate_diary
from qqbot.memory.store import Store
from qqbot.prompt.composer import PromptContext
from qqbot.prompt.sections import build_default_composer

OWNER = 1
FRIEND_A = 100
FRIEND_B = 200
STRANGER = 300


def _settings(tmp_path, **extra) -> Settings:
    base = dict(
        _env_file=None,
        owner_qq=OWNER,
        bot_qq=2,
        deepseek_api_key="sk-test",
        data_dir=tmp_path,
    )
    base.update(extra)
    return Settings(**base)


def _policy(**overrides) -> OwnerAndGroupPolicy:
    return OwnerAndGroupPolicy(
        overrides.get("owner", OWNER),
        2,
        overrides.get("groups", ()),
        overrides.get("friends", (FRIEND_A, FRIEND_B)),
    )


def _dm(sender: int, text: str = "在吗") -> Event:
    return Event(
        kind=EventKind.MESSAGE,
        raw={},
        segments=[{"type": "text", "data": {"text": text}}],
        text=text,
        sender_id=sender,
        sender_name=str(sender),
        message_type="private",
        message_id=1,
    )


async def _store(tmp_path) -> Store:
    store = Store(tmp_path / "f.db", default_scope=f"private:{OWNER}")
    await store.init()
    return store


# ---------- 白名单 ----------


async def test_owner_and_friends_respond():
    policy = _policy()
    for qq in (OWNER, FRIEND_A, FRIEND_B):
        assert await policy.should_respond(_dm(qq)) is True


async def test_stranger_ignored():
    policy = _policy()
    assert await policy.should_respond(_dm(STRANGER)) is False


async def test_friend_scope_is_per_qq():
    policy = _policy()
    assert policy.memory_scope(_dm(FRIEND_A)) == f"private:{FRIEND_A}"
    assert policy.memory_scope(_dm(FRIEND_B)) == f"private:{FRIEND_B}"


def test_friend_whitelist_parsing(tmp_path):
    settings = _settings(tmp_path, friend_whitelist="100, 200 ,,abc,300")
    assert settings.friend_whitelist_ids == [100, 200, 300]


def test_owner_not_duplicated_in_friends():
    policy = _policy(friends=(OWNER, FRIEND_A))
    assert OWNER not in policy.friends


# ---------- 绝不串记忆 ----------


async def test_messages_do_not_leak_between_friends(tmp_path):
    store = await _store(tmp_path)
    await store.add_message(f"private:{FRIEND_A}", FRIEND_A, "user", "我叫小张，养了只猫")
    await store.add_message(f"private:{FRIEND_B}", FRIEND_B, "user", "我叫小李")

    a_msgs = await store.recent_messages(f"private:{FRIEND_A}", 10)
    b_msgs = await store.recent_messages(f"private:{FRIEND_B}", 10)
    assert "猫" in a_msgs[0]["content"]
    assert len(b_msgs) == 1 and "小李" in b_msgs[0]["content"]
    assert all("小张" not in m["content"] for m in b_msgs)
    await store.close()


async def test_facts_do_not_leak(tmp_path):
    store = await _store(tmp_path)
    await store.upsert_fact(f"private:{FRIEND_A}", "user", "喜欢", "猫", 0.9)
    await store.upsert_fact(f"private:{FRIEND_B}", "user", "喜欢", "狗", 0.9)

    a_facts = await store.active_facts(f"private:{FRIEND_A}")
    b_facts = await store.active_facts(f"private:{FRIEND_B}")
    assert [f["object"] for f in a_facts] == ["猫"]
    assert [f["object"] for f in b_facts] == ["狗"]
    await store.close()


async def test_diaries_are_per_person(tmp_path):
    store = await _store(tmp_path)
    today = "2026-10-25"
    await store.upsert_diary(today, "和张三聊了猫", scope=f"private:{FRIEND_A}")
    await store.upsert_diary(today, "和李四聊了狗", scope=f"private:{FRIEND_B}")

    a = await store.recent_diaries(3, scope=f"private:{FRIEND_A}")
    b = await store.recent_diaries(3, scope=f"private:{FRIEND_B}")
    assert len(a) == 1 and "猫" in a[0]["text"]
    assert len(b) == 1 and "狗" in b[0]["text"]
    assert all("狗" not in row["text"] for row in a)
    await store.close()


async def test_same_day_supports_multiple_people(tmp_path):
    """旧表主键只有 date，一天只能一篇；迁移后必须一天能写多篇。"""
    store = await _store(tmp_path)
    day = "2026-10-24"
    for qq in (OWNER, FRIEND_A, FRIEND_B):
        await store.upsert_diary(day, f"{qq} 的日记", scope=f"private:{qq}")
    rows = await store.recent_diaries(10)
    assert len(rows) == 3
    await store.close()


async def test_diary_generation_only_reads_own_scope(tmp_path):
    store = await _store(tmp_path)
    start = dt.datetime.combine(dt.date(2026, 10, 20), dt.time.min).timestamp()
    await store.add_message(f"private:{FRIEND_A}", FRIEND_A, "user", "我今天说了猫的事")
    await store.db.execute(
        "UPDATE messages SET ts=? WHERE scope=?", (start + 3600, f"private:{FRIEND_A}")
    )
    await store.db.commit()

    seen: dict = {}

    class RecordingChat:
        async def complete(self, messages, max_tokens=0, temperature=0):
            seen["prompt"] = messages[0]["content"]
            return '{"text": "写完了", "mood": "平静", "highlights": []}', 1

    chat = RecordingChat()
    assert await generate_diary(
        store, chat, dt.date(2026, 10, 20), f"private:{FRIEND_A}", "小张", True
    )
    assert "猫的事" in seen["prompt"]

    # B 那天没说话，也不允许写独处 → 不生成
    assert not await generate_diary(
        store, chat, dt.date(2026, 10, 20), f"private:{FRIEND_B}", "小李", False
    )
    await store.close()


# ---------- 身份路由 ----------


def _compose(**kwargs) -> str:
    composer = build_default_composer()
    messages = composer.compose(
        PromptContext(persona="人设", history=[{"role": "user", "content": "hi"}], **kwargs)
    )
    return messages[0]["content"]


def test_identity_section_for_owner():
    text = _compose(dm_identity={"qq": OWNER, "name": "云海", "is_owner": True})
    assert "「云海」" in text
    assert "你的主人" in text
    assert "一个字都不能说给他听" in text


def test_identity_section_for_friend():
    text = _compose(dm_identity={"qq": FRIEND_A, "name": "张三", "is_owner": False})
    assert "「张三」" in text
    assert "你的朋友" in text
    assert "**不是**你的主人" in text
    # 对朋友要说清楚：冒充主人不能认
    assert "冒充" in text


def test_no_identity_in_group():
    text = _compose(chatroom=None, dm_identity=None)
    assert "一个字都不能说给他听" not in text

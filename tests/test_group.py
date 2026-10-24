from __future__ import annotations

import time
from types import SimpleNamespace

from qqbot.config import Settings
from qqbot.core.events import Event, EventKind
from qqbot.core.session import OwnerAndGroupPolicy, SessionKey, SessionRegistry
from qqbot.memory.store import Store
from qqbot.modules.chat import ChatModule
from qqbot.prompt.composer import PromptContext
from qqbot.prompt.sections import build_default_composer

BOT_QQ = 999
OWNER_QQ = 1
GROUP_ID = 1083370981


def _settings(tmp_path, **overrides) -> Settings:
    params = dict(
        _env_file=None,
        owner_qq=OWNER_QQ,
        bot_qq=BOT_QQ,
        deepseek_api_key="sk-test",
        data_dir=tmp_path,
        group_whitelist=str(GROUP_ID),
        group_enabled=True,
        # 关掉后台任务里用不到的东西，避免测试打网络
        sticker_enabled=False,
        growth_enabled=False,
        summary_every=10_000,
        episode_every=10_000,
        facts_every=10_000,
    )
    params.update(overrides)
    return Settings(**params)


def _group_event(
    text: str = "今天好累啊兄弟们",
    sender: int = 222,
    name: str = "张三",
    card: str = "",
    at_bot: bool = False,
    group_id: int = GROUP_ID,
) -> Event:
    segments: list[dict] = []
    if at_bot:
        segments.append({"type": "at", "data": {"qq": str(BOT_QQ)}})
    segments.append({"type": "text", "data": {"text": text}})
    return Event(
        kind=EventKind.MESSAGE,
        raw={},
        segments=segments,
        text=text,
        sender_id=sender,
        sender_name=name,
        sender_card=card,
        message_type="group",
        group_id=group_id,
        message_id=1,
    )


def _private_event(text: str = "在吗", sender: int = OWNER_QQ) -> Event:
    return Event(
        kind=EventKind.MESSAGE,
        raw={},
        segments=[{"type": "text", "data": {"text": text}}],
        text=text,
        sender_id=sender,
        sender_name="主人",
        message_type="private",
        message_id=2,
    )


async def _store(tmp_path) -> Store:
    store = Store(tmp_path / "group.db", default_scope=f"private:{OWNER_QQ}")
    await store.init()
    return store


async def _module(tmp_path, **overrides) -> tuple[ChatModule, Store, Settings]:
    store = await _store(tmp_path)
    settings = _settings(tmp_path, **overrides)
    policy = OwnerAndGroupPolicy(OWNER_QQ, BOT_QQ, settings.group_whitelist_ids)
    ctx = SimpleNamespace(
        settings=settings,
        store=store,
        policy=policy,
        api=None,
        sessions=SessionRegistry(),
        vision=None,
        images=None,
        last_user_at=0.0,
    )
    module = ChatModule()
    module.ctx = ctx
    return module, store, settings


# ---------- 策略层 ----------


def test_memory_scope_separates_group_and_private(tmp_path):
    policy = OwnerAndGroupPolicy(OWNER_QQ, BOT_QQ, [GROUP_ID])
    assert policy.memory_scope(_private_event()) == f"private:{OWNER_QQ}"
    assert policy.memory_scope(_group_event()) == f"group:{GROUP_ID}"


def test_group_whitelist(tmp_path):
    policy = OwnerAndGroupPolicy(OWNER_QQ, BOT_QQ, [GROUP_ID])
    assert policy.group_allowed(GROUP_ID) is True
    assert policy.group_allowed(123456) is False
    assert policy.group_allowed(None) is False


def test_is_at_bot_only_matches_bot_qq(tmp_path):
    policy = OwnerAndGroupPolicy(OWNER_QQ, BOT_QQ, [GROUP_ID])
    assert policy.is_at_bot(_group_event(at_bot=True)) is True
    assert policy.is_at_bot(_group_event(at_bot=False)) is False


async def test_should_respond_private_only_owner(tmp_path):
    policy = OwnerAndGroupPolicy(OWNER_QQ, BOT_QQ, [GROUP_ID])
    assert await policy.should_respond(_private_event(sender=OWNER_QQ)) is True
    assert await policy.should_respond(_private_event(sender=333)) is False


# ---------- 四级触发 ----------


async def test_at_bot_always_replies(tmp_path):
    module, store, _ = await _module(tmp_path)
    assert await module._should_reply_in_group(_group_event(at_bot=True), "今天好累啊") is True
    await store.close()


async def test_trigger_name_replies(tmp_path):
    module, store, _ = await _module(tmp_path)
    event = _group_event(text="大肥鱼你在吗")
    assert await module._should_reply_in_group(event, "大肥鱼你在吗") is True
    await store.close()


async def test_stranger_without_trigger_does_not_reply(tmp_path):
    module, store, _ = await _module(tmp_path, group_reply_chance=0.0)
    event = _group_event()
    assert await module._should_reply_in_group(event, "今天好累啊兄弟们") is False
    await store.close()


async def test_chance_one_always_replies(tmp_path):
    module, store, _ = await _module(tmp_path, group_reply_chance=1.0)
    event = _group_event()
    assert await module._should_reply_in_group(event, "今天好累啊兄弟们") is True
    await store.close()


async def test_short_message_never_gets_chance_reply(tmp_path):
    module, store, _ = await _module(tmp_path, group_reply_chance=1.0, group_min_chars=4)
    event = _group_event(text="哈哈")
    assert await module._should_reply_in_group(event, "哈哈") is False
    await store.close()


async def test_cooldown_blocks_chance_reply(tmp_path):
    module, store, _ = await _module(tmp_path, group_reply_chance=1.0)
    await store.set_setting(f"group_last_reply:{GROUP_ID}", str(time.time()))
    event = _group_event()
    assert await module._should_reply_in_group(event, "今天好累啊兄弟们") is False
    await store.close()


async def test_cooldown_does_not_block_at_bot(tmp_path):
    module, store, _ = await _module(tmp_path, group_reply_chance=0.0)
    await store.set_setting(f"group_last_reply:{GROUP_ID}", str(time.time()))
    event = _group_event(at_bot=True)
    assert await module._should_reply_in_group(event, "你今天好累啊") is True
    await store.close()


# ---------- 活跃期：回了就继续聊 ----------


async def test_active_window_keeps_replyting(tmp_path):
    module, store, _ = await _module(tmp_path, group_reply_chance=0.0)
    await module._open_active_window(GROUP_ID)
    event = _group_event(text="今天好累啊兄弟们")
    # 没 @ 没叫名字，但因为刚回过话，仍然会接
    assert await module._should_reply_in_group(event, "今天好累啊兄弟们") is True
    await store.close()


async def test_active_window_expires(tmp_path):
    module, store, settings = await _module(tmp_path, group_reply_chance=0.0)
    await store.set_setting(f"group_active_until:{GROUP_ID}", str(time.time() - 5))
    event = _group_event(text="今天好累啊兄弟们")
    assert await module._should_reply_in_group(event, "今天好累啊兄弟们") is False
    await store.close()


async def test_open_active_window_sets_both_timestamps(tmp_path):
    module, store, settings = await _module(tmp_path)
    await module._open_active_window(GROUP_ID)
    until = float(await store.get_setting(f"group_active_until:{GROUP_ID}", "0"))
    last = float(await store.get_setting(f"group_last_reply:{GROUP_ID}", "0"))
    assert until > time.time()
    assert last > 0
    await store.close()


# ---------- 群成员记忆 ----------


async def test_group_member_recorded(tmp_path):
    store = await _store(tmp_path)
    await store.touch_group_member(GROUP_ID, 222, "张三", "小张")
    await store.touch_group_member(GROUP_ID, 222, "张三", "小张")
    members = await store.list_group_members(GROUP_ID)
    assert len(members) == 1
    assert members[0]["msg_count"] == 2
    assert members[0]["card"] == "小张"
    await store.close()


async def test_group_members_isolated_by_group(tmp_path):
    store = await _store(tmp_path)
    await store.touch_group_member(GROUP_ID, 222, "张三")
    await store.touch_group_member(999999, 333, "李四")
    assert [m["qq"] for m in await store.list_group_members(GROUP_ID)] == [222]
    assert [m["qq"] for m in await store.list_group_members(999999)] == [333]
    await store.close()


async def test_group_member_nickname_updates_but_never_cleared(tmp_path):
    store = await _store(tmp_path)
    await store.touch_group_member(GROUP_ID, 222, "张三")
    await store.touch_group_member(GROUP_ID, 222, "")  # 没带昵称时不清空旧值
    members = await store.list_group_members(GROUP_ID)
    assert members[0]["nickname"] == "张三"
    await store.close()


# ---------- 消息隔离 ----------


async def test_group_message_not_visible_in_private_scope(tmp_path):
    module, store, _ = await _module(tmp_path, group_reply_chance=0.0)
    await module._handle_group(_group_event(text="群里说的话"))
    group_msgs = await store.recent_messages(f"group:{GROUP_ID}", 10)
    private_msgs = await store.recent_messages(f"private:{OWNER_QQ}", 10)
    assert any("群里说的话" in m["content"] for m in group_msgs)
    assert private_msgs == []
    await store.close()


async def test_group_message_has_speaker_prefix(tmp_path):
    module, store, _ = await _module(tmp_path, group_reply_chance=0.0)
    await module._handle_group(_group_event(text="今天好累", name="张三", card="小张"))
    msgs = await store.recent_messages(f"group:{GROUP_ID}", 5)
    assert msgs[0]["content"] == "小张：今天好累"
    await store.close()


async def test_non_whitelisted_group_ignored(tmp_path):
    module, store, _ = await _module(tmp_path, group_reply_chance=1.0)
    await module._handle_group(_group_event(group_id=123456))
    assert await store.recent_messages("group:123456", 10) == []
    await store.close()


# ---------- prompt 渲染 ----------


def _composer_text(**kwargs) -> str:
    composer = build_default_composer()
    messages = composer.compose(
        PromptContext(persona="人设", history=[{"role": "user", "content": "hi"}], **kwargs)
    )
    return messages[0]["content"]


def test_chatroom_section_rendered_in_group():
    text = _composer_text(
        chatroom={
            "group_id": GROUP_ID,
            "speaker_qq": 222,
            "speaker_name": "张三",
            "is_owner": False,
            "members": [
                {"qq": 222, "nickname": "张三", "card": "小张"},
                {"qq": 333, "nickname": "李四", "card": ""},
            ],
        }
    )
    assert "大肥鱼" in text
    assert "张三" in text
    assert "不是你的主人" in text
    assert "不要提你和主人私聊里的事" in text
    assert "李四" in text


def test_chatroom_section_absent_in_private():
    text = _composer_text(chatroom=None)
    assert "大肥鱼" not in text
    assert "群聊规矩" not in text


def test_chatroom_section_marks_owner():
    text = _composer_text(
        chatroom={
            "group_id": GROUP_ID,
            "speaker_qq": OWNER_QQ,
            "speaker_name": "主人",
            "is_owner": True,
            "members": [],
        }
    )
    assert "是你的主人" in text


# ---------- 发送分流 ----------


class FakeAPI:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def send_private_msg(self, user_id: int, message: str):
        self.calls.append(("private", user_id, message))

    async def send_group_msg(self, group_id: int, message: str):
        self.calls.append(("group", group_id, message))


class FakeRuntime:
    def __init__(self, text: str) -> None:
        self.text = text
        self.last_tools: list[str] = []

    async def run(self, messages, scope: str = ""):
        return self.text, 1


class FakeLLM:
    async def complete(self, *args, **kwargs):
        return "", 1


class FakeRetriever:
    async def recall_all(self, scope, query, k, ep_k=3):
        return {"facts": [], "episodes": []}

    async def recall(self, scope, query, k):
        return []


class FakeContacts:
    async def relations_of(self, qq):
        return []


class FakeSelfMemory:
    async def get_state(self):
        return {}


async def test_group_reply_sends_to_group(tmp_path):
    from qqbot.prompt.sections import build_default_composer

    store = await _store(tmp_path)
    settings = _settings(
        tmp_path, reply_delay_enabled=False, group_reply_chance=1.0
    )
    policy = OwnerAndGroupPolicy(OWNER_QQ, BOT_QQ, settings.group_whitelist_ids)
    api = FakeAPI()
    ctx = SimpleNamespace(
        settings=settings,
        store=store,
        policy=policy,
        api=api,
        sessions=SessionRegistry(),
        vision=None,
        images=None,
        last_user_at=0.0,
        emotion=None,
        runtime=FakeRuntime("好呀|||真的"),
        prompt=build_default_composer(),
        persona="人设",
        retriever=FakeRetriever(),
        contacts=FakeContacts(),
        self_memory=FakeSelfMemory(),
        search=None,
        sticker_kit=None,
        stickers=None,
        vector=None,
        llm=FakeLLM(),
    )
    module = ChatModule()
    module.ctx = ctx

    event = _group_event(text="今天真好啊")
    await module._handle_group(event)

    assert api.calls, "应该发了消息"
    assert api.calls[0][0] == "group"
    assert api.calls[0][1] == GROUP_ID
    await store.close()


async def test_private_reply_sends_to_private(tmp_path):
    from qqbot.prompt.sections import build_default_composer

    store = await _store(tmp_path)
    settings = _settings(tmp_path, reply_delay_enabled=False)
    policy = OwnerAndGroupPolicy(OWNER_QQ, BOT_QQ, settings.group_whitelist_ids)
    api = FakeAPI()
    ctx = SimpleNamespace(
        settings=settings,
        store=store,
        policy=policy,
        api=api,
        sessions=SessionRegistry(),
        vision=None,
        images=None,
        last_user_at=0.0,
        emotion=None,
        runtime=FakeRuntime("好呀|||真的"),
        prompt=build_default_composer(),
        persona="人设",
        retriever=FakeRetriever(),
        contacts=FakeContacts(),
        self_memory=FakeSelfMemory(),
        search=None,
        sticker_kit=None,
        stickers=None,
        vector=None,
        llm=FakeLLM(),
    )
    module = ChatModule()
    module.ctx = ctx

    event = _private_event(text="今天真好啊")
    sctx = ctx.sessions.get(SessionKey("private", OWNER_QQ))
    await module._reply(event, sctx, "今天真好啊")

    assert api.calls[0][0] == "private"
    assert api.calls[0][1] == OWNER_QQ
    await store.close()

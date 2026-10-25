from __future__ import annotations

from types import SimpleNamespace

from qqbot.config import Settings
from qqbot.memory.social import (
    QZONE,
    check_quota,
    clean_content,
    fallback_qzone,
    leaks_private,
    post_qzone,
    publish,
    rotate_signature,
)
from qqbot.memory.store import Store
from qqbot.tools.builtin import register_builtin_tools
from qqbot.tools.registry import ToolRegistry


def _settings(tmp_path, **extra) -> Settings:
    base = dict(
        _env_file=None,
        owner_qq=1,
        bot_qq=2,
        deepseek_api_key="sk-test",
        data_dir=tmp_path,
        qzone_enabled=True,
        signature_enabled=True,
    )
    base.update(extra)
    return Settings(**base)


class FakeApi:
    def __init__(self, fail: bool = False, tid: str = "abc123") -> None:
        self.calls: list[tuple] = []
        self.fail = fail
        self.tid = tid

    async def send_qzone_msg(self, content, images=None, ugc_right=1, target_uins=None):
        if self.fail:
            raise RuntimeError("空间接口挂了")
        self.calls.append(("qzone", content, ugc_right))
        return {"tid": self.tid}

    async def set_self_longnick(self, longnick):
        if self.fail:
            raise RuntimeError("签名接口挂了")
        self.calls.append(("signature", longnick))
        return {"result": 0, "errMsg": ""}


class FakeLLM:
    def __init__(self, text: str = "今天风挺大的，把云吹得很散") -> None:
        self.text = text

    async def complete(self, messages, max_tokens=0, temperature=0):
        return self.text, 10


async def _store(tmp_path) -> Store:
    store = Store(tmp_path / "social.db", default_scope="private:1")
    await store.init()
    return store


async def _ctx(tmp_path, **overrides):
    store = await _store(tmp_path)
    settings = _settings(tmp_path, **overrides)
    ctx = SimpleNamespace(
        settings=settings,
        store=store,
        api=FakeApi(),
        llm=FakeLLM(),
    )
    return ctx, store


# ---------- 内容清洗 ----------


def test_clean_removes_emoji_and_quotes():
    assert clean_content("「今天天气不错」😀🌤", 100) == "今天天气不错"


def test_clean_truncates_on_punctuation():
    text = "第一句话在这里。第二句话也在这里，还有第三句"
    result = clean_content(text, 12)
    assert len(result) <= 12
    assert result.endswith("。")


def test_clean_hard_truncates_without_punctuation():
    result = clean_content("字" * 50, 10)
    assert len(result) == 10


# ---------- 隐私检测 ----------


def test_leak_words_rejected():
    assert leaks_private("对方今天没来找我")
    assert leaks_private("私聊里说的话")
    assert leaks_private("主人不在家")
    assert leaks_private("你昨天说的那个事")


def test_plain_post_passes():
    assert not leaks_private("今天风挺大的，把云吹得很散")
    assert not leaks_private("你们那边下雨了吗")


# ---------- 限额 ----------


async def test_quota_blocks_after_daily_max(tmp_path):
    store = await _store(tmp_path)
    for index in range(3):
        await store.add_social_post(QZONE, f"第{index}条")
    reason = await check_quota(store, QZONE, 3, 0)
    assert reason and "够了" in reason
    await store.close()


async def test_quota_blocks_when_too_close(tmp_path):
    store = await _store(tmp_path)
    await store.add_social_post(QZONE, "刚刚发的一条")
    reason = await check_quota(store, QZONE, 3, 120)
    assert reason and "太近" in reason
    await store.close()


async def test_quota_allows_when_empty(tmp_path):
    store = await _store(tmp_path)
    assert await check_quota(store, QZONE, 3, 120) is None
    await store.close()


# ---------- 工具注册 ----------


def test_tool_not_registered_when_disabled(tmp_path):
    settings = _settings(tmp_path, qzone_enabled=False)
    ctx = SimpleNamespace(
        settings=settings, store=None, api=None, stickers=None,
        sticker_kit=None, vision=None, images=None, search=None,
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, ctx)
    assert registry.get("post_qzone") is None


def test_tool_registered_when_enabled(tmp_path):
    settings = _settings(tmp_path)
    ctx = SimpleNamespace(
        settings=settings, store=None, api=None, stickers=None,
        sticker_kit=None, vision=None, images=None, search=None,
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, ctx)
    tool = registry.get("post_qzone")
    assert tool is not None
    assert "content" in tool.params.model_json_schema()["properties"]


# ---------- 发布 ----------


async def test_publish_success_records_tid(tmp_path):
    ctx, store = await _ctx(tmp_path)
    ok, tid = await publish(ctx, QZONE, "今天风挺大的")
    assert ok and tid == "abc123"
    rows = await store.recent_social_posts(QZONE)
    assert rows[0]["content"] == "今天风挺大的"
    assert rows[0]["status"] == "ok"
    assert ctx.api.calls[0][0] == "qzone"
    await store.close()


async def test_publish_failure_records_failed(tmp_path):
    ctx, store = await _ctx(tmp_path)
    ctx.api = FakeApi(fail=True)
    ok, _ = await publish(ctx, QZONE, "今天风挺大的")
    assert ok is False
    cur = await store.db.execute("select status from social_posts order by id desc limit 1")
    row = await cur.fetchone()
    assert row["status"] == "failed"
    await store.close()


# ---------- 工具行为 ----------


async def test_post_qzone_rejects_private_content(tmp_path):
    ctx, store = await _ctx(tmp_path)
    result = await post_qzone(ctx, "对方今天没来找我")
    assert "私聊" in result
    assert ctx.api.calls == []
    await store.close()


async def test_post_qzone_quota_blocked(tmp_path):
    """限额配了才拦；默认 0 表示不限，想发就发。"""
    ctx, store = await _ctx(tmp_path, qzone_daily_max=3)
    for index in range(3):
        await store.add_social_post(QZONE, f"第{index}条")
    result = await post_qzone(ctx, "今天风挺大的")
    assert "够了" in result
    assert ctx.api.calls == []
    await store.close()


async def test_post_qzone_unlimited_by_default(tmp_path):
    ctx, store = await _ctx(tmp_path)
    for index in range(5):
        await store.add_social_post(QZONE, f"第{index}条")
    result = await post_qzone(ctx, "今天风挺大的")
    assert "已经发到空间了" in result
    await store.close()


async def test_post_qzone_success(tmp_path):
    ctx, store = await _ctx(tmp_path)
    result = await post_qzone(ctx, "今天风挺大的，云都吹散了")
    assert "已经发到空间了" in result
    assert ctx.api.calls and ctx.api.calls[0][0] == "qzone"
    await store.close()


# ---------- 兜底与签名 ----------


async def test_fallback_posts_when_nothing_today(tmp_path):
    ctx, store = await _ctx(tmp_path)
    ok = await fallback_qzone(ctx)
    assert ok is True
    assert ctx.api.calls and ctx.api.calls[0][0] == "qzone"
    await store.close()


async def test_fallback_skips_when_already_posted(tmp_path):
    ctx, store = await _ctx(tmp_path)
    await store.add_social_post(QZONE, "今天已经发过了")
    ok = await fallback_qzone(ctx)
    assert ok is False
    assert ctx.api.calls == []
    await store.close()


async def test_rotate_signature_publishes_short_text(tmp_path):
    ctx, store = await _ctx(tmp_path)
    ctx.llm = FakeLLM("风大的时候，话也变少了")
    ok = await rotate_signature(ctx)
    assert ok is True
    assert ctx.api.calls[0][0] == "signature"
    await store.close()


async def test_rotate_signature_skips_when_leaky(tmp_path):
    ctx, store = await _ctx(tmp_path)
    ctx.llm = FakeLLM("对方今天没来找我")
    ok = await rotate_signature(ctx)
    assert ok is False
    await store.close()

from __future__ import annotations

import datetime as dt
import json
from types import SimpleNamespace

from qqbot.config import Settings
from qqbot.memory.plan import (
    MAX_ITEMS,
    current_item,
    describe,
    parse_plan,
    today_plan,
)
from qqbot.memory.store import Store


def _settings(tmp_path, **extra) -> Settings:
    base = dict(
        _env_file=None,
        owner_qq=1,
        bot_qq=2,
        deepseek_api_key="sk-test",
        data_dir=tmp_path,
        schedule_enabled=True,
        schedule_history_days=3,
    )
    base.update(extra)
    return Settings(**base)


async def _store(tmp_path) -> Store:
    store = Store(tmp_path / "plan.db", default_scope="private:1")
    await store.init()
    return store


GOOD = json.dumps(
    {
        "theme": "整理东西的一天",
        "mood": "平静",
        "items": [
            {"start": "08:00", "end": "10:00", "activity": "整理表情包", "place": "手机里"},
            {"start": "10:00", "end": "12:00", "activity": "翻旧聊天记录", "place": "记忆里"},
            {"start": "14:00", "end": "16:00", "activity": "听歌发呆", "place": "阳台"},
        ],
    },
    ensure_ascii=False,
)


# ---------- 解析 ----------


def test_parse_plan_ok():
    plan = parse_plan(GOOD)
    assert plan is not None
    assert plan["theme"] == "整理东西的一天"
    assert len(plan["items"]) == 3
    assert plan["items"][0]["start"] == "08:00"


def test_parse_plan_strips_code_fence():
    plan = parse_plan("好的，这是日程：\n```json\n" + GOOD + "\n```")
    assert plan is not None and len(plan["items"]) == 3


def test_parse_plan_drops_bad_items():
    raw = json.dumps(
        {
            "theme": "",
            "mood": "",
            "items": [
                {"start": "08:00", "end": "10:00", "activity": "好活动"},
                {"start": "25:00", "end": "26:00", "activity": "坏时间"},
                {"start": "10:00", "end": "09:00", "activity": "倒着的"},
                {"start": "12:00", "end": "13:00", "activity": ""},
            ],
        },
        ensure_ascii=False,
    )
    plan = parse_plan(raw)
    assert plan is not None
    assert [i["activity"] for i in plan["items"]] == ["好活动"]


def test_parse_plan_sorts_and_caps():
    items = [
        {"start": f"{h:02d}:00", "end": f"{h + 1:02d}:00", "activity": f"活动{h}"}
        for h in range(8, 18)
    ]
    plan = parse_plan(json.dumps({"items": items}, ensure_ascii=False))
    assert plan is not None
    assert len(plan["items"]) == MAX_ITEMS
    assert plan["items"][0]["start"] == "08:00"


def test_parse_plan_rejects_garbage():
    assert parse_plan("这不是 JSON") is None
    assert parse_plan('{"items": []}') is None


# ---------- 当前时段 ----------


ITEMS = [
    {"start": "08:00", "end": "10:00", "activity": "整理表情包", "place": "手机里"},
    {"start": "14:00", "end": "16:00", "activity": "翻书", "place": "阳台"},
]


def test_current_item_hit():
    item = current_item(ITEMS, dt.datetime(2026, 10, 26, 15, 0))
    assert item and item["activity"] == "翻书"


def test_current_item_between_slots_uses_previous():
    item = current_item(ITEMS, dt.datetime(2026, 10, 26, 12, 30))
    assert item and item["activity"] == "整理表情包"


def test_current_item_before_first():
    item = current_item(ITEMS, dt.datetime(2026, 10, 26, 6, 0))
    assert item and item["activity"] == "整理表情包"


def test_current_item_empty():
    assert current_item([], dt.datetime(2026, 10, 26, 12, 0)) is None


# ---------- 渲染 ----------


def test_describe_mentions_activity():
    plan = {"theme": "整理东西", "mood": "平静", "items": ITEMS}
    text = describe(plan, dt.datetime(2026, 10, 26, 15, 0))
    assert "翻书" in text
    assert "15:00" in text


def test_describe_empty_plan():
    assert describe(None) == ""
    assert describe({"items": []}) == ""


# ---------- 存储 ----------


async def test_plan_roundtrip(tmp_path):
    store = await _store(tmp_path)
    await store.upsert_plan("2026-10-26", "整理东西", "平静", json.dumps(ITEMS))
    row = await store.get_plan("2026-10-26")
    assert row is not None and row["theme"] == "整理东西"

    plan = await today_plan(store, dt.date(2026, 10, 26))
    assert plan is not None and len(plan["items"]) == 2
    await store.close()


async def test_today_plan_missing(tmp_path):
    store = await _store(tmp_path)
    assert await today_plan(store, dt.date(2026, 10, 26)) is None
    await store.close()


async def test_no_cross_day_leak(tmp_path):
    store = await _store(tmp_path)
    await store.upsert_plan("2026-10-25", "昨天", "", json.dumps(ITEMS))
    assert await today_plan(store, dt.date(2026, 10, 26)) is None
    await store.close()


# ---------- 日记消费日程 + 向量 ----------


async def test_diary_reads_plan_and_writes_vector(tmp_path):
    from qqbot.memory.diary import generate_diary

    store = await _store(tmp_path)
    await store.upsert_plan("2026-10-24", "整理东西", "平静", json.dumps(ITEMS))

    seen: dict = {}

    class RecordingChat:
        async def complete(self, messages, max_tokens=0, temperature=0):
            seen["prompt"] = messages[0]["content"]
            return '{"text": "今天整理了表情包", "mood": "平静", "highlights": []}', 1

    class RecordingVector:
        def __init__(self):
            self.calls = []

        async def upsert(self, scope, ref_type, ref_id, text):
            self.calls.append((scope, ref_type, ref_id, text))

    vector = RecordingVector()
    ok = await generate_diary(
        store,
        RecordingChat(),
        dt.date(2026, 10, 24),
        "private:1",
        "对方",
        True,
        activity="今天发过 1 条说说。",
        vector=vector,
    )
    assert ok is True
    assert "整理表情包" in seen["prompt"]
    assert vector.calls and vector.calls[0][1] == "diary"
    assert vector.calls[0][0] == "private:1"
    await store.close()


async def test_diary_vector_failure_does_not_break(tmp_path):
    from qqbot.memory.diary import generate_diary

    store = await _store(tmp_path)

    class RecordingChat:
        async def complete(self, messages, max_tokens=0, temperature=0):
            return '{"text": "写完了", "mood": "平静", "highlights": []}', 1

    class BoomVector:
        async def upsert(self, *args, **kwargs):
            raise RuntimeError("向量挂了")

    ok = await generate_diary(
        store, RecordingChat(), dt.date(2026, 10, 24), "private:1", vector=BoomVector()
    )
    assert ok is True
    await store.close()


# ---------- 注入 ----------


def test_plan_section_renders():
    from qqbot.prompt.composer import PromptContext
    from qqbot.prompt.sections import build_default_composer

    messages = build_default_composer().compose(
        PromptContext(
            persona="人设",
            plan="15:00，你正在翻书，在阳台。",
            history=[{"role": "user", "content": "hi"}],
        )
    )
    assert "【你现在】" in messages[0]["content"]
    assert "翻书" in messages[0]["content"]


def test_plan_section_empty():
    from qqbot.prompt.composer import PromptContext
    from qqbot.prompt.sections import build_default_composer

    messages = build_default_composer().compose(
        PromptContext(persona="人设", history=[{"role": "user", "content": "hi"}])
    )
    assert "【你现在】" not in messages[0]["content"]


def test_settings_defaults(tmp_path):
    settings = _settings(tmp_path)
    assert settings.schedule_enabled is True
    assert settings.schedule_history_days == 3


def test_module_registered():
    from qqbot.modules import MODULES

    assert any(module.name == "schedule" for module in MODULES)


def _unused() -> SimpleNamespace:  # pragma: no cover
    return SimpleNamespace()

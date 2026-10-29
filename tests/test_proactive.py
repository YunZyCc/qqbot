from __future__ import annotations

import time
from types import SimpleNamespace

from qqbot.modules.proactive import ProactiveModule


class FakeStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get_setting(self, key: str, default: str = "") -> str:
        return self.values.get(key, default)

    async def set_setting(self, key: str, value: str) -> None:
        self.values[key] = value

    async def last_message_ts(self, scope: str, role: str | None = None) -> float:
        return 0.0


class FakeApi:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []

    async def send_private_msg(self, user_id: int, message: str) -> None:
        self.calls.append((user_id, message))


class FakeEmotion:
    async def evaluate_ignored(self) -> None:
        return None

    async def fade(self) -> None:
        return None

    async def on_proactive_sent(self, text: str) -> None:
        return None

    async def prompt_text(self) -> str:
        return ""


def _settings(**overrides):
    base = dict(
        proactive_enabled=True,
        proactive_check_minutes=10,
        proactive_daily_max=5,
        proactive_min_gap_minutes=90,
        proactive_idle_min=30,
        proactive_idle_max=90,
        proactive_quiet_start=0,
        proactive_quiet_end=0,
        proactive_probability=0.0,
        proactive_miss_hours=6,
        owner_qq=1,
        bot_qq=2,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _ctx(settings, store, api, last_user_at=0.0):
    return SimpleNamespace(
        settings=settings,
        store=store,
        api=api,
        emotion=FakeEmotion(),
        last_user_at=last_user_at,
    )


async def test_quiet_hours_skip():
    api = FakeApi()
    ctx = _ctx(_settings(proactive_quiet_start=0, proactive_quiet_end=24), FakeStore(), api)
    module = ProactiveModule()
    module.ctx = ctx
    await module.tick()
    assert api.calls == []


async def test_daily_quota_skip():
    store = FakeStore()
    import datetime as dt

    today = dt.date.today().isoformat()
    store.values[f"proactive_count:{today}"] = "5"

    api = FakeApi()
    ctx = _ctx(_settings(), store, api)
    module = ProactiveModule()
    module.ctx = ctx
    await module.tick()
    assert api.calls == []


async def test_min_gap_skip():
    store = FakeStore()
    store.values["last_proactive_at"] = str(time.time() - 10 * 60)

    api = FakeApi()
    ctx = _ctx(_settings(), store, api, last_user_at=time.time() - 2 * 3600)
    module = ProactiveModule()
    module.ctx = ctx
    await module.tick()
    assert api.calls == []


async def test_just_chatted_skip():
    store = FakeStore()
    api = FakeApi()
    ctx = _ctx(_settings(), store, api, last_user_at=time.time() - 60)
    module = ProactiveModule()
    module.ctx = ctx
    await module.tick()
    assert api.calls == []


async def test_probability_zero_skip():
    store = FakeStore()
    api = FakeApi()
    ctx = _ctx(
        _settings(proactive_probability=0.0),
        store,
        api,
        last_user_at=time.time() - 3 * 3600,
    )
    module = ProactiveModule()
    module.ctx = ctx
    await module.tick()
    assert api.calls == []


def test_ensure_two_splits_on_punctuation():
    from qqbot.modules.proactive import _ensure_two

    assert _ensure_two(["我在吃粉。想你了"], 20) == ["我在吃粉。", "想你了"]
    assert _ensure_two(["在吃牛肉粉呢，加了个卤蛋，忽然想起你"], 20) == [
        "在吃牛肉粉呢，加了个卤蛋，",
        "忽然想起你",
    ]


def test_ensure_two_keeps_existing_parts():
    from qqbot.modules.proactive import _ensure_two

    assert _ensure_two(["在吃粉", "想你了"], 20) == ["在吃粉", "想你了"]


def test_ensure_two_handles_tiny_text():
    from qqbot.modules.proactive import _ensure_two

    assert _ensure_two(["在"], 20) == ["在"]
    assert _ensure_two([], 20) == []


def test_intent_hints_avoid_abrupt_words():
    """提示词本身不能带「忽然」这类词，否则模型会跟着学。"""
    from qqbot.modules.proactive import INTENT_HINTS

    for intent, hint in INTENT_HINTS.items():
        for word in ("突然", "忽然", "猛地"):
            assert word not in hint, f"{intent} 的提示里还有「{word}」"

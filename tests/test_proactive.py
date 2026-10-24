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

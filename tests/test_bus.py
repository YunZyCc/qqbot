from __future__ import annotations

from qqbot.core.bus import EventBus
from qqbot.core.events import EventKind
from qqbot.core.session import OwnerOnlyPolicy, SessionKey, session_from_event

_MSG = {
    "post_type": "message",
    "message_type": "private",
    "user_id": 123,
    "message_id": 1,
    "message": [{"type": "text", "data": {"text": "hi"}}],
}


async def test_dispatch_respects_priority():
    bus = EventBus()
    order: list[str] = []

    async def late(ev):
        order.append("late")

    async def early(ev):
        order.append("early")

    bus.on(EventKind.MESSAGE, late, priority=200)
    bus.on(EventKind.MESSAGE, early, priority=10)
    await bus.dispatch(_MSG)
    assert order == ["early", "late"]


async def test_dispatch_isolates_handler_errors():
    bus = EventBus()
    called: list[str] = []

    async def boom(ev):
        raise RuntimeError("boom")

    async def ok(ev):
        called.append("ok")

    bus.on(EventKind.MESSAGE, boom, priority=10)
    bus.on(EventKind.MESSAGE, ok, priority=20)
    await bus.dispatch(_MSG)
    assert called == ["ok"]


async def test_dispatch_sets_session_scope():
    bus = EventBus()
    seen: list[str | None] = []

    async def handler(ev):
        seen.append(ev.session_scope)

    bus.on(EventKind.MESSAGE, handler)
    await bus.dispatch(_MSG)
    assert seen == ["private:123"]


async def test_owner_policy():
    policy = OwnerOnlyPolicy(owner_qq=123)
    bus = EventBus()
    responded: list[bool] = []

    async def probe(ev):
        responded.append(await policy.should_respond(ev))

    bus.on(EventKind.MESSAGE, probe)
    await bus.dispatch(_MSG)
    assert responded == [True]
    assert policy.memory_scope(type("E", (), {"kind": EventKind.MESSAGE})()) == "private:123"


def test_session_key_scope():
    assert SessionKey("private", 1).scope == "private:1"
    assert SessionKey("group", 2).scope == "group:2"


def test_session_from_event_group():
    ev = type(
        "E",
        (),
        {
            "kind": EventKind.MESSAGE,
            "message_type": "group",
            "group_id": 9,
            "sender_id": 1,
        },
    )()
    assert session_from_event(ev) == SessionKey("group", 9)

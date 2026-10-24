from __future__ import annotations

from qqbot.core.events import EventKind, normalize


def test_normalize_private_message():
    ev = normalize(
        {
            "post_type": "message",
            "message_type": "private",
            "user_id": 123,
            "message_id": 9,
            "message": [{"type": "text", "data": {"text": "在吗"}}],
        }
    )
    assert ev is not None
    assert ev.kind is EventKind.MESSAGE
    assert ev.text == "在吗"
    assert ev.sender_id == 123
    assert ev.is_private


def test_normalize_group_message():
    ev = normalize(
        {
            "post_type": "message",
            "message_type": "group",
            "group_id": 456,
            "user_id": 123,
            "message": [{"type": "text", "data": {"text": "hi"}}],
        }
    )
    assert ev is not None
    assert ev.is_group
    assert ev.group_id == 456


def test_normalize_heartbeat():
    ev = normalize({"post_type": "meta_event", "meta_event_type": "heartbeat"})
    assert ev is not None
    assert ev.kind is EventKind.META


def test_normalize_unknown_returns_none():
    assert normalize({"foo": "bar"}) is None
    assert normalize({"post_type": "unknown_type"}) is None

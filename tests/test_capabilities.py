from __future__ import annotations

from types import SimpleNamespace

from qqbot.capabilities.builtin import register_builtin_actions
from qqbot.capabilities.registry import ActionRegistry


class FakeAPI:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def call(self, action: str, **params):
        self.calls.append((action, params))
        return {"ok": True}

    async def set_self_longnick(self, text: str):
        self.calls.append(("set_self_longnick", {"text": text}))
        return {"ok": True}

    async def send_qzone_msg(self, content: str, images=None):
        self.calls.append(("send_qzone_msg", {"content": content, "images": images}))
        return {"ok": True}


def _registry() -> tuple[ActionRegistry, FakeAPI]:
    api = FakeAPI()
    registry = ActionRegistry()
    register_builtin_actions(registry, SimpleNamespace(api=api))
    return registry, api


async def test_send_text_invokes_onebot():
    registry, api = _registry()
    await registry.invoke("send_text", user_id=1, text="hi")
    action, params = api.calls[0]
    assert action == "send_private_msg"
    assert params["message"] == [{"type": "text", "data": {"text": "hi"}}]


async def test_send_face_and_voice():
    registry, api = _registry()
    await registry.invoke("send_face", user_id=1, face_id=14)
    await registry.invoke("send_voice", user_id=1, file="v.mp3")
    assert api.calls[0][1]["message"][0]["type"] == "face"
    assert api.calls[1][1]["message"][0]["type"] == "record"


async def test_signature_and_qzone():
    registry, api = _registry()
    await registry.invoke("set_signature", text="今天也要开心")
    await registry.invoke("qzone_post", content="说说", images=["a.png"])
    assert api.calls[0][0] == "set_self_longnick"
    assert api.calls[1][1]["images"] == ["a.png"]


async def test_friend_request():
    registry, api = _registry()
    await registry.invoke("friend_request", flag="abc", approve=True, remark="朋友")
    assert api.calls[0][0] == "set_friend_add_request"
    assert api.calls[0][1]["approve"] is True


def test_duplicate_action_rejected():
    registry, _ = _registry()
    import pytest

    with pytest.raises(ValueError):
        register_builtin_actions(registry, SimpleNamespace(api=FakeAPI()))


async def test_token_budget_persists_per_day(tmp_path):
    """额度按自然日存库；重启不重置，跨天自然归零。"""
    from qqbot.llm.client import ChatClient
    from qqbot.memory.store import Store

    store = Store(tmp_path / "budget.db", default_scope="private:1")
    await store.init()
    client = ChatClient(store)
    original = client.budget
    try:
        client.budget = 100
        await client._add_usage(80)
        assert await client._over_budget() is False

        # 新客户端模拟重启：内存计数是 0，但库里还是 80
        restarted = ChatClient(store)
        restarted.budget = 100
        assert await restarted._over_budget() is False
        await restarted._add_usage(30)
        assert await restarted._over_budget() is True
    finally:
        client.budget = original
        await store.close()

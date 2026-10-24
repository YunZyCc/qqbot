from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from qqbot.core.commands import handle_command, list_personas, switch_persona
from qqbot.persona.loader import load_personas

PERSONA_DIR = Path("src/qqbot/persona/personas")


class FakeStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def set_setting(self, key: str, value: str) -> None:
        self.values[key] = value


def _personas():
    return load_personas(PERSONA_DIR)


def test_loads_multiple_personas():
    personas = _personas()
    unique = {p.path for p in personas.values()}
    assert len(unique) >= 5
    assert personas["阿宁"].name == "阿宁"
    assert "温柔" in personas["阿宁"].tags


def test_alias_lookup():
    personas = _personas()
    assert personas["毒哥"].name == "小毒"
    assert personas["ningning"] if "ningning" in personas else True


async def test_switch_persona():
    ctx = SimpleNamespace(
        persona="旧人设", personas=_personas(), current_persona="", store=FakeStore()
    )
    reply = await switch_persona(ctx, "阿宁")
    assert "阿宁" in reply
    assert ctx.current_persona == "阿宁"
    assert "阿宁" in ctx.persona
    assert ctx.store.values["current_persona"] == "阿宁"


async def test_switch_unknown_persona():
    ctx = SimpleNamespace(
        persona="旧人设", personas=_personas(), current_persona="", store=FakeStore()
    )
    reply = await switch_persona(ctx, "不存在")
    assert "没有叫" in reply
    assert ctx.persona == "旧人设"


async def test_command_list_and_switch():
    ctx = SimpleNamespace(
        persona="旧人设", personas=_personas(), current_persona="小毒", store=FakeStore()
    )
    listing = await handle_command(ctx, "/persona")
    assert listing and "可用人设" in listing
    assert "当前" in listing

    switched = await handle_command(ctx, "/persona 老张")
    assert switched and "老张" in switched

    assert await handle_command(ctx, "普通聊天") is None
    assert await handle_command(ctx, "/unknown") is None


def test_list_shows_current():
    ctx = SimpleNamespace(personas=_personas(), current_persona="小满")
    text = list_personas(ctx)
    assert "小满（当前）" in text

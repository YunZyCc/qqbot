from __future__ import annotations

from qqbot.app import build_context, shutdown
from qqbot.config import Settings


def _settings(tmp_path, modules: str = "chat", **extra) -> Settings:
    return Settings(
        _env_file=None,
        owner_qq=1,
        deepseek_api_key="sk-test",
        data_dir=tmp_path,
        enabled_modules=modules,
        persona_file=tmp_path / "persona.md",
        **extra,
    )


async def test_default_only_chat(tmp_path):
    ctx = await build_context(_settings(tmp_path))
    assert [m.name for m in ctx.modules] == ["chat"]
    await shutdown(ctx)


async def test_all_modules_load(tmp_path):
    modules = "chat,diary,friends,media,qzone,profile,self_memory"
    ctx = await build_context(
        _settings(
            tmp_path,
            modules,
            qzone_enabled=True,
            qzone_fallback_enabled=True,
            signature_enabled=True,
        )
    )
    names = [m.name for m in ctx.modules]
    assert names == [
        "chat",
        "diary",
        "friends",
        "media",
        "qzone",
        "profile",
        "self_memory",
    ]

    tools = [t.name for t in ctx.tools.all()]
    assert "memory_search" in tools
    assert "remember_self" in tools

    jobs = [j.id for j in ctx.scheduler.jobs()]
    assert "qzone-fallback" in jobs
    assert "signature-daily" in jobs

    await shutdown(ctx)

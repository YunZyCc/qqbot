"""打印当前真实拼装出的 prompt，用于调试人设与记忆。

用法：python scripts/print_prompt.py ["用于检索的一句话"]
不传问句就用最后一条消息当 query，和真实回复时的检索条件一致。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from qqbot.app import build_context  # noqa: E402
from qqbot.config import get_settings  # noqa: E402
from qqbot.modules.chat import build_reply_messages  # noqa: E402


async def main() -> None:
    settings = get_settings()
    ctx = await build_context(settings)
    scope = f"private:{settings.owner_qq}"
    try:
        history = await ctx.store.recent_messages(scope, settings.max_context_messages)
        query = (
            sys.argv[1]
            if len(sys.argv) > 1
            else (history[-1]["content"] if history else "在吗")
        )
        messages = await build_reply_messages(
            ctx, scope, settings.owner_qq, query, history
        )
        total = sum(len(m["content"]) for m in messages)

        facts = await ctx.store.active_facts(scope)
        focus = await ctx.store.recent_facts(scope, "focus", 5)
        episodes = await ctx.store.recent_episodes(scope, 5)

        print(f"# scope: {scope}")
        print(f"# 检索问句: {query}")
        print(f"# 消息条数: {len(messages)}，总字符数: {total}")
        print(f"# 历史: {len(history)} 条")
        print(f"# 事实: {len(facts)} 条（其中 focus {len(focus)} 条）；事件: {len(episodes)} 条")
        print()
        for i, m in enumerate(messages):
            print(f"===== [{i}] role={m['role']} len={len(m['content'])} =====")
            print(m["content"])
            print()
    finally:
        await ctx.store.close()


if __name__ == "__main__":
    asyncio.run(main())

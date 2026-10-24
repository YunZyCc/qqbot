"""打印当前真实拼装出的 prompt，用于调试人设与记忆。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from qqbot.config import get_settings  # noqa: E402
from qqbot.llm.prompt import build_messages  # noqa: E402
from qqbot.memory.retrieve import retrieve  # noqa: E402
from qqbot.memory.store import Store  # noqa: E402
from qqbot.persona.loader import load_persona  # noqa: E402


async def main() -> None:
    s = get_settings()
    scope = f"private:{s.owner_qq}"
    store = Store(s.data_dir / "qqbot.db", default_scope=scope)
    await store.init()

    history = await store.recent_messages(scope, s.max_context_messages)
    facts = await store.active_facts(scope)
    summary_row = await store.latest_summary(scope)
    summary = summary_row["text"] if summary_row else ""
    persona = load_persona(s.persona_file)

    query = history[-1]["content"] if history else ""
    picked = retrieve(query, facts, s.retrieve_top_k)

    messages = build_messages(persona, summary, picked, history)
    total = sum(len(m["content"]) for m in messages)

    print(f"# scope: {scope}")
    print(f"# 消息条数: {len(messages)}，总字符数: {total}")
    print(f"# 历史: {len(history)} 条；事实库: {len(facts)} 条；命中记忆: {len(picked)} 条")
    print(f"# 摘要: {'有，' + str(len(summary)) + ' 字' if summary else '无'}")
    print()
    for i, m in enumerate(messages):
        print(f"===== [{i}] role={m['role']} len={len(m['content'])} =====")
        print(m["content"])
        print()

    await store.close()


if __name__ == "__main__":
    asyncio.run(main())

"""诊断事实抽取：拿库里真实对话跑一次，打印模型原始返回。

用法：python scripts/check_facts.py [条数]
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from qqbot.config import get_settings  # noqa: E402
from qqbot.llm.client import ChatClient  # noqa: E402
from qqbot.memory.facts import FACT_PROMPT, _parse_items, has_signal  # noqa: E402
from qqbot.memory.store import Store  # noqa: E402


async def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    settings = get_settings()
    store = Store(Path(settings.data_dir) / "qqbot.db")
    await store.init()
    chat = ChatClient()
    try:
        cur = await store.db.execute(
            "SELECT DISTINCT scope FROM messages WHERE scope LIKE 'private:%'"
        )
        scopes = [row[0] for row in await cur.fetchall()]
        print("scopes:", scopes)
        for scope in scopes:
            recent = await store.recent_messages(scope, n)
            if not recent:
                continue
            print(f"\n{'=' * 60}\nscope={scope}  取最近 {len(recent)} 条\n{'=' * 60}")
            for m in recent:
                print(f"  [{m['role']}] {m['content'][:100]}")
            joined = "\n".join(f"{m['role']}: {m['content']}" for m in recent)
            print(f"\n信号词命中: {has_signal(joined)}")

            response, usage = await chat.complete(
                [
                    {"role": "system", "content": FACT_PROMPT},
                    {"role": "user", "content": joined[-4000:]},
                ],
                max_tokens=500,
                temperature=0.2,
            )
            print("\n--- 模型原始返回 ---")
            print(response)
            print("\n--- 解析结果 ---")
            print(_parse_items(response))
            print("usage:", usage)
    finally:
        await store.close()


if __name__ == "__main__":
    asyncio.run(main())

"""打印各 scope 的记忆统计，排查「记忆到底有没有在工作」。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from qqbot.config import get_settings  # noqa: E402
from qqbot.memory.store import Store  # noqa: E402


async def main() -> None:
    settings = get_settings()
    store = Store(
        settings.data_dir / "qqbot.db",
        default_scope=f"private:{settings.owner_qq}",
    )
    await store.init()
    db = store.db

    print(f"# 数据库: {settings.data_dir / 'qqbot.db'}")
    print(f"# schema_version: {await store.get_setting('schema_version', '?')}")

    print("\n## messages")
    cur = await db.execute(
        "SELECT scope, COUNT(*) AS n, MIN(ts) AS first_ts, MAX(ts) AS last_ts"
        " FROM messages GROUP BY scope"
    )
    for row in await cur.fetchall():
        print(f"  {row['scope']}: {row['n']} 条")

    print("\n## summaries (按 scope + type)")
    cur = await db.execute(
        "SELECT scope, type, COUNT(*) AS n, MAX(version) AS v"
        " FROM summaries GROUP BY scope, type"
    )
    for row in await cur.fetchall():
        print(f"  {row['scope']} [{row['type']}]: {row['n']} 版，最新 v{row['v']}")

    print("\n## facts (按 scope + status)")
    cur = await db.execute(
        "SELECT scope, status, COUNT(*) AS n FROM facts GROUP BY scope, status"
    )
    for row in await cur.fetchall():
        print(f"  {row['scope']} [{row['status']}]: {row['n']} 条")

    print("\n## episodes")
    cur = await db.execute("SELECT scope, COUNT(*) AS n FROM episodes GROUP BY scope")
    rows = await cur.fetchall()
    if rows:
        for row in rows:
            print(f"  {row['scope']}: {row['n']} 条")
    else:
        print("  （空）")

    print("\n## diaries")
    cur = await db.execute(
        "SELECT COUNT(*) AS n, MIN(date) AS first, MAX(date) AS last FROM diaries"
    )
    row = await cur.fetchone()
    if row and row["n"]:
        print(f"  {row['n']} 篇（{row['first']} ~ {row['last']}）")
        cur = await db.execute(
            "SELECT date, source_msg_count, substr(text, 1, 40) AS preview"
            " FROM diaries ORDER BY date DESC LIMIT 5"
        )
        for d in await cur.fetchall():
            kind = "回顾" if d["source_msg_count"] else "独处"
            print(f"  {d['date']} [{kind}] {d['preview']}…")
    else:
        print("  （空）")

    print("\n## embeddings")
    cur = await db.execute(
        "SELECT model, ref_type, COUNT(*) AS n FROM embeddings GROUP BY model, ref_type"
    )
    rows = await cur.fetchall()
    if rows:
        for row in rows:
            print(f"  {row['model']} / {row['ref_type']}: {row['n']} 条")
    else:
        print("  （空，向量检索未启用或还没写入）")

    print("\n## 抽取计数")
    for key in ("facts_attempt", "facts_empty", "facts_parse_error", "facts_written"):
        cur = await db.execute("SELECT k, v FROM settings WHERE k LIKE ?", (f"{key}%",))
        rows = await cur.fetchall()
        if rows:
            for row in rows:
                print(f"  {row['k']}: {row['v']}")

    await store.close()


if __name__ == "__main__":
    asyncio.run(main())

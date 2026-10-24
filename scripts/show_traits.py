"""查看/清理人格成长记录。

用法：
    python scripts/show_traits.py            # 看全部
    python scripts/show_traits.py --active   # 只看已生效的
    python scripts/show_traits.py --clear    # 清空，回到人设基线
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from qqbot.config import get_settings  # noqa: E402
from qqbot.memory.growth import TRAIT_SCOPE  # noqa: E402
from qqbot.memory.store import Store  # noqa: E402

KIND_LABEL = {
    "style": "说话习惯",
    "address": "称呼",
    "interest": "兴趣",
    "character": "性格",
    "lore": "梗",
}


async def main() -> None:
    args = sys.argv[1:]
    settings = get_settings()
    store = Store(Path(settings.data_dir) / "qqbot.db")
    await store.init()
    try:
        if "--clear" in args:
            removed = await store.clear_traits(TRAIT_SCOPE)
            print(f"已清空 {removed} 条人格记录，回到人设基线")
            return

        status = "active" if "--active" in args else None
        rows = await store.list_traits(TRAIT_SCOPE, status, limit=100)
        if not rows:
            print("还没有记录。多聊几天再看。")
            return

        print(f"{'状态':<10}{'类型':<10}{'证据':<6}{'置信':<6}内容")
        print("-" * 78)
        for row in rows:
            state = "已生效" if row["status"] == "active" else "候选"
            kind = KIND_LABEL.get(row["kind"], row["kind"])
            print(
                f"{state:<10}{kind:<10}{row['evidence_count']:<6}"
                f"{row['confidence']:<6.2f}{row['content']}"
            )
        active = sum(1 for row in rows if row["status"] == "active")
        print()
        print(f"共 {len(rows)} 条，其中已生效 {active} 条")
    finally:
        await store.close()


if __name__ == "__main__":
    asyncio.run(main())

from __future__ import annotations

import time

from .store import Store


class ContactStore:
    """联系人 + 好友间关系。"""

    def __init__(self, store: Store) -> None:
        self.store = store

    async def upsert_contact(
        self,
        qq: int,
        nickname: str = "",
        remark: str = "",
        tags: str = "",
        intimacy: float = 0.0,
        notes: str = "",
    ) -> None:
        now = time.time()
        await self.store.db.execute(
            "INSERT INTO contacts(qq, nickname, remark, tags, intimacy, first_seen, last_seen,"
            " notes) VALUES(?,?,?,?,?,?,?,?)"
            " ON CONFLICT(qq) DO UPDATE SET nickname=excluded.nickname,"
            " remark=excluded.remark, tags=excluded.tags, intimacy=excluded.intimacy,"
            " last_seen=excluded.last_seen, notes=excluded.notes",
            (qq, nickname, remark, tags, intimacy, now, now, notes),
        )
        await self.store.db.commit()

    async def touch(self, qq: int) -> None:
        await self.store.db.execute(
            "UPDATE contacts SET last_seen=? WHERE qq=?", (time.time(), qq)
        )
        await self.store.db.commit()

    async def get_contact(self, qq: int) -> dict | None:
        cur = await self.store.db.execute("SELECT * FROM contacts WHERE qq=?", (qq,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def list_contacts(self) -> list[dict]:
        cur = await self.store.db.execute(
            "SELECT * FROM contacts ORDER BY last_seen DESC"
        )
        return [dict(r) for r in await cur.fetchall()]

    async def upsert_relation(
        self,
        src_qq: int,
        dst_qq: int,
        rel_type: str,
        label: str = "",
        confidence: float = 0.8,
        source_qq: int = 0,
    ) -> bool:
        """写一条关系。同一对人只留一条，新证据更可信才覆盖旧的。

        主人说的话权重最高；本人自称次之；别人转述最低——防止有人自称是主人的爸爸
        就把真实关系盖掉。
        """
        if not src_qq or not dst_qq or src_qq == dst_qq:
            return False
        rel_type = (rel_type or "other").strip() or "other"

        cur = await self.store.db.execute(
            "SELECT rel_type, confidence FROM relations WHERE src_qq=? AND dst_qq=?",
            (src_qq, dst_qq),
        )
        existing = await cur.fetchone()
        if existing is not None and float(existing["confidence"]) > confidence:
            return False

        await self.store.db.execute(
            "INSERT INTO relations(src_qq, dst_qq, rel_type, label, confidence,"
            " source_qq, updated_at) VALUES(?,?,?,?,?,?,?)"
            " ON CONFLICT(src_qq, dst_qq) DO UPDATE SET"
            " rel_type=excluded.rel_type, label=excluded.label,"
            " confidence=excluded.confidence, source_qq=excluded.source_qq,"
            " updated_at=excluded.updated_at",
            (src_qq, dst_qq, rel_type, label, confidence, source_qq, time.time()),
        )
        await self.store.db.commit()
        return True

    async def relations_of(self, qq: int) -> list[dict]:
        cur = await self.store.db.execute(
            "SELECT * FROM relations WHERE src_qq=? OR dst_qq=?"
            " ORDER BY confidence DESC",
            (qq, qq),
        )
        return [dict(r) for r in await cur.fetchall()]

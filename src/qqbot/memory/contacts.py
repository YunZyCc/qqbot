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
        a_qq: int,
        b_qq: int,
        relation_type: str,
        strength: float = 0.5,
        evidence: str = "",
    ) -> None:
        now = time.time()
        await self.store.db.execute(
            "INSERT INTO relations(a_qq, b_qq, relation_type, strength, evidence, updated_at)"
            " VALUES(?,?,?,?,?,?)"
            " ON CONFLICT(a_qq, b_qq, relation_type) DO UPDATE SET"
            " strength=excluded.strength, evidence=excluded.evidence,"
            " updated_at=excluded.updated_at",
            (a_qq, b_qq, relation_type, strength, evidence, now),
        )
        await self.store.db.commit()

    async def relations_of(self, qq: int) -> list[dict]:
        cur = await self.store.db.execute(
            "SELECT * FROM relations WHERE a_qq=? OR b_qq=? ORDER BY strength DESC",
            (qq, qq),
        )
        return [dict(r) for r in await cur.fetchall()]

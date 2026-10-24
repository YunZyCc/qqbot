from __future__ import annotations

import json
import time

from .retrieve import retrieve
from .store import Store

SELF_SCOPE = "bot:self"


class SelfMemory:
    """机器人自己的记忆：心情、关注、承诺，以及关于自己的事实。"""

    def __init__(self, store: Store) -> None:
        self.store = store

    async def get_state(self) -> dict:
        cur = await self.store.db.execute("SELECT * FROM self_state WHERE id=1")
        row = await cur.fetchone()
        if row is None:
            return {"mood": "", "focus": "", "commitments": [], "updated_at": 0.0}
        return {
            "mood": row["mood"],
            "focus": row["focus"],
            "commitments": json.loads(row["commitments_json"] or "[]"),
            "updated_at": row["updated_at"],
        }

    async def update_state(
        self,
        mood: str | None = None,
        focus: str | None = None,
        commitments: list[str] | None = None,
    ) -> dict:
        state = await self.get_state()
        if mood is not None:
            state["mood"] = mood
        if focus is not None:
            state["focus"] = focus
        if commitments is not None:
            state["commitments"] = commitments
        await self.store.db.execute(
            "INSERT INTO self_state(id, mood, focus, commitments_json, updated_at)"
            " VALUES(1,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET mood=excluded.mood, focus=excluded.focus,"
            " commitments_json=excluded.commitments_json, updated_at=excluded.updated_at",
            (
                state["mood"],
                state["focus"],
                json.dumps(state["commitments"], ensure_ascii=False),
                time.time(),
            ),
        )
        await self.store.db.commit()
        return state

    async def remember(self, predicate: str, obj: str, confidence: float = 0.8) -> None:
        await self.store.upsert_fact(SELF_SCOPE, "bot", predicate, obj, confidence)

    async def recall(self, query: str, k: int = 5) -> list[dict]:
        facts = await self.store.active_facts(SELF_SCOPE)
        return retrieve(query, facts, k)

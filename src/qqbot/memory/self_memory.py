from __future__ import annotations

import json
import time

from .retrieve import retrieve
from .store import Store

SELF_SCOPE = "bot:self"

FIELDS = (
    "mood",
    "focus",
    "commitments",
    "ignored_count",
    "sulk_until",
    "relief_until",
    "last_proactive",
    "last_proactive_at",
)

DEFAULTS = {
    "mood": "",
    "focus": "",
    "commitments": [],
    "ignored_count": 0,
    "sulk_until": 0.0,
    "relief_until": 0.0,
    "last_proactive": "",
    "last_proactive_at": 0.0,
}


class SelfMemory:
    """机器人自己的记忆：心情、关注、承诺、被晾情绪，以及关于自己的事实。"""

    def __init__(self, store: Store) -> None:
        self.store = store

    async def get_state(self) -> dict:
        cur = await self.store.db.execute("SELECT * FROM self_state WHERE id=1")
        row = await cur.fetchone()
        if row is None:
            return dict(DEFAULTS)
        keys = row.keys()
        state = dict(DEFAULTS)
        columns = {
            "mood": "mood",
            "focus": "focus",
            "commitments_json": "commitments",
            "ignored_count": "ignored_count",
            "sulk_until": "sulk_until",
            "relief_until": "relief_until",
            "last_proactive": "last_proactive",
            "last_proactive_at": "last_proactive_at",
        }
        for column, field in columns.items():
            if column not in keys:
                continue
            value = row[column]
            if field == "commitments":
                try:
                    value = json.loads(value or "[]")
                except json.JSONDecodeError:
                    value = []
            state[field] = value
        return state

    async def update_state(self, **kwargs) -> dict:
        state = await self.get_state()
        for key, value in kwargs.items():
            if key in FIELDS:
                state[key] = value
        await self.store.db.execute(
            "INSERT INTO self_state(id, mood, focus, commitments_json, ignored_count,"
            " sulk_until, relief_until, last_proactive, last_proactive_at, updated_at)"
            " VALUES(1,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET mood=excluded.mood, focus=excluded.focus,"
            " commitments_json=excluded.commitments_json, ignored_count=excluded.ignored_count,"
            " sulk_until=excluded.sulk_until, relief_until=excluded.relief_until,"
            " last_proactive=excluded.last_proactive,"
            " last_proactive_at=excluded.last_proactive_at, updated_at=excluded.updated_at",
            (
                state["mood"],
                state["focus"],
                json.dumps(state["commitments"], ensure_ascii=False),
                int(state["ignored_count"]),
                float(state["sulk_until"]),
                float(state["relief_until"]),
                state["last_proactive"],
                float(state["last_proactive_at"]),
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

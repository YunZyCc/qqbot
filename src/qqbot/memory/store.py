from __future__ import annotations

import time
from pathlib import Path

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id INTEGER NOT NULL,
    role      TEXT    NOT NULL,
    content   TEXT    NOT NULL,
    msg_id    INTEGER,
    ts        REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages(ts);

CREATE TABLE IF NOT EXISTS summaries (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    start_ts REAL    NOT NULL,
    end_ts   REAL    NOT NULL,
    text     TEXT    NOT NULL,
    version  INTEGER NOT NULL DEFAULT 1,
    ts       REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS facts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    subject       TEXT    NOT NULL,
    predicate     TEXT    NOT NULL,
    object        TEXT    NOT NULL,
    confidence    REAL    NOT NULL DEFAULT 1.0,
    status        TEXT    NOT NULL DEFAULT 'active',
    source_msg_id INTEGER,
    created_at    REAL    NOT NULL,
    updated_at    REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_facts_status ON facts(status);

CREATE TABLE IF NOT EXISTS settings (
    k TEXT PRIMARY KEY,
    v TEXT NOT NULL
);
"""


class Store:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.executescript(SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Store 尚未初始化")
        return self._db

    # ---------- messages ----------
    async def add_message(
        self, sender_id: int, role: str, content: str, msg_id: int | None = None
    ) -> None:
        await self.db.execute(
            "INSERT INTO messages(sender_id, role, content, msg_id, ts) VALUES(?,?,?,?,?)",
            (sender_id, role, content, msg_id, time.time()),
        )
        await self.db.commit()

    async def recent_messages(self, limit: int) -> list[dict]:
        cur = await self.db.execute(
            "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?", (limit,)
        )
        rows = await cur.fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    async def messages_after(self, ts: float) -> list[dict]:
        cur = await self.db.execute(
            "SELECT role, content, ts FROM messages WHERE ts > ? ORDER BY id", (ts,)
        )
        return [dict(r) for r in await cur.fetchall()]

    async def count_messages(self) -> int:
        cur = await self.db.execute("SELECT COUNT(*) AS n FROM messages")
        return int((await cur.fetchone())["n"])

    # ---------- summaries ----------
    async def latest_summary(self) -> dict | None:
        cur = await self.db.execute("SELECT * FROM summaries ORDER BY id DESC LIMIT 1")
        row = await cur.fetchone()
        return dict(row) if row else None

    async def add_summary(self, start_ts: float, end_ts: float, text: str, version: int) -> None:
        await self.db.execute(
            "INSERT INTO summaries(start_ts, end_ts, text, version, ts) VALUES(?,?,?,?,?)",
            (start_ts, end_ts, text, version, time.time()),
        )
        await self.db.commit()

    # ---------- facts ----------
    async def active_facts(self) -> list[dict]:
        cur = await self.db.execute("SELECT * FROM facts WHERE status='active'")
        return [dict(r) for r in await cur.fetchall()]

    async def upsert_fact(
        self,
        subject: str,
        predicate: str,
        obj: str,
        confidence: float,
        source_msg_id: int | None = None,
    ) -> None:
        now = time.time()
        cur = await self.db.execute(
            "SELECT id, object FROM facts WHERE subject=? AND predicate=? AND status='active'",
            (subject, predicate),
        )
        row = await cur.fetchone()
        if row is None:
            await self.db.execute(
                "INSERT INTO facts(subject, predicate, object, confidence, source_msg_id,"
                " created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
                (subject, predicate, obj, confidence, source_msg_id, now, now),
            )
        elif row["object"].strip() == obj.strip():
            await self.db.execute(
                "UPDATE facts SET confidence=?, updated_at=? WHERE id=?",
                (confidence, now, row["id"]),
            )
        else:
            await self.db.execute(
                "UPDATE facts SET status='superseded', updated_at=? WHERE id=?", (now, row["id"])
            )
            await self.db.execute(
                "INSERT INTO facts(subject, predicate, object, confidence, source_msg_id,"
                " created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
                (subject, predicate, obj, confidence, source_msg_id, now, now),
            )
        await self.db.commit()

    # ---------- settings ----------
    async def get_setting(self, key: str, default: str = "") -> str:
        cur = await self.db.execute("SELECT v FROM settings WHERE k=?", (key,))
        row = await cur.fetchone()
        return row["v"] if row else default

    async def set_setting(self, key: str, value: str) -> None:
        await self.db.execute(
            "INSERT INTO settings(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
            (key, value),
        )
        await self.db.commit()

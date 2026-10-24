from __future__ import annotations

import time
from pathlib import Path

import aiosqlite

from .base import MemoryItem
from .retrieve import retrieve

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    scope     TEXT    NOT NULL DEFAULT '',
    sender_id INTEGER NOT NULL,
    role      TEXT    NOT NULL,
    content   TEXT    NOT NULL,
    msg_id    INTEGER,
    ts        REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS summaries (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    scope    TEXT    NOT NULL DEFAULT '',
    start_ts REAL    NOT NULL,
    end_ts   REAL    NOT NULL,
    text     TEXT    NOT NULL,
    version  INTEGER NOT NULL DEFAULT 1,
    ts       REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS facts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    scope         TEXT    NOT NULL DEFAULT '',
    subject       TEXT    NOT NULL,
    predicate     TEXT    NOT NULL,
    object        TEXT    NOT NULL,
    confidence    REAL    NOT NULL DEFAULT 1.0,
    status        TEXT    NOT NULL DEFAULT 'active',
    source_msg_id INTEGER,
    created_at    REAL    NOT NULL,
    updated_at    REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS contacts (
    qq         INTEGER PRIMARY KEY,
    nickname   TEXT NOT NULL DEFAULT '',
    remark     TEXT NOT NULL DEFAULT '',
    tags       TEXT NOT NULL DEFAULT '',
    intimacy   REAL NOT NULL DEFAULT 0,
    first_seen REAL NOT NULL DEFAULT 0,
    last_seen  REAL NOT NULL DEFAULT 0,
    notes      TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS relations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    a_qq          INTEGER NOT NULL,
    b_qq          INTEGER NOT NULL,
    relation_type TEXT    NOT NULL,
    strength      REAL    NOT NULL DEFAULT 0.5,
    evidence      TEXT    NOT NULL DEFAULT '',
    updated_at    REAL    NOT NULL,
    UNIQUE(a_qq, b_qq, relation_type)
);

CREATE TABLE IF NOT EXISTS self_state (
    id               INTEGER PRIMARY KEY CHECK (id = 1),
    mood             TEXT NOT NULL DEFAULT '',
    focus            TEXT NOT NULL DEFAULT '',
    commitments_json TEXT NOT NULL DEFAULT '[]',
    updated_at       REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pending_actions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    kind         TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    created_at   REAL NOT NULL,
    expires_at   REAL
);

CREATE TABLE IF NOT EXISTS settings (
    k TEXT PRIMARY KEY,
    v TEXT NOT NULL
);
"""

# 索引单独建：旧库先补列，再建引用新列的索引
INDEXES = """
CREATE INDEX IF NOT EXISTS idx_messages_scope_ts ON messages(scope, ts);
CREATE INDEX IF NOT EXISTS idx_summaries_scope ON summaries(scope, id);
CREATE INDEX IF NOT EXISTS idx_facts_status ON facts(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_facts_unique
    ON facts(scope, subject, predicate) WHERE status='active';
CREATE INDEX IF NOT EXISTS idx_relations_a ON relations(a_qq);
CREATE INDEX IF NOT EXISTS idx_relations_b ON relations(b_qq);
"""


class Store:
    """单文件 SQLite：会话、记忆、联系人、关系、自我状态、待确认动作。"""

    def __init__(self, db_path: Path, default_scope: str = "private:unknown") -> None:
        self.db_path = db_path
        self.default_scope = default_scope
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.executescript(SCHEMA)
        await self._migrate()
        await self._ensure_indexes()
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

    # ---------- migration ----------
    async def _columns(self, table: str) -> set[str]:
        cur = await self.db.execute(f"PRAGMA table_info({table})")
        return {row["name"] for row in await cur.fetchall()}

    async def _ensure_column(self, table: str, name: str, ddl: str) -> bool:
        if name in await self._columns(table):
            return False
        await self.db.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
        return True

    async def _migrate(self) -> None:
        changed = False
        changed |= await self._ensure_column("messages", "scope", "scope TEXT NOT NULL DEFAULT ''")
        changed |= await self._ensure_column("summaries", "scope", "scope TEXT NOT NULL DEFAULT ''")
        changed |= await self._ensure_column("facts", "scope", "scope TEXT NOT NULL DEFAULT ''")

        if changed:
            for table in ("messages", "summaries", "facts"):
                await self.db.execute(
                    f"UPDATE {table} SET scope=? WHERE scope=''", (self.default_scope,)
                )

        await self.set_setting("schema_version", "3")

    async def _ensure_indexes(self) -> None:
        await self.db.executescript(INDEXES)

    # ---------- messages ----------
    async def add_message(
        self,
        scope: str,
        sender_id: int,
        role: str,
        content: str,
        msg_id: int | None = None,
    ) -> None:
        await self.db.execute(
            "INSERT INTO messages(scope, sender_id, role, content, msg_id, ts)"
            " VALUES(?,?,?,?,?,?)",
            (scope, sender_id, role, content, msg_id, time.time()),
        )
        await self.db.commit()

    async def recent_messages(self, scope: str, limit: int) -> list[dict]:
        cur = await self.db.execute(
            "SELECT role, content FROM messages WHERE scope=? ORDER BY id DESC LIMIT ?",
            (scope, limit),
        )
        rows = await cur.fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    async def messages_after(self, scope: str, ts: float) -> list[dict]:
        cur = await self.db.execute(
            "SELECT role, content, ts FROM messages WHERE scope=? AND ts>? ORDER BY id",
            (scope, ts),
        )
        return [dict(r) for r in await cur.fetchall()]

    async def count_messages(self, scope: str) -> int:
        cur = await self.db.execute(
            "SELECT COUNT(*) AS n FROM messages WHERE scope=?", (scope,)
        )
        return int((await cur.fetchone())["n"])

    # ---------- summaries ----------
    async def latest_summary(self, scope: str) -> dict | None:
        cur = await self.db.execute(
            "SELECT * FROM summaries WHERE scope=? ORDER BY id DESC LIMIT 1", (scope,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def add_summary(
        self, scope: str, start_ts: float, end_ts: float, text: str, version: int
    ) -> None:
        await self.db.execute(
            "INSERT INTO summaries(scope, start_ts, end_ts, text, version, ts)"
            " VALUES(?,?,?,?,?,?)",
            (scope, start_ts, end_ts, text, version, time.time()),
        )
        await self.db.commit()

    # ---------- facts ----------
    async def active_facts(self, scope: str) -> list[dict]:
        cur = await self.db.execute(
            "SELECT * FROM facts WHERE scope=? AND status='active'", (scope,)
        )
        return [dict(r) for r in await cur.fetchall()]

    async def upsert_fact(
        self,
        scope: str,
        subject: str,
        predicate: str,
        obj: str,
        confidence: float,
        source_msg_id: int | None = None,
    ) -> None:
        now = time.time()
        cur = await self.db.execute(
            "SELECT id, object FROM facts"
            " WHERE scope=? AND subject=? AND predicate=? AND status='active'",
            (scope, subject, predicate),
        )
        row = await cur.fetchone()
        if row is None:
            await self.db.execute(
                "INSERT INTO facts(scope, subject, predicate, object, confidence,"
                " source_msg_id, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (scope, subject, predicate, obj, confidence, source_msg_id, now, now),
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
                "INSERT INTO facts(scope, subject, predicate, object, confidence,"
                " source_msg_id, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (scope, subject, predicate, obj, confidence, source_msg_id, now, now),
            )
        await self.db.commit()

    async def forget_fact(self, scope: str, fact_id: int) -> None:
        await self.db.execute(
            "UPDATE facts SET status='frozen', updated_at=? WHERE id=? AND scope=?",
            (time.time(), fact_id, scope),
        )
        await self.db.commit()

    # ---------- MemoryBackend 协议实现 ----------
    async def remember(self, item: MemoryItem) -> None:
        if item.kind == "fact":
            await self.upsert_fact(
                item.scope, "user", "note", item.content, item.confidence, item.source_id
            )
        elif item.kind == "self":
            await self.upsert_fact(
                "bot:self", "bot", "note", item.content, item.confidence, item.source_id
            )

    async def recall(self, scope: str, query: str, k: int) -> list[MemoryItem]:
        facts = await self.active_facts(scope)
        picked = retrieve(query, facts, k)
        return [
            MemoryItem(
                scope=scope,
                kind="fact",
                content=f"{f['predicate']}: {f['object']}",
                confidence=float(f.get("confidence") or 1.0),
                source_id=f.get("source_msg_id"),
                created_at=float(f.get("created_at") or 0),
            )
            for f in picked
        ]

    async def summary(self, scope: str) -> str:
        row = await self.latest_summary(scope)
        return row["text"] if row else ""

    async def forget(self, scope: str, item_id: int) -> None:
        await self.forget_fact(scope, item_id)

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

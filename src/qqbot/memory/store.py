from __future__ import annotations

import logging
import time
from pathlib import Path

import aiosqlite

from .base import MemoryItem
from .retrieve import retrieve

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    scope     TEXT    NOT NULL DEFAULT '',
    sender_id INTEGER NOT NULL,
    role      TEXT    NOT NULL,
    content   TEXT    NOT NULL,
    msg_id    INTEGER,
    source    TEXT    NOT NULL DEFAULT 'reply',
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
    src_qq     INTEGER NOT NULL,
    dst_qq     INTEGER NOT NULL,
    rel_type   TEXT    NOT NULL DEFAULT 'other',
    label      TEXT    NOT NULL DEFAULT '',
    confidence REAL    NOT NULL DEFAULT 0.8,
    source_qq  INTEGER NOT NULL DEFAULT 0,
    updated_at REAL    NOT NULL,
    PRIMARY KEY(src_qq, dst_qq)
);

CREATE TABLE IF NOT EXISTS self_state (
    id               INTEGER PRIMARY KEY CHECK (id = 1),
    mood             TEXT NOT NULL DEFAULT '',
    focus            TEXT NOT NULL DEFAULT '',
    commitments_json TEXT NOT NULL DEFAULT '[]',
    ignored_count    INTEGER NOT NULL DEFAULT 0,
    sulk_until       REAL NOT NULL DEFAULT 0,
    relief_until     REAL NOT NULL DEFAULT 0,
    last_proactive   TEXT NOT NULL DEFAULT '',
    last_proactive_at REAL NOT NULL DEFAULT 0,
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

CREATE TABLE IF NOT EXISTS episodes (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    scope    TEXT NOT NULL DEFAULT '',
    start_ts REAL NOT NULL,
    end_ts   REAL NOT NULL,
    text     TEXT NOT NULL,
    people   TEXT NOT NULL DEFAULT '',
    ts       REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS diaries (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    date             TEXT NOT NULL,
    scope            TEXT NOT NULL DEFAULT 'bot:self',
    text             TEXT NOT NULL,
    mood             TEXT NOT NULL DEFAULT '',
    highlights       TEXT NOT NULL DEFAULT '',
    source_msg_count INTEGER NOT NULL DEFAULT 0,
    created_at       REAL NOT NULL,
    UNIQUE(date, scope)
);

-- 她每天打算干什么。按天存，全局共享：她的一天是她自己的
CREATE TABLE IF NOT EXISTS daily_plans (
    date         TEXT NOT NULL,
    theme        TEXT NOT NULL DEFAULT '',
    mood         TEXT NOT NULL DEFAULT '',
    items_json   TEXT NOT NULL DEFAULT '[]',
    generated_at REAL NOT NULL,
    PRIMARY KEY(date)
);

CREATE TABLE IF NOT EXISTS embeddings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    scope      TEXT NOT NULL,
    ref_type   TEXT NOT NULL,
    ref_id     INTEGER NOT NULL,
    model      TEXT NOT NULL,
    dim        INTEGER NOT NULL,
    vector     BLOB NOT NULL,
    created_at REAL NOT NULL,
    UNIQUE(scope, ref_type, ref_id, model)
);

CREATE TABLE IF NOT EXISTS image_refs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    scope       TEXT NOT NULL,
    msg_id      INTEGER,
    sha256      TEXT NOT NULL,
    mime        TEXT NOT NULL,
    path        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS stickers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key         TEXT NOT NULL UNIQUE,
    file        TEXT NOT NULL,
    tags        TEXT NOT NULL DEFAULT '',
    emotion     TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    enabled     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS settings (
    k TEXT PRIMARY KEY,
    v TEXT NOT NULL
);

-- 发出去的社会化内容：说说、签名。用来限额、防重复、查历史
CREATE TABLE IF NOT EXISTS social_posts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT NOT NULL,
    content    TEXT NOT NULL,
    tid        TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'ok',
    created_at REAL NOT NULL
);

-- 群成员：按群隔离，记住群里出现过谁；不跨群共享
CREATE TABLE IF NOT EXISTS group_members (
    group_id   INTEGER NOT NULL,
    qq         INTEGER NOT NULL,
    nickname   TEXT NOT NULL DEFAULT '',
    card       TEXT NOT NULL DEFAULT '',
    last_seen  REAL NOT NULL,
    msg_count  INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY(group_id, qq)
);

-- 人格成长：候选信号攒够证据才升级成 active，单独存在，绝不回写 persona.md
CREATE TABLE IF NOT EXISTS persona_traits (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    scope          TEXT NOT NULL DEFAULT 'bot:self',
    kind           TEXT NOT NULL,
    content        TEXT NOT NULL,
    evidence_count INTEGER NOT NULL DEFAULT 1,
    confidence     REAL NOT NULL DEFAULT 0.5,
    status         TEXT NOT NULL DEFAULT 'candidate',
    first_seen     REAL NOT NULL,
    updated_at     REAL NOT NULL,
    UNIQUE(scope, kind, content)
);
"""

# 索引单独建：旧库先补列，再建引用新列的索引
INDEXES = """
CREATE INDEX IF NOT EXISTS idx_messages_scope_ts ON messages(scope, ts);
CREATE INDEX IF NOT EXISTS idx_summaries_scope ON summaries(scope, id);
CREATE INDEX IF NOT EXISTS idx_facts_status ON facts(status);
-- source 进唯一键：同一 predicate 下 fact 和 focus 可以共存（在做前端 / 最近在看比赛）
DROP INDEX IF EXISTS idx_facts_unique;
CREATE UNIQUE INDEX IF NOT EXISTS idx_facts_unique
    ON facts(scope, source, subject, predicate) WHERE status='active';
CREATE INDEX IF NOT EXISTS idx_relations_src ON relations(src_qq);
CREATE INDEX IF NOT EXISTS idx_episodes_scope_ts ON episodes(scope, ts);
CREATE INDEX IF NOT EXISTS idx_diaries_scope ON diaries(scope, date);
CREATE INDEX IF NOT EXISTS idx_embeddings_scope ON embeddings(scope, ref_type);
CREATE INDEX IF NOT EXISTS idx_image_refs_scope ON image_refs(scope, id);
CREATE INDEX IF NOT EXISTS idx_image_refs_hash ON image_refs(sha256);
CREATE INDEX IF NOT EXISTS idx_stickers_emotion ON stickers(emotion);
CREATE INDEX IF NOT EXISTS idx_traits_status ON persona_traits(scope, status, updated_at);
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

        await self._ensure_column(
            "summaries", "type", "type TEXT NOT NULL DEFAULT 'session'"
        )
        await self._ensure_column(
            "facts", "source", "source TEXT NOT NULL DEFAULT 'extract'"
        )
        await self._ensure_column(
            "messages", "source", "source TEXT NOT NULL DEFAULT 'reply'"
        )
        await self._ensure_column(
            "self_state", "ignored_count", "ignored_count INTEGER NOT NULL DEFAULT 0"
        )
        await self._ensure_column(
            "self_state", "sulk_until", "sulk_until REAL NOT NULL DEFAULT 0"
        )
        await self._ensure_column(
            "self_state", "relief_until", "relief_until REAL NOT NULL DEFAULT 0"
        )
        await self._ensure_column(
            "self_state", "last_proactive", "last_proactive TEXT NOT NULL DEFAULT ''"
        )
        await self._ensure_column(
            "self_state", "last_proactive_at", "last_proactive_at REAL NOT NULL DEFAULT 0"
        )

        # v6：facts.source 从 'extract' 细分成 fact / focus
        await self.db.execute("UPDATE facts SET source='fact' WHERE source='extract'")

        # v12：日记加自增 id（向量要用），并为日程做准备
        await self._migrate_diary_id()

        # v11：关系表改成枚举 + 来源可信度
        await self._migrate_relations()

        # v10：称呼/性格类特质从全局挪到主人名下，避免用到别人身上
        await self._migrate_relation_traits()

        # v9：日记按人拆，主键从 date 改成 (date, scope)
        await self._migrate_diaries()

        # v7：群聊接入，新增 group_members 表（表本身由 SCHEMA 建）
        await self.set_setting("schema_version", "12")

    @staticmethod
    def _guess_rel_type(label: str) -> str:
        """把「是云海的朋友」这种自由文本归到枚举上。"""
        text = label or ""
        for keyword, rel in (
            ("姐姐", "family"), ("哥哥", "family"), ("妹妹", "family"),
            ("弟弟", "family"), ("爸", "family"), ("妈", "family"),
            ("家人", "family"), ("父", "family"), ("母", "family"),
            ("朋友", "friend"), ("闺蜜", "friend"), ("兄弟", "friend"),
            ("恋人", "lover"), ("男友", "lover"), ("女友", "lover"),
            ("老婆", "lover"), ("老公", "lover"),
            ("同事", "colleague"), ("同学", "classmate"),
            ("主人", "master"),
        ):
            if keyword in text:
                return rel
        return "other"

    async def _migrate_diary_id(self) -> bool:
        """旧 diaries 只有 (date, scope) 复合主键，向量需要稳定的整数 id。"""
        cur = await self.db.execute("PRAGMA table_info(diaries)")
        columns = {row["name"] for row in await cur.fetchall()}
        if not columns or "id" in columns:
            return False

        log.info("迁移 diaries 表：补自增 id 供向量使用")
        await self.db.executescript(
            """
            CREATE TABLE diaries_v12 (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                date             TEXT NOT NULL,
                scope            TEXT NOT NULL DEFAULT 'bot:self',
                text             TEXT NOT NULL,
                mood             TEXT NOT NULL DEFAULT '',
                highlights       TEXT NOT NULL DEFAULT '',
                source_msg_count INTEGER NOT NULL DEFAULT 0,
                created_at       REAL NOT NULL,
                UNIQUE(date, scope)
            );
            INSERT INTO diaries_v12(date, scope, text, mood, highlights, source_msg_count, created_at)
                SELECT date, scope, text, mood, highlights, source_msg_count, created_at FROM diaries;
            DROP TABLE diaries;
            ALTER TABLE diaries_v12 RENAME TO diaries;
            """
        )
        await self.db.commit()
        return True

    async def _migrate_relations(self) -> bool:
        """旧 relations 是 (a_qq, b_qq, relation_type) 自由文本，改成枚举 + 来源。"""
        cur = await self.db.execute("PRAGMA table_info(relations)")
        columns = {row["name"] for row in await cur.fetchall()}
        if not columns or "rel_type" in columns:
            return False

        log.info("迁移 relations 表结构（枚举 + 来源可信度）")
        await self.db.execute("ALTER TABLE relations RENAME TO relations_v10")
        await self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS relations (
                src_qq     INTEGER NOT NULL,
                dst_qq     INTEGER NOT NULL,
                rel_type   TEXT    NOT NULL DEFAULT 'other',
                label      TEXT    NOT NULL DEFAULT '',
                confidence REAL    NOT NULL DEFAULT 0.8,
                source_qq  INTEGER NOT NULL DEFAULT 0,
                updated_at REAL    NOT NULL,
                PRIMARY KEY(src_qq, dst_qq)
            );
            """
        )
        cur = await self.db.execute("SELECT * FROM relations_v10")
        rows = await cur.fetchall()
        for row in rows:
            label = str(row["relation_type"] or row["evidence"] or "")
            await self.db.execute(
                "INSERT OR REPLACE INTO relations"
                "(src_qq, dst_qq, rel_type, label, confidence, source_qq, updated_at)"
                " VALUES(?,?,?,?,?,?,?)",
                (
                    int(row["a_qq"]),
                    int(row["b_qq"]),
                    self._guess_rel_type(label),
                    label,
                    float(row["strength"] or 0.8),
                    int(row["a_qq"]),
                    float(row["updated_at"] or time.time()),
                ),
            )
        await self.db.execute("DROP TABLE relations_v10")
        await self.db.commit()
        log.info("relations 迁移完成：%s 条", len(rows))
        return True

    async def _migrate_relation_traits(self) -> bool:
        """关系类特质（称呼、性格）原本全挂在 bot:self，会串到所有人身上。

        挪到主人 scope 下；说话习惯（style）仍然全局共享。
        """
        cur = await self.db.execute(
            "SELECT COUNT(*) AS n FROM persona_traits"
            " WHERE scope='bot:self' AND kind IN ('address','character')"
        )
        row = await cur.fetchone()
        count = int(row["n"]) if row else 0
        if not count:
            return False

        await self.db.execute(
            "UPDATE persona_traits SET scope=? WHERE scope='bot:self'"
            " AND kind IN ('address','character')",
            (self.default_scope,),
        )
        await self.db.commit()
        log.info("迁移 %s 条关系类特质到 %s", count, self.default_scope)
        return True

    async def _migrate_diaries(self) -> bool:
        """旧库的 diaries 主键只有 date，改成 (date, scope)；旧数据归给主人。"""
        cur = await self.db.execute("PRAGMA table_info(diaries)")
        columns = await cur.fetchall()
        primary = [row["name"] for row in columns if row["pk"]]
        if primary != ["date"]:
            return False

        log.info("迁移 diaries 主键为 (date, scope)，旧日记归到 %s", self.default_scope)
        await self.db.executescript(
            f"""
            CREATE TABLE diaries_v9 (
                date             TEXT NOT NULL,
                scope            TEXT NOT NULL DEFAULT 'bot:self',
                text             TEXT NOT NULL,
                mood             TEXT NOT NULL DEFAULT '',
                highlights       TEXT NOT NULL DEFAULT '',
                source_msg_count INTEGER NOT NULL DEFAULT 0,
                created_at       REAL NOT NULL,
                PRIMARY KEY(date, scope)
            );
            INSERT INTO diaries_v9(date, scope, text, mood, highlights, source_msg_count, created_at)
                SELECT date, CASE WHEN scope='bot:self' OR scope='' THEN '{self.default_scope}' ELSE scope END,
                       text, mood, highlights, source_msg_count, created_at
                FROM diaries;
            DROP TABLE diaries;
            ALTER TABLE diaries_v9 RENAME TO diaries;
            """
        )
        await self.db.commit()
        return True

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
        source: str = "reply",
    ) -> None:
        await self.db.execute(
            "INSERT INTO messages(scope, sender_id, role, content, msg_id, source, ts)"
            " VALUES(?,?,?,?,?,?,?)",
            (scope, sender_id, role, content, msg_id, source, time.time()),
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

    async def messages_between(
        self, start_ts: float, end_ts: float, scope: str | None = None
    ) -> list[dict]:
        if scope:
            cur = await self.db.execute(
                "SELECT scope, sender_id, role, content, ts FROM messages"
                " WHERE ts>=? AND ts<? AND scope=? ORDER BY id",
                (start_ts, end_ts, scope),
            )
        else:
            cur = await self.db.execute(
                "SELECT scope, sender_id, role, content, ts FROM messages"
                " WHERE ts>=? AND ts<? ORDER BY id",
                (start_ts, end_ts),
            )
        return [dict(r) for r in await cur.fetchall()]

    async def count_messages(self, scope: str) -> int:
        cur = await self.db.execute(
            "SELECT COUNT(*) AS n FROM messages WHERE scope=?", (scope,)
        )
        return int((await cur.fetchone())["n"])

    async def last_message_ts(self, scope: str, role: str | None = None) -> float:
        """最近一条消息的时间；重启后用它恢复空闲计时，否则主动消息永远不触发。"""
        if role:
            cur = await self.db.execute(
                "SELECT ts FROM messages WHERE scope=? AND role=? ORDER BY ts DESC LIMIT 1",
                (scope, role),
            )
        else:
            cur = await self.db.execute(
                "SELECT ts FROM messages WHERE scope=? ORDER BY ts DESC LIMIT 1", (scope,)
            )
        row = await cur.fetchone()
        return float(row["ts"]) if row else 0.0

    # ---------- summaries ----------
    async def latest_summary(self, scope: str, kind: str | None = None) -> dict | None:
        if kind:
            cur = await self.db.execute(
                "SELECT * FROM summaries WHERE scope=? AND type=? ORDER BY id DESC LIMIT 1",
                (scope, kind),
            )
        else:
            cur = await self.db.execute(
                "SELECT * FROM summaries WHERE scope=? ORDER BY id DESC LIMIT 1", (scope,)
            )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def add_summary(
        self,
        scope: str,
        start_ts: float,
        end_ts: float,
        text: str,
        version: int,
        kind: str = "session",
    ) -> int:
        cur = await self.db.execute(
            "INSERT INTO summaries(scope, start_ts, end_ts, text, version, type, ts)"
            " VALUES(?,?,?,?,?,?,?)",
            (scope, start_ts, end_ts, text, version, kind, time.time()),
        )
        await self.db.commit()
        return int(cur.lastrowid or 0)

    # ---------- facts ----------
    async def active_facts(self, scope: str, source: str | None = None) -> list[dict]:
        if source is None:
            cur = await self.db.execute(
                "SELECT * FROM facts WHERE scope=? AND status='active'", (scope,)
            )
        else:
            cur = await self.db.execute(
                "SELECT * FROM facts WHERE scope=? AND status='active' AND source=?",
                (scope, source),
            )
        return [dict(r) for r in await cur.fetchall()]

    async def recent_facts(
        self, scope: str, source: str, limit: int = 10
    ) -> list[dict]:
        """按写入时间倒序取某一类事实（focus 这种有时效的用它）。"""
        cur = await self.db.execute(
            "SELECT * FROM facts WHERE scope=? AND status='active' AND source=?"
            " ORDER BY updated_at DESC, id DESC LIMIT ?",
            (scope, source, limit),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in reversed(rows)]

    async def upsert_fact(
        self,
        scope: str,
        subject: str,
        predicate: str,
        obj: str,
        confidence: float,
        source_msg_id: int | None = None,
        source: str = "fact",
    ) -> int:
        """写入或更新事实，返回最终生效的 fact id（被忽略时返回旧 id 或 0）。"""
        now = time.time()
        new_status = "active" if confidence >= 0.6 else "pending"
        cur = await self.db.execute(
            "SELECT id, object, status FROM facts"
            " WHERE scope=? AND subject=? AND predicate=? AND source=?"
            " AND status IN ('active','pending')",
            (scope, subject, predicate, source),
        )
        row = await cur.fetchone()
        fact_id = 0
        if row is None:
            insert_cur = await self.db.execute(
                "INSERT INTO facts(scope, subject, predicate, object, confidence,"
                " status, source_msg_id, source, created_at, updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    scope,
                    subject,
                    predicate,
                    obj,
                    confidence,
                    new_status,
                    source_msg_id,
                    source,
                    now,
                    now,
                ),
            )
            fact_id = int(insert_cur.lastrowid or 0)
        elif row["object"].strip() == obj.strip():
            await self.db.execute(
                "UPDATE facts SET confidence=?, status=?, updated_at=? WHERE id=?",
                (confidence, new_status, now, row["id"]),
            )
            fact_id = int(row["id"])
        elif confidence < 0.6 and row["status"] == "active":
            # 低置信度不覆盖已有高置信事实
            await self.db.commit()
            return int(row["id"])
        else:
            await self.db.execute(
                "UPDATE facts SET status='superseded', updated_at=? WHERE id=?", (now, row["id"])
            )
            insert_cur = await self.db.execute(
                "INSERT INTO facts(scope, subject, predicate, object, confidence,"
                " status, source_msg_id, source, created_at, updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    scope,
                    subject,
                    predicate,
                    obj,
                    confidence,
                    new_status,
                    source_msg_id,
                    source,
                    now,
                    now,
                ),
            )
            fact_id = int(insert_cur.lastrowid or 0)
        await self.db.commit()
        return fact_id

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

    # ---------- episodes ----------
    async def add_episode(
        self, scope: str, start_ts: float, end_ts: float, text: str, people: str = ""
    ) -> int:
        cur = await self.db.execute(
            "INSERT INTO episodes(scope, start_ts, end_ts, text, people, ts)"
            " VALUES(?,?,?,?,?,?)",
            (scope, start_ts, end_ts, text, people, time.time()),
        )
        await self.db.commit()
        return int(cur.lastrowid or 0)

    async def latest_episode_end(self, scope: str) -> float:
        cur = await self.db.execute(
            "SELECT end_ts FROM episodes WHERE scope=? ORDER BY id DESC LIMIT 1", (scope,)
        )
        row = await cur.fetchone()
        return float(row["end_ts"]) if row else 0.0

    async def recent_episodes(self, scope: str, limit: int = 5) -> list[dict]:
        cur = await self.db.execute(
            "SELECT * FROM episodes WHERE scope=? ORDER BY id DESC LIMIT ?", (scope, limit)
        )
        rows = await cur.fetchall()
        return [dict(r) for r in reversed(rows)]

    # ---------- 日程 ----------
    async def upsert_plan(
        self, date: str, theme: str, mood: str, items_json: str
    ) -> None:
        await self.db.execute(
            "INSERT INTO daily_plans(date, theme, mood, items_json, generated_at)"
            " VALUES(?,?,?,?,?)"
            " ON CONFLICT(date) DO UPDATE SET theme=excluded.theme,"
            " mood=excluded.mood, items_json=excluded.items_json,"
            " generated_at=excluded.generated_at",
            (date, theme, mood, items_json, time.time()),
        )
        await self.db.commit()

    async def get_plan(self, date: str) -> dict | None:
        cur = await self.db.execute("SELECT * FROM daily_plans WHERE date=?", (date,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def recent_plans(self, limit: int = 3, before: str = "") -> list[dict]:
        if before:
            cur = await self.db.execute(
                "SELECT * FROM daily_plans WHERE date < ? ORDER BY date DESC LIMIT ?",
                (before, limit),
            )
        else:
            cur = await self.db.execute(
                "SELECT * FROM daily_plans ORDER BY date DESC LIMIT ?", (limit,)
            )
        rows = await cur.fetchall()
        return [dict(r) for r in reversed(rows)]

    # ---------- diaries ----------
    async def get_diary(self, date: str, scope: str = "") -> dict | None:
        if scope:
            cur = await self.db.execute(
                "SELECT * FROM diaries WHERE date=? AND scope=?", (date, scope)
            )
        else:
            cur = await self.db.execute(
                "SELECT * FROM diaries WHERE date=? ORDER BY scope LIMIT 1", (date,)
            )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def upsert_diary(
        self,
        date: str,
        text: str,
        mood: str = "",
        highlights: str = "",
        source_msg_count: int = 0,
        scope: str = "bot:self",
    ) -> int:
        """写入或更新日记，返回自增 id（向量索引要用）。"""
        await self.db.execute(
            "INSERT INTO diaries(date, scope, text, mood, highlights, source_msg_count,"
            " created_at) VALUES(?,?,?,?,?,?,?)"
            " ON CONFLICT(date, scope) DO UPDATE SET text=excluded.text,"
            " mood=excluded.mood, highlights=excluded.highlights,"
            " source_msg_count=excluded.source_msg_count, created_at=excluded.created_at",
            (date, scope, text, mood, highlights, source_msg_count, time.time()),
        )
        await self.db.commit()
        cur = await self.db.execute(
            "SELECT id FROM diaries WHERE date=? AND scope=?", (date, scope)
        )
        row = await cur.fetchone()
        return int(row["id"]) if row else 0

    async def recent_diaries(
        self, limit: int = 3, scope: str = "", before: str | None = None
    ) -> list[dict]:
        """只取某个 scope 的日记；不传 scope 才跨人取（后台统计用）。"""
        sql = "SELECT * FROM diaries"
        clauses: list[str] = []
        params: list = []
        if scope:
            clauses.append("scope=?")
            params.append(scope)
        if before:
            clauses.append("date < ?")
            params.append(before)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY date DESC LIMIT ?"
        params.append(limit)

        cur = await self.db.execute(sql, params)
        rows = await cur.fetchall()
        return [dict(r) for r in reversed(rows)]

    async def diary_dates_since(self, since: str, scope: str = "") -> set[str]:
        if scope:
            cur = await self.db.execute(
                "SELECT date FROM diaries WHERE date >= ? AND scope=?", (since, scope)
            )
        else:
            cur = await self.db.execute(
                "SELECT date FROM diaries WHERE date >= ?", (since,)
            )
        return {row["date"] for row in await cur.fetchall()}

    # ---------- embeddings ----------
    async def upsert_embedding(
        self, scope: str, ref_type: str, ref_id: int, model: str, dim: int, vector: bytes
    ) -> None:
        await self.db.execute(
            "INSERT INTO embeddings(scope, ref_type, ref_id, model, dim, vector, created_at)"
            " VALUES(?,?,?,?,?,?,?)"
            " ON CONFLICT(scope, ref_type, ref_id, model) DO UPDATE SET"
            " dim=excluded.dim, vector=excluded.vector, created_at=excluded.created_at",
            (scope, ref_type, ref_id, model, dim, vector, time.time()),
        )
        await self.db.commit()

    async def load_embeddings(self, scope: str, ref_type: str, model: str) -> list[dict]:
        cur = await self.db.execute(
            "SELECT ref_id, vector FROM embeddings"
            " WHERE scope=? AND ref_type=? AND model=?",
            (scope, ref_type, model),
        )
        return [dict(r) for r in await cur.fetchall()]

    async def delete_embeddings(self, scope: str, ref_type: str, model: str) -> None:
        await self.db.execute(
            "DELETE FROM embeddings WHERE scope=? AND ref_type=? AND model=?",
            (scope, ref_type, model),
        )
        await self.db.commit()

    # ---------- image refs ----------
    async def add_image_ref(
        self,
        scope: str,
        msg_id: int | None,
        sha256: str,
        mime: str,
        path: str,
        description: str,
    ) -> int:
        cur = await self.db.execute(
            "INSERT INTO image_refs(scope, msg_id, sha256, mime, path, description, created_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (scope, msg_id, sha256, mime, path, description, time.time()),
        )
        await self.db.commit()
        return int(cur.lastrowid or 0)

    async def recent_images(self, scope: str, limit: int = 3) -> list[dict]:
        cur = await self.db.execute(
            "SELECT * FROM image_refs WHERE scope=? ORDER BY id DESC LIMIT ?", (scope, limit)
        )
        rows = await cur.fetchall()
        return [dict(r) for r in reversed(rows)]

    async def get_image_by_hash(self, sha256: str) -> dict | None:
        cur = await self.db.execute(
            "SELECT * FROM image_refs WHERE sha256=? ORDER BY id DESC LIMIT 1", (sha256,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    # ---------- stickers ----------
    async def upsert_sticker(
        self,
        key: str,
        file: str,
        tags: str = "",
        emotion: str = "",
        description: str = "",
    ) -> int:
        await self.db.execute(
            "INSERT INTO stickers(key, file, tags, emotion, description)"
            " VALUES(?,?,?,?,?)"
            " ON CONFLICT(key) DO UPDATE SET file=excluded.file, tags=excluded.tags,"
            " emotion=excluded.emotion, description=excluded.description",
            (key, file, tags, emotion, description),
        )
        await self.db.commit()
        cur = await self.db.execute("SELECT id FROM stickers WHERE key=?", (key,))
        row = await cur.fetchone()
        return int(row["id"]) if row else 0

    async def get_sticker(self, sticker_id: int) -> dict | None:
        cur = await self.db.execute(
            "SELECT * FROM stickers WHERE id=? AND enabled=1", (sticker_id,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def search_stickers_keyword(self, query: str, k: int = 3) -> list[dict]:
        q = f"%{query.strip()}%"
        cur = await self.db.execute(
            "SELECT * FROM stickers WHERE enabled=1"
            " AND (tags LIKE ? OR emotion LIKE ? OR description LIKE ? OR key LIKE ?)"
            " LIMIT ?",
            (q, q, q, q, k),
        )
        return [dict(r) for r in await cur.fetchall()]

    async def list_stickers(self) -> list[dict]:
        cur = await self.db.execute("SELECT * FROM stickers WHERE enabled=1")
        return [dict(r) for r in await cur.fetchall()]

    # ---------- 人格成长 ----------
    async def record_trait_signal(
        self, scope: str, kind: str, content: str, promote_after: int
    ) -> dict:
        """记一次人格信号：同类内容累加证据，攒够 promote_after 次就升为 active。"""
        now = time.time()
        cur = await self.db.execute(
            "SELECT id, evidence_count, status FROM persona_traits"
            " WHERE scope=? AND kind=? AND content=?",
            (scope, kind, content),
        )
        row = await cur.fetchone()
        if row is None:
            status = "active" if promote_after <= 1 else "candidate"
            await self.db.execute(
                "INSERT INTO persona_traits(scope, kind, content, evidence_count,"
                " confidence, status, first_seen, updated_at)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (scope, kind, content, 1, 0.6 if status == "active" else 0.5,
                 status, now, now),
            )
            await self.db.commit()
            return {"created": True, "promoted": status == "active"}

        count = int(row["evidence_count"]) + 1
        status = row["status"]
        promoted = False
        if status == "candidate" and count >= promote_after:
            status = "active"
            promoted = True
        confidence = min(0.95, 0.5 + 0.1 * count)
        await self.db.execute(
            "UPDATE persona_traits SET evidence_count=?, status=?, confidence=?,"
            " updated_at=? WHERE id=?",
            (count, status, confidence, now, row["id"]),
        )
        await self.db.commit()
        return {"created": False, "promoted": promoted}

    async def list_traits(
        self, scope: str, status: str | None = None, limit: int = 50
    ) -> list[dict]:
        if status is None:
            cur = await self.db.execute(
                "SELECT * FROM persona_traits WHERE scope=?"
                " ORDER BY evidence_count DESC, updated_at DESC LIMIT ?",
                (scope, limit),
            )
        else:
            cur = await self.db.execute(
                "SELECT * FROM persona_traits WHERE scope=? AND status=?"
                " ORDER BY evidence_count DESC, updated_at DESC LIMIT ?",
                (scope, status, limit),
            )
        return [dict(r) for r in await cur.fetchall()]

    async def prune_traits(self, scope: str, keep: int) -> int:
        """active 超过上限时，把证据最少、最久没更新的一批降回候选。"""
        active = await self.list_traits(scope, "active", limit=200)
        if len(active) <= keep:
            return 0
        losers = active[keep:]
        for row in losers:
            await self.db.execute(
                "UPDATE persona_traits SET status='candidate', updated_at=?"
                " WHERE id=? AND status='active'",
                (time.time(), row["id"]),
            )
        await self.db.commit()
        return len(losers)

    async def clear_traits(self, scope: str) -> int:
        cur = await self.db.execute(
            "DELETE FROM persona_traits WHERE scope=?", (scope,)
        )
        await self.db.commit()
        return cur.rowcount

    # ---------- 说说 / 签名 ----------
    async def add_social_post(
        self, kind: str, content: str, tid: str = "", status: str = "ok"
    ) -> int:
        cur = await self.db.execute(
            "INSERT INTO social_posts(kind, content, tid, status, created_at)"
            " VALUES(?,?,?,?,?)",
            (kind, content, tid, status, time.time()),
        )
        await self.db.commit()
        return int(cur.lastrowid or 0)

    async def recent_social_posts(self, kind: str, limit: int = 5) -> list[dict]:
        cur = await self.db.execute(
            "SELECT * FROM social_posts WHERE kind=? AND status='ok'"
            " ORDER BY id DESC LIMIT ?",
            (kind, limit),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in reversed(rows)]

    async def social_posts_today(self, kind: str) -> list[dict]:
        start = time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1))
        cur = await self.db.execute(
            "SELECT * FROM social_posts WHERE kind=? AND status='ok' AND created_at>=?"
            " ORDER BY id DESC",
            (kind, start),
        )
        return [dict(r) for r in await cur.fetchall()]

    # ---------- 群成员 ----------
    async def touch_group_member(
        self, group_id: int, qq: int, nickname: str = "", card: str = ""
    ) -> None:
        """记一次群成员露面：新人插入，老人累加消息数并更新时间。"""
        now = time.time()
        await self.db.execute(
            "INSERT INTO group_members(group_id, qq, nickname, card, last_seen, msg_count)"
            " VALUES(?,?,?,?,?,1)"
            " ON CONFLICT(group_id, qq) DO UPDATE SET"
            "   nickname=CASE WHEN excluded.nickname<>'' THEN excluded.nickname ELSE group_members.nickname END,"
            "   card=CASE WHEN excluded.card<>'' THEN excluded.card ELSE group_members.card END,"
            "   last_seen=excluded.last_seen,"
            "   msg_count=group_members.msg_count + 1",
            (group_id, qq, nickname, card, now),
        )
        await self.db.commit()

    async def list_group_members(self, group_id: int, limit: int = 20) -> list[dict]:
        cur = await self.db.execute(
            "SELECT * FROM group_members WHERE group_id=?"
            " ORDER BY msg_count DESC, last_seen DESC LIMIT ?",
            (group_id, limit),
        )
        return [dict(r) for r in await cur.fetchall()]

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

    async def incr_counter(self, key: str, n: int = 1) -> int:
        cur = await self.db.execute("SELECT v FROM settings WHERE k=?", (key,))
        row = await cur.fetchone()
        try:
            value = int(row["v"]) if row else 0
        except (TypeError, ValueError):
            value = 0
        value += n
        await self.set_setting(key, str(value))
        return value

    async def counter(self, key: str) -> int:
        cur = await self.db.execute("SELECT v FROM settings WHERE k=?", (key,))
        row = await cur.fetchone()
        if row is None:
            return 0
        try:
            return int(row["v"])
        except (TypeError, ValueError):
            return 0

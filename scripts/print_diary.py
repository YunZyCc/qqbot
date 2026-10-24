"""打印最近的日记，用于人工检查。"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

db = Path("data/qqbot.db")
if len(sys.argv) > 1:
    db = Path(sys.argv[1])

conn = sqlite3.connect(db)
rows = conn.execute(
    "SELECT date, text, mood, source_msg_count FROM diaries ORDER BY date DESC LIMIT 10"
).fetchall()
for date, text, mood, count in rows:
    kind = "回顾" if count else "独处"
    print(f"=== {date} [{kind}] 心情:{mood or '—'} ===")
    print(text)
    print()

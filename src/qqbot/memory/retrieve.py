from __future__ import annotations

import math
import time

HALF_LIFE_DAYS = 21.0
ALPHA = math.log(2) / HALF_LIFE_DAYS


def _grams(text: str, n: int = 2) -> set[str]:
    text = "".join(ch for ch in text if not ch.isspace())
    if len(text) <= n:
        return {text}
    return {text[i : i + n] for i in range(len(text) - n + 1)}


def _relevance(query: str, fact_text: str) -> float:
    q = _grams(query)
    if not q:
        return 0.0
    f = _grams(fact_text)
    if not f:
        return 0.0
    hit = len(q & f)
    return hit / len(q)


def score_fact(query: str, fact: dict, now: float | None = None) -> float:
    now = now or time.time()
    fact_text = f"{fact['subject']} {fact['predicate']} {fact['object']}"
    rel = _relevance(query, fact_text)
    if rel <= 0:
        return 0.0
    age_days = max(0.0, (now - float(fact.get("updated_at") or now)) / 86400.0)
    decay = math.exp(-ALPHA * age_days)
    conf = float(fact.get("confidence") or 1.0)
    # 高置信事实不衰减
    if conf >= 0.9:
        decay = 1.0
    return 0.6 * rel + 0.3 * decay + 0.1 * conf


def retrieve(query: str, facts: list[dict], top_k: int = 5) -> list[dict]:
    scored = [(score_fact(query, f), f) for f in facts]
    scored = [x for x in scored if x[0] > 0]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [f for _, f in scored[:top_k]]

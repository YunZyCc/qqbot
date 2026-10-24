from __future__ import annotations

import time

from qqbot.memory.retrieve import retrieve, score_fact


def _fact(predicate: str, obj: str, confidence: float = 0.9, age_days: float = 0) -> dict:
    return {
        "subject": "user",
        "predicate": predicate,
        "object": obj,
        "confidence": confidence,
        "updated_at": time.time() - age_days * 86400,
    }


def test_relevant_fact_scores_higher():
    facts = [
        _fact("喜欢", "猫"),
        _fact("住在", "上海"),
    ]
    result = retrieve("你还记得我喜欢什么动物吗", facts, top_k=1)
    assert result and result[0]["object"] == "猫"


def test_irrelevant_fact_filtered():
    facts = [_fact("喜欢", "猫")]
    assert retrieve("今天天气怎么样", facts) == []


def test_high_confidence_does_not_decay():
    fresh = _fact("生日是", "3 月 5 日", confidence=0.95, age_days=0)
    old = _fact("生日是", "3 月 5 日", confidence=0.95, age_days=400)
    assert abs(score_fact("生日是", fresh) - score_fact("生日是", old)) < 1e-6


def test_low_confidence_decays():
    fresh = _fact("讨厌", "香菜", confidence=0.6, age_days=0)
    old = _fact("讨厌", "香菜", confidence=0.6, age_days=60)
    assert score_fact("讨厌香菜", fresh) > score_fact("讨厌香菜", old)

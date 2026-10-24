from __future__ import annotations

from qqbot.core.splitter import split_message


def test_short_message_not_split():
    assert split_message("在吗", 500) == ["在吗"]


def test_empty_message():
    assert split_message("   ", 500) == []


def test_long_message_respects_limit():
    text = "这是一句话。" * 200
    parts = split_message(text, 100)
    assert parts
    assert all(len(p) <= 100 for p in parts)
    assert "".join(parts).replace("\n", "") == text


def test_splits_on_sentence_boundary():
    text = "第一句话。" * 30
    parts = split_message(text, 50)
    assert all(p.endswith("。") for p in parts[:-1])

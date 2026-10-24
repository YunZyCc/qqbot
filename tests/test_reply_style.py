from __future__ import annotations

from types import SimpleNamespace

from qqbot.core.reply_style import reply_delay, segment_interval, split_reply


def test_split_by_delimiter():
    text = "今天天气真不错呀哈哈哈|||你说是不是这个道理呢"
    assert split_reply(text, 3, 500) == ["今天天气真不错呀哈哈哈", "你说是不是这个道理呢"]


def test_short_segments_merged():
    assert split_reply("好|||嗯", 3, 500) == ["好嗯"]


def test_max_segments():
    text = "|||".join(["a" * 20, "b" * 20, "c" * 20, "d" * 20])
    assert len(split_reply(text, 3, 500)) == 3


def test_single_reply_without_delimiter():
    assert split_reply("就一句话", 3, 500) == ["就一句话"]


def test_fallback_splits_sentences():
    parts = split_reply("行吧，你开心就好。要不要再来一张看看？", 3, 500)
    assert len(parts) == 2
    assert parts[0].endswith("。")


def test_delay_ranges():
    settings = SimpleNamespace(
        reply_delay_min=0.5,
        reply_delay_max=3.0,
        segment_interval_min=1.0,
        segment_interval_max=2.0,
    )
    for _ in range(50):
        assert 0.5 <= reply_delay(settings) <= 3.0
        assert 1.0 <= segment_interval(settings) <= 2.0

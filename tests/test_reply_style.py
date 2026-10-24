from __future__ import annotations

from types import SimpleNamespace

from qqbot.core.reply_style import reply_delay, segment_interval, split_reply

# 权重故意做成极端值，把「按概率抽几条」变成确定性行为，方便断言
ONE_ONLY = [100, 0, 0, 0, 0]
FIVE_ONLY = [0, 0, 0, 0, 100]


def test_split_by_delimiter():
    text = "今天天气真不错呀哈哈哈|||你说是不是这个道理呢"
    assert split_reply(text, 5, 40, FIVE_ONLY) == [
        "今天天气真不错呀哈哈哈",
        "你说是不是这个道理呢",
    ]


def test_segment_max_chars_enforced():
    text = "字" * 100
    parts = split_reply(text, 5, 40, FIVE_ONLY)
    assert parts
    assert all(len(part) <= 40 for part in parts)


def test_short_replies_not_compressed():
    """一两条是正常节奏，权重再低也不合并。"""
    text = "今天等你消息|||说真的就这点事"
    assert len(split_reply(text, 5, 40, ONE_ONLY)) == 2


def test_three_or_more_can_be_compressed():
    text = "第一句在这|||第二句在这|||第三句在这"
    merged = split_reply(text, 5, 40, ONE_ONLY)
    assert len(merged) == 2
    assert merged[1] == "第二句在这，第三句在这"


def test_weights_can_keep_five():
    text = "|||".join(f"第{i}句话在这" for i in range(1, 6))
    parts = split_reply(text, 5, 40, FIVE_ONLY)
    assert len(parts) == 5


def test_max_segments_is_hard_limit():
    text = "|||".join(f"第{i}句话在这" for i in range(1, 8))
    parts = split_reply(text, 3, 40, FIVE_ONLY)
    assert len(parts) <= 3


def test_single_reply_without_delimiter():
    assert split_reply("就一句话", 5, 40, ONE_ONLY) == ["就一句话"]


def test_fallback_splits_sentences():
    parts = split_reply("你开心就好。要不要再来一张看看？", 5, 40, FIVE_ONLY)
    assert len(parts) == 2
    assert parts[0].endswith("。")


def test_merge_adds_comma_between_pieces():
    text = "第一句在这|||今天等你消息|||说真的就这点事"
    merged = split_reply(text, 5, 40, ONE_ONLY)
    assert "今天等你消息，说真的就这点事" in merged


def test_default_weights_favour_short_replies():
    """默认权重下，长串回复应该被压短，5 条是小概率。"""
    text = "|||".join(f"第{i}句话在这" for i in range(1, 6))
    counts: dict[int, int] = {}
    for _ in range(400):
        length = len(split_reply(text, 5, 40))
        counts[length] = counts.get(length, 0) + 1
    assert counts.get(2, 0) > counts.get(3, 0)
    assert counts.get(3, 0) > counts.get(5, 0)
    assert counts.get(5, 0) < 40


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

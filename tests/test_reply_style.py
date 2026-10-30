from __future__ import annotations

from types import SimpleNamespace

from qqbot.core.reply_style import (
    DEFAULT_WEIGHTS,
    reply_delay,
    segment_interval,
    split_reply,
)

# 权重故意做成极端值，把「按概率抽几条」变成确定性行为，方便断言
ONE_ONLY = [100, 0, 0, 0, 0]
TWO_ONLY = [0, 100, 0, 0, 0]
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


def test_weights_can_merge_two_into_one():
    """抽到「只发一条」时，两段要合并，不能硬发两条。"""
    text = "今天等你消息|||说真的就这点事"
    parts = split_reply(text, 5, 40, ONE_ONLY)
    assert len(parts) == 1
    assert parts[0] == "今天等你消息，说真的就这点事"


def test_weights_keep_two_when_target_is_two():
    text = "今天等你消息|||说真的就这点事"
    assert len(split_reply(text, 5, 40, TWO_ONLY)) == 2


def test_three_or_more_compressed_to_one():
    text = "第一句在这|||第二句在这|||第三句在这"
    merged = split_reply(text, 5, 40, ONE_ONLY)
    assert len(merged) == 1
    assert "，第二句在这，第三句在这" in merged[0]


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
    # 句号会被去掉，问号保留
    assert not parts[0].endswith("。")
    assert parts[1].endswith("？")


def test_trailing_period_stripped():
    from qqbot.core.reply_style import split_reply

    assert split_reply("今天好累啊。", 5, 0, target_segments=1) == ["今天好累啊"]
    assert split_reply("行吧。|||没睡好。", 5, 0, target_segments=2) == ["行吧", "没睡好"]
    # 问号、感叹号、省略号是语气，不能动
    assert split_reply("真的假的？！", 5, 0, target_segments=1) == ["真的假的？！"]
    assert split_reply("等等……", 5, 0, target_segments=1) == ["等等……"]


def test_trailing_period_kept_for_verbatim():
    from qqbot.core.reply_style import split_reply

    parts = split_reply("今天这页留着，不折叠。", 5, 0, verbatim=True)
    assert parts and parts[0].endswith("。")


def test_merge_adds_comma_between_pieces():
    text = "第一句在这|||今天等你消息|||说真的就这点事"
    merged = split_reply(text, 5, 40, ONE_ONLY)
    assert len(merged) == 1
    assert "今天等你消息，说真的就这点事" in merged[0]


def test_short_text_stays_one_message():
    """20 字以内的话装得进一条，权重再高也发不成多条。"""
    text = "今天上班真是累得不行啊"
    for weights in ([100, 0, 0, 0, 0], [0, 0, 0, 0, 100]):
        parts = split_reply(text, 5, 20, weights)
        assert len(parts) == 1
        assert len(parts[0]) <= 20


def test_long_text_must_split_even_if_weights_want_one():
    """想发一条但内容超 20 字，只能切开——单条上限优先于权重。"""
    text = "这是一句比较长的话，" * 4
    parts = split_reply(text, 5, 20, [100, 0, 0, 0, 0])
    assert len(parts) >= 2
    assert all(len(p) <= 20 for p in parts)


def test_default_weights_are_ordered_descending():
    assert list(DEFAULT_WEIGHTS) == sorted(DEFAULT_WEIGHTS, reverse=True)


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


def test_verbatim_not_split():
    """念日记/贴代码这类原文不按字数切碎。"""
    diary = "今天对方没来找我，我把记忆柜从里到外整理了一遍，顺手毒了自己一句。"
    parts = split_reply(diary, 5, 20, [100, 0, 0, 0], verbatim=True)
    assert len(parts) == 1
    assert parts[0] == diary


def test_each_segment_capped_at_20():
    """单条最多 20 字，超了必须切开。"""
    long_text = "这部分内容比较长，" * 8
    parts = split_reply(long_text, 5, 20, [100, 0, 0, 0])
    assert len(parts) >= 2
    assert all(len(p) <= 20 for p in parts)


def test_merge_uses_period_before_question():
    """「在呢，一直没走」+「怎么了，比赛出事了？」应该是两句，不是逗号硬连。"""
    from qqbot.core.reply_style import _join_pieces

    merged = _join_pieces("在呢，一直没走", "怎么了，比赛出事了？")
    assert merged == "在呢，一直没走。怎么了，比赛出事了？"


def test_merge_uses_period_after_sentence_tail():
    from qqbot.core.reply_style import _join_pieces

    assert _join_pieces("行啊，加上吧", "那你现在知道几点了不") == (
        "行啊，加上吧。那你现在知道几点了不"
    )


def test_merge_uses_comma_for_connective():
    from qqbot.core.reply_style import _join_pieces

    assert _join_pieces("今天等你消息", "说真的就这点事") == (
        "今天等你消息，说真的就这点事"
    )
    assert _join_pieces("我不困", "但其实快睡着了") == "我不困，但其实快睡着了"


def test_merge_keeps_existing_punct():
    from qqbot.core.reply_style import _join_pieces

    assert _join_pieces("先这样。", "明天再说") == "先这样。明天再说"


def test_max_segments_is_hard_even_when_pieces_long():
    """637 字的日记被切成 9 段发出去过；硬上限必须生效，宁可最后一条长。"""
    text = "这是一段很长的内容，" * 80  # 约 800 字，切完远超 5 段
    parts = split_reply(text, 5, 100, [100, 0, 0, 0, 0])
    assert len(parts) <= 5


def test_blank_line_used_as_separator():
    """模型有时用空行分段，要当成 ||| 处理，别把空行发出去。"""
    from qqbot.core.reply_style import split_reply

    text = "真的呀|||先练练怎么打招呼\n\n我这嘴没把门的|||你帮我看着点"
    parts = split_reply(text, 5, 0, target_segments=3)
    assert parts == ["真的呀", "先练练怎么打招呼", "我这嘴没把门的，你帮我看着点"]
    assert all("\n" not in p for p in parts)


def test_single_newline_becomes_space():
    from qqbot.core.reply_style import split_reply

    parts = split_reply("第一行\n第二行", 5, 0, target_segments=1)
    assert parts == ["第一行 第二行"]


def test_verbatim_keeps_newlines():
    """念日记、贴代码时换行要原样保留。"""
    from qqbot.core.reply_style import split_reply

    text = "```\nline1\nline2\n```"
    parts = split_reply(text, 5, 0, verbatim=True)
    assert parts and "\n" in parts[0]

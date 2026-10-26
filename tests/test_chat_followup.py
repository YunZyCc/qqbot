from __future__ import annotations

from qqbot.modules.chat import _PROMISED_SEARCH


def test_promise_phrases_detected():
    """她说要去查的各种说法都要能识别出来。"""
    for text in (
        "我去查查",
        "我查一下哈",
        "等我查了告诉你",
        "我去搜搜看",
        "搜一下就有了",
        "等我看看",
        "去瞅瞅",
        "帮你查一下",
        "我这就查",
    ):
        assert _PROMISED_SEARCH.search(text), text


def test_normal_replies_not_matched():
    for text in ("今天好累啊", "我在翻书", "哥陪你聊会儿", "不知道诶"):
        assert not _PROMISED_SEARCH.search(text), text

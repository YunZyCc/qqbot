"""人格成长：从聊天里抽取「她自己的变化」，攒够证据才真正生效。

设计上分成三层，互不越界：
- 骨架（persona.md）：身份、说话方式、边界，永不被自动改写
- 成长层（本模块，persona_traits 表）：习惯、称呼、兴趣、性格微调
- 状态层（self_state）：短期情绪，会淡忘

成长层绝不回写 persona.md。系统长歪了，清空 traits 就回到零点。

注意「措辞漂移」：模型每次描述同一件事都会换说法，所以写入前要先和已有记录做
相似度归并，否则同一件事会散成七八条候选，永远攒不够证据。
"""

from __future__ import annotations

import logging

from ..llm.client import ChatClient
from .facts import _parse_items
from .retrieve import _grams
from .store import Store

log = logging.getLogger(__name__)

TRAIT_SCOPE = "bot:self"
MAX_ACTIVE = 12
MAX_CHARACTER_ACTIVE = 2
VALID_KINDS = ("style", "address", "interest", "character", "lore")
MAX_CONTENT_CHARS = 60
MERGE_THRESHOLD = 0.82

TRAIT_PROMPT = """你在观察一段聊天里「AI 自己」发生了什么变化，抽取能长期指导她行为的变化信号。

只抽这五类，kind 取值：
- style     说话习惯：口头禅、句式、语气的变化（她在戒掉什么、开始说什么）
- address   称呼：她怎么叫对方，对方怎么叫她
- interest  兴趣：她主动表现出偏好、熟悉起来的话题
- character 性格：她的脾气、主动性、尺度发生了变化（只抽确实反复体现的）
- lore      梗：两人之间形成了、以后提起来还能笑的固定梗

每条 content 要写成**对她的行为指令**，以「你」开头，不超过 40 字。

最重要的规则：**只抽「变化」，不抽「现状」**。必须带方向感——开始/正在/改口/不再/变得。

反例（现状，不要）：「你爱用「行吧」接话」
正例（变化，要）：「你正在戒掉「行吧」，改说「成」」

反例（一次性玩笑，不要）：「你拿「丫丫」自比」
反例（某个话题的具体内容，不要）：「你知道绿龙和BB战队」
正例（可复用，要）：「你对 CS 比赛熟了，能接得上话」

如果对方明确嫌弃过某个习惯，抽「正在改」，不要抽「爱用」——否则会把她固定在一个坏习惯里。

已经记过的变化不要重复输出（下面会给出已有记录）。如果新的观察意思和已有的差不多，
就原样输出已有的那句，不要换措辞。

输出 JSON 数组：
[{"kind":"style","content":"...","confidence":0.7}]

规则：
- 必须是从对话里真实体现的，不要根据人设推测。
- 宁少勿多，没有就输出 []。
- confidence 取 0.5~0.9，一次性的玩笑给 0.5。
只输出 JSON，不要解释。"""


def _similarity(a: str, b: str) -> float:
    grams_a = _grams(a)
    grams_b = _grams(b)
    if not grams_a or not grams_b:
        return 0.0
    return len(grams_a & grams_b) / len(grams_a | grams_b)


async def _merge_target(
    store: Store, vector, kind: str, content: str
) -> dict | None:
    """找工作里已有记录的相近条目；找不到返回 None。

    优先用向量，向量不可用时退回字符 bigram。
    """
    rows = await store.list_traits(TRAIT_SCOPE, limit=60)
    same_kind = [row for row in rows if row["kind"] == kind]
    if not same_kind:
        return None

    if vector is not None and getattr(vector.embedder, "dim", 0):
        try:
            vectors = await vector.embedder.embed(
                [content] + [row["content"] for row in same_kind]
            )
        except Exception:
            log.warning("人格归并向量失败，退回字符相似度", exc_info=True)
            vectors = []
        if len(vectors) == len(same_kind) + 1:
            import numpy as np

            base = np.asarray(vectors[0], dtype=np.float32)
            base = base / (np.linalg.norm(base) + 1e-8)
            best_row = None
            best_score = 0.0
            for row, raw in zip(same_kind, vectors[1:], strict=True):
                vec = np.asarray(raw, dtype=np.float32)
                vec = vec / (np.linalg.norm(vec) + 1e-8)
                score = float(base @ vec)
                if score > best_score:
                    best_score = score
                    best_row = row
            if best_row is not None and best_score >= MERGE_THRESHOLD:
                return best_row
            return None

    best_row = None
    best_score = 0.0
    for row in same_kind:
        score = _similarity(content, row["content"])
        if score > best_score:
            best_score = score
            best_row = row
    if best_row is not None and best_score >= 0.55:
        return best_row
    return None


async def collect_signals(
    store: Store,
    chat: ChatClient,
    messages: list[dict],
    promote_after: int = 3,
    vector=None,
) -> int:
    """扫一段对话，抽人格信号；累计够次数自动升级。返回处理条数。"""
    if not messages:
        return 0

    existing = await store.list_traits(TRAIT_SCOPE, limit=30)
    existing_text = (
        "\n".join(f"- [{row['kind']}] {row['content']}" for row in existing)
        or "（暂无）"
    )

    lines = [f"{m['role']}: {m['content']}" for m in messages]
    user_content = (
        f"已经记下的变化：\n{existing_text}\n\n最近的对话：\n"
        + "\n".join(lines)[-6000:]
    )

    try:
        response, _ = await chat.complete(
            [
                {"role": "system", "content": TRAIT_PROMPT},
                {"role": "user", "content": user_content},
            ],
            max_tokens=400,
            temperature=0.2,
        )
    except Exception:
        log.exception("人格信号抽取调用失败")
        return 0

    items = _parse_items(response)
    if not items:
        return 0

    count = 0
    for item in items:
        kind = str(item.get("kind") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if kind not in VALID_KINDS or not content:
            continue
        if not content.startswith("你"):
            continue
        if len(content) > MAX_CONTENT_CHARS:
            continue

        target = await _merge_target(store, vector, kind, content)
        if target is not None:
            kind = target["kind"]
            content = target["content"]

        result = await store.record_trait_signal(
            TRAIT_SCOPE, kind, content, promote_after
        )
        if result.get("promoted"):
            log.info("人格变化生效：[%s] %s", kind, content)
        count += 1

    if count:
        await _enforce_limits(store)
    return count


async def _enforce_limits(store: Store) -> None:
    """active 太多就降回候选，避免 prompt 被撑爆。性格类的条数在注入时单独限制。"""
    await store.prune_traits(TRAIT_SCOPE, MAX_ACTIVE)


async def active_traits(store: Store) -> list[dict]:
    """给 prompt 用：active 的变化，性格类最多两条。"""
    rows = await store.list_traits(TRAIT_SCOPE, "active", limit=MAX_ACTIVE)
    picked: list[dict] = []
    characters = 0
    for row in rows:
        if row["kind"] == "character":
            if characters >= MAX_CHARACTER_ACTIVE:
                continue
            characters += 1
        picked.append(row)
    return picked

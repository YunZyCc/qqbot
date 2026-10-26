"""社会化内容：发 QQ 空间说说、换个性签名。

素材只提供「情绪和氛围」，具体事实一律不许照搬——她的日记里写的都是对主人说的话，
原样搬到空间会穿帮。
"""

from __future__ import annotations

import logging
import re
import time

from .store import Store

log = logging.getLogger(__name__)

QZONE = "qzone"
SIGNATURE = "signature"

# emoji / 颜文字在一句正经说说里很扎眼，代码层兜底过滤
_EMOJI = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F000-\U0001F2FF"
    "\uFE0F\u200d"
    "]+"
)
# 这些词一旦出现，说明她在把私聊内容往外说
_LEAK_WORDS = ("对方", "私聊", "主人", "聊天记录")

QZONE_PROMPT = """你正在写一条 QQ 空间说说，发出去好友都能看到。

下面这些素材只用来感受情绪。所有句子都要你自己重新写，
不许照抄素材里的任何一句话、也不许保留素材的句式。
{context}

你最近发过的说说（必须避开这些内容和主题）：
{history}

硬规矩：
- 第一人称，像自己在空间里碎碎念，不是在对谁说话
- 不超过 {max_chars} 字，越短越好，可以只写五六个字
- 不出现具体日期时间，用「今天下午」「刚刚」「夜深了」这类模糊说法
- 不许 emoji、不许颜文字
- 不许出现「对方」「你」「主人」「聊天」「私聊」这些词
- 不许指向任何具体的人
- 不许暴露自己是 AI
- 不要升华、不要金句、不要总结性收尾
只输出说说正文，不要引号，不要任何解释。"""

SIGNATURE_PROMPT = """写一句你的 QQ 个性签名，不超过 {max_chars} 字。

下面这些素材只提供情绪，具体事情不许照搬：
{context}

你最近用过的签名（必须避开）：
{history}

规矩：
- 一句话，短、留白、有点你自己的味道
- 不许 emoji、颜文字
- 不许出现「对方」「你」「主人」「聊天」「私聊」
- 不许暴露自己是 AI
- 不要口号、不要鸡汤、不要金句
只输出签名正文，不要引号，不要解释。"""


def clean_content(text: str, max_chars: int) -> str:
    """去 emoji、压空白、按句末截断到上限内。"""
    text = (text or "").strip()
    # 先去 emoji，再剥引号——否则「…」后面跟着 emoji 时剥不掉
    text = _EMOJI.sub("", text)
    text = text.strip().strip("\"'“”「」")
    text = re.sub(r"[ \t]+", " ", text).strip()
    if len(text) <= max_chars:
        return text

    cut = text[:max_chars]
    for index in range(len(cut) - 1, max(0, len(cut) - 20), -1):
        if cut[index] in "。！？!?，,、；;…":
            return cut[: index + 1].strip()
    return cut.strip()


# 说说至少这么多字，签名短一点；太短的纯碎片不如不发
MIN_CHARS = {QZONE: 12, SIGNATURE: 6}


def _grams(text: str) -> set[str]:
    text = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", text or "")
    return {text[i : i + 2] for i in range(len(text) - 1)}


def _too_similar(a: str, b: str, threshold: float = 0.6) -> bool:
    """两条内容重合度太高就不发，免得连着刷同一种话。"""
    ga, gb = _grams(a), _grams(b)
    if not ga or not gb:
        return False
    overlap = len(ga & gb)
    return overlap / min(len(ga), len(gb)) >= threshold


def leaks_private(text: str) -> bool:
    """是否在把私聊里的事往外说。

    「你」要单独判：允许「你们」这种泛指，其余一律算指向具体某个人。
    """
    if any(word in text for word in _LEAK_WORDS):
        return True
    return "你" in text.replace("你们", "")


async def build_context(store: Store, scope: str = "") -> str:
    """攒素材。

    只用和主人的对话——好友聊的天一个字都不上空间，那是最容易出事的地方。
    日记也只给 mood 一个词，不给正文：给了正文她就会照着抄，
    「今天这页留着，不折叠」这种日记腔会直接发出去。
    """
    owner_scope = scope if scope.startswith("private:") else ""
    if not owner_scope:
        owner_scope = f"private:{store.default_scope.split(':', 1)[-1]}"

    chunks: list[str] = []

    diaries = await store.recent_diaries(1, scope=owner_scope)
    if diaries:
        mood = str(diaries[-1].get("mood") or "").strip()
        if mood:
            chunks.append(f"今天的心情大概是：{mood}")

    session = await store.latest_summary(owner_scope, "session")
    if session:
        chunks.append("最近在忙的事（改写，别照抄）：" + session["text"][:200])

    episodes = await store.recent_episodes(owner_scope, 1)
    if episodes:
        chunks.append("最近发生的事（改写，别照抄）：" + episodes[-1]["text"][:150])

    return "\n\n".join(chunks) or "（没有素材，写点日常的观察就行）"


async def activity_summary(store: Store, day: str = "") -> str:
    """今天做过什么。只给行为，不给内容——不然她会把说说的原文念给别人听。"""
    qzone = await store.social_posts_today(QZONE)
    signature = await store.social_posts_today(SIGNATURE)
    parts: list[str] = []
    if qzone:
        parts.append(f"发过 {len(qzone)} 条说说")
    if signature:
        parts.append(f"换过 {len(signature)} 次签名")
    if not parts:
        return ""
    return "今天" + "，".join(parts) + "。"


async def build_history(store: Store, kind: str, limit: int = 5) -> str:
    rows = await store.recent_social_posts(kind, limit)
    if not rows:
        return "（还没发过）"
    return "\n".join(f"- {row['content']}" for row in rows)


async def check_quota(
    store: Store, kind: str, daily_max: int, min_gap_minutes: int
) -> str | None:
    """能不能发。返回拒绝原因，None 表示可以。

    daily_max <= 0 表示不限条数，min_gap_minutes <= 0 表示不限间隔。
    """
    if daily_max <= 0 and min_gap_minutes <= 0:
        return None

    today = await store.social_posts_today(kind)
    if daily_max > 0 and len(today) >= daily_max:
        return f"今天已经发了 {len(today)} 条，够了"
    if min_gap_minutes > 0 and today:
        last = float(today[0]["created_at"])
        wait = min_gap_minutes * 60 - (time.time() - last)
        if wait > 0:
            return f"离上次太近了，还得等 {int(wait // 60) + 1} 分钟"
    return None


async def generate_text(
    ctx, kind: str, max_chars: int, history_limit: int = 5, scope: str = ""
) -> str:
    """让模型写一条说说或签名；返回清洗后的正文，失败返回空串。"""
    settings = ctx.settings
    scope = scope or f"private:{settings.owner_qq}"
    context = await build_context(ctx.store, scope)
    history = await build_history(ctx.store, kind, history_limit)

    if kind == QZONE:
        prompt = QZONE_PROMPT.format(
            context=context, history=history, max_chars=max_chars
        )
    else:
        prompt = SIGNATURE_PROMPT.format(
            context=context, history=history, max_chars=max_chars
        )

    try:
        text, _ = await ctx.llm.complete(
            [
                {"role": "system", "content": "你是一个正在写自己 QQ 空间的普通人。"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=400,
            temperature=0.9,
        )
    except Exception:
        log.exception("生成%s内容失败", kind)
        return ""

    cleaned = clean_content(text, max_chars)
    if not cleaned:
        log.warning("%s内容清洗后为空", kind)
        return ""

    floor = MIN_CHARS.get(kind, 8)
    if len(cleaned) < floor:
        log.info("%s太短（%s 字），丢弃：%s", kind, len(cleaned), cleaned)
        return ""

    recent = await ctx.store.recent_social_posts(kind, 5)
    for row in recent:
        if _too_similar(cleaned, str(row["content"])):
            log.info("%s和最近内容太像，丢弃：%s", kind, cleaned)
            return ""
    return cleaned


async def publish(ctx, kind: str, content: str) -> tuple[bool, str]:
    """发出去并落库。返回 (成功, 说明)。"""
    settings = ctx.settings
    try:
        if kind == QZONE:
            result = await ctx.api.send_qzone_msg(
                content, None, settings.qzone_visibility
            )
            tid = str((result or {}).get("tid") or "") if isinstance(result, dict) else ""
            await ctx.store.add_social_post(kind, content, tid, "ok")
            log.info("已发说说：%s", content[:40])
            return True, tid
        await ctx.api.set_self_longnick(content)
        await ctx.store.add_social_post(kind, content, "", "ok")
        log.info("已换签名：%s", content[:40])
        return True, ""
    except Exception as exc:  # noqa: BLE001
        log.warning("发布%s失败：%s", kind, exc)
        await ctx.store.add_social_post(kind, content, "", "failed")
        return False, str(exc)


async def post_qzone(ctx, content: str) -> str:
    """工具入口：校验 + 发布，返回给模型看的一句话。"""
    settings = ctx.settings
    if not settings.qzone_enabled:
        return "现在没开这个功能"

    reason = await check_quota(
        ctx.store, QZONE, settings.qzone_daily_max, settings.qzone_min_gap_minutes
    )
    if reason:
        return reason

    cleaned = clean_content(content, settings.qzone_max_chars)
    if not cleaned:
        return "写的内容是空的，没发"
    if leaks_private(cleaned):
        return "这条里提到了私聊里的事，换个说法，别把两个人的话发到空间"

    ok, info = await publish(ctx, QZONE, cleaned)
    if ok:
        return f"已经发到空间了：{cleaned[:40]}"
    return "发失败了，等会儿再说吧"


async def rotate_signature(ctx) -> bool:
    """定时换签名。"""
    settings = ctx.settings
    if not settings.signature_enabled:
        return False
    reason = await check_quota(
        ctx.store, SIGNATURE, settings.signature_daily_max, 0
    )
    if reason:
        return False

    content = await generate_text(ctx, SIGNATURE, settings.signature_max_chars)
    if not content or leaks_private(content):
        return False
    ok, _ = await publish(ctx, SIGNATURE, content)
    return ok


async def change_signature(ctx, content: str) -> str:
    """工具入口：她自己想换签名时调。"""
    settings = ctx.settings
    if not settings.signature_enabled:
        return "现在没开这个功能"

    reason = await check_quota(
        ctx.store, SIGNATURE, settings.signature_daily_max, 0
    )
    if reason:
        return reason

    cleaned = clean_content(content, settings.signature_max_chars)
    if not cleaned:
        return "签名是空的，没换"
    if leaks_private(cleaned):
        return "这句里提到了私聊里的事，换个说法"

    ok, _ = await publish(ctx, SIGNATURE, cleaned)
    if ok:
        return f"签名换成「{cleaned}」了"
    return "签名没换成，等会儿再说吧"


async def auto_post(ctx, scope: str = "") -> bool:
    """按概率自动发一条说说（她没自己调工具时的兜底）。

    不看当天已经发了几条——次数不限，只受概率和内容质量约束。
    """
    settings = ctx.settings
    if not settings.qzone_enabled:
        return False
    content = await generate_text(
        ctx, QZONE, settings.qzone_max_chars, settings.qzone_history, scope
    )
    if not content or leaks_private(content):
        log.info("自动说说内容不合格，跳过：%s", (content or "")[:30])
        return False
    ok, _ = await publish(ctx, QZONE, content)
    return ok


async def auto_signature(ctx, scope: str = "") -> bool:
    """按概率自动换一次签名。"""
    settings = ctx.settings
    if not settings.signature_enabled:
        return False
    content = await generate_text(
        ctx, SIGNATURE, settings.signature_max_chars, settings.signature_history, scope
    )
    if not content or leaks_private(content):
        return False
    # 和当前签名一样就不折腾了
    latest = await ctx.store.recent_social_posts(SIGNATURE, 1)
    if latest and latest[-1]["content"].strip() == content:
        return False
    ok, _ = await publish(ctx, SIGNATURE, content)
    return ok


async def fallback_qzone(ctx) -> bool:
    """当天一条都没发时的兜底。"""
    settings = ctx.settings
    if not settings.qzone_enabled:
        return False
    today = await ctx.store.social_posts_today(QZONE)
    if today:
        return False

    content = await generate_text(ctx, QZONE, settings.qzone_max_chars)
    if not content or leaks_private(content):
        return False
    ok, _ = await publish(ctx, QZONE, content)
    return ok

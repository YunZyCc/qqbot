"""她的一天：每天生成一份日程，聊天时知道自己此刻在做什么。

素材只用主人那边的对话和过去几天的日程——她的一天是连贯的，
不按对话对象切分，也不该因为好友来了就换一套生活。
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re

from .store import Store

log = logging.getLogger(__name__)

PLAN_PROMPT = """你在给「周周」安排今天的一天。

她是个二十多岁的姑娘，自由职业，一个人住，有手有脚，想去哪就去哪。
她的一天是实地过的：出门买咖啡、在公园长椅上坐一下午、逛超市、去菜市场、
在家躺到中午、接活干两小时、临时起意坐车去江边、下雨了懒得动……

**她不受地域限制**：家附近能去，隔壁城市也能去；可以临时买张票出远门，
在外地住一晚，去海边、去山里、去朋友那儿待两天。没人管她，她也不缺这个胆。

今天是 {date}。

{history}

{recent}

要求：
- 3 到 6 个时段，从早到晚覆盖，不要全挤在一个时间
- 每个时段写清楚：几点到几点、在做什么、在哪儿
- 活动要具体但要短（15 字以内），别写「思考人生」这种空话；写成「去街角买杯冰美式」
- **要有真实的身体和生活**：吃饭、走路、坐车、晒太阳、逛店、跟人说话都算
- **地点可以离家很远**：别的区、别的城市、高铁上、海边、山里的民宿都行
- 不要一天到晚守着手机——聊天是她的事，但不是她全部的事
- **不要编造和某个具体的人的约定**（她不能主动约人）
- 和过去几天的活动错开，别连续几天都做同一件事
- 时间用 24 小时制，格式 HH:MM

输出 JSON：
{{"theme": "今天大概是什么日子，一句话", "mood": "一个词", "items": [{{"start":"08:00","end":"10:00","activity":"做什么","place":"在哪"}}]}}
只输出 JSON，不要解释。"""

_JSON_OBJ = re.compile(r"\{.*\}", re.S)
_TIME = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

MIN_ITEMS = 3
MAX_ITEMS = 6


def parse_plan(text: str) -> dict | None:
    """从模型输出里抠出日程。时间格式不对的条目直接丢掉。"""
    match = _JSON_OBJ.search(text or "")
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    items: list[dict] = []
    for raw in data.get("items") or []:
        if not isinstance(raw, dict):
            continue
        start = str(raw.get("start") or "").strip()
        end = str(raw.get("end") or "").strip()
        activity = str(raw.get("activity") or "").strip()
        if not activity or not _TIME.match(start) or not _TIME.match(end):
            continue
        if start >= end:
            continue
        items.append(
            {
                "start": start,
                "end": end,
                "activity": activity[:30],
                "place": str(raw.get("place") or "").strip()[:30],
            }
        )

    if not items:
        return None
    items.sort(key=lambda item: item["start"])
    items = items[:MAX_ITEMS]
    return {
        "theme": str(data.get("theme") or "").strip()[:60],
        "mood": str(data.get("mood") or "").strip()[:20],
        "items": items,
    }


def current_item(items: list[dict], now: dt.datetime | None = None) -> dict | None:
    """按当前时间找命中时段；不在任何时段就返回最近一个。"""
    if not items:
        return None
    now = now or dt.datetime.now()
    hhmm = now.strftime("%H:%M")
    for item in items:
        if item["start"] <= hhmm < item["end"]:
            return item
    # 落在两个时段之间，或者已经过了最后一个
    earlier = [item for item in items if item["end"] <= hhmm]
    if earlier:
        return earlier[-1]
    return items[0]


def describe(plan: dict | None, now: dt.datetime | None = None) -> str:
    """把当天日程渲染成给 prompt 看的一小段。"""
    if not plan:
        return ""
    items = plan.get("items") or []
    if not items:
        return ""
    now = now or dt.datetime.now()
    hhmm = now.strftime("%H:%M")

    lines = []
    item = current_item(items, now)
    if item:
        place = f"，在{item['place']}" if item.get("place") else ""
        lines.append(f"{hhmm}，你正在{item['activity']}{place}。")
    theme = plan.get("theme") or ""
    if theme:
        # 活动描述可能很长，只截前一小段，免得把 prompt 撑爆
        overview = "、".join(str(i["activity"])[:10] for i in items[:4])
        lines.append(f"今天大概是：{theme[:30]}。计划里有{overview}。")
    return "\n".join(lines)


async def build_history(store: Store, days: int) -> str:
    """过去几天的日程，用来避开重复。"""
    rows = await store.recent_plans(days)
    if not rows:
        return ""
    lines = []
    for row in rows:
        try:
            items = json.loads(row.get("items_json") or "[]")
        except json.JSONDecodeError:
            continue
        activity = "、".join(str(i.get("activity") or "") for i in items if i)
        if activity:
            lines.append(f"- {row['date']}：{activity}")
    return "过去几天她做过这些（今天别重复）：\n" + "\n".join(lines) if lines else ""


async def build_recent_chat(ctx) -> str:
    """最近和主人聊了什么，给今天的日程一点由头。"""
    settings = ctx.settings
    scope = f"private:{settings.owner_qq}"
    try:
        session = await ctx.store.latest_summary(scope, "session")
    except Exception:
        return ""
    if not session:
        return ""
    return "最近和主人聊到（可以变成今天的念头，但别写成约定）：\n" + session["text"][:300]


async def generate_plan(ctx, day: dt.date | None = None) -> dict | None:
    """生成某一天的日程；不传就是今天。"""
    settings = ctx.settings
    day = day or dt.date.today()

    history = await build_history(ctx.store, settings.schedule_history_days)
    recent = await build_recent_chat(ctx)
    prompt = PLAN_PROMPT.format(
        date=day.isoformat(), history=history, recent=recent
    )

    try:
        text, _ = await ctx.llm.complete(
            [
                {"role": "system", "content": "你在给一个自由职业的姑娘写她今天的日程。"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=600,
            temperature=0.9,
        )
    except Exception:
        log.exception("生成日程失败")
        return None

    plan = parse_plan(text)
    if plan is None:
        log.warning("日程解析失败：%s", (text or "")[:200])
        return None
    if len(plan["items"]) < MIN_ITEMS:
        log.info("日程只有 %s 个时段，不用", len(plan["items"]))
        return None

    await ctx.store.upsert_plan(
        day.isoformat(),
        plan["theme"],
        plan["mood"],
        json.dumps(plan["items"], ensure_ascii=False),
    )
    log.info(
        "日程已生成 %s：%s（%s 个时段）",
        day,
        plan["theme"][:20],
        len(plan["items"]),
    )
    return plan


async def ensure_plan(ctx, day: dt.date | None = None) -> dict | None:
    """某天有日程就返回，没有就现生成一份。"""
    day = day or dt.date.today()
    plan = await today_plan(ctx.store, day)
    if plan is not None:
        return plan
    return await generate_plan(ctx, day)


def resolve_day(text: str) -> dt.date | None:
    """把 today / tomorrow / 明天 / 2026-10-28 解析成日期。"""
    raw = (text or "").strip()
    today = dt.date.today()
    if not raw:
        return today
    lowered = raw.lower()
    if lowered in {"today", "今天", "今日", "now"}:
        return today
    if lowered in {"tomorrow", "明天", "明日"}:
        return today + dt.timedelta(days=1)
    if lowered in {"yesterday", "昨天"}:
        return today - dt.timedelta(days=1)
    for fmt in ("%Y-%m-%d", "%m-%d", "%Y/%m/%d", "%m/%d"):
        try:
            parsed = dt.datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
        if fmt in ("%m-%d", "%m/%d"):
            parsed = parsed.replace(year=today.year)
        return parsed
    return None


async def plan_text_for(ctx, day: dt.date) -> str:
    """给工具用的文本版日程。"""
    plan = await ensure_plan(ctx, day)
    if not plan:
        return "这天没安排上，脑子里是空的"
    lines = [f"{day.isoformat()}（{plan.get('mood') or '平常'}）：{plan.get('theme') or ''}"]
    for item in plan.get("items") or []:
        place = f"，{item['place']}" if item.get("place") else ""
        lines.append(f"- {item['start']}-{item['end']} {item['activity']}{place}")
    return "\n".join(lines)


async def today_plan(store: Store, day: dt.date | None = None) -> dict | None:
    """读当天的日程，读出来就转成结构化。"""
    day = day or dt.date.today()
    row = await store.get_plan(day.isoformat())
    if not row:
        return None
    try:
        items = json.loads(row.get("items_json") or "[]")
    except json.JSONDecodeError:
        return None
    if not isinstance(items, list) or not items:
        return None
    return {
        "theme": row.get("theme") or "",
        "mood": row.get("mood") or "",
        "items": items,
    }

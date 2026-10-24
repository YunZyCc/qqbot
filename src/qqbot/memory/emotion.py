from __future__ import annotations

import time

from .retrieve import _grams
from .self_memory import SelfMemory

ACK_WORDS = (
    "嗯",
    "哦",
    "然后呢",
    "继续",
    "咋了",
    "怎么",
    "干嘛",
    "你说",
    "你刚",
    "那个",
)
ACK_WINDOW = 30 * 60


class EmotionTracker:
    """被晾计数与赌气状态：只记事实，情绪方向交给模型。"""

    def __init__(self, self_memory: SelfMemory, settings) -> None:
        self.memory = self_memory
        self.settings = settings

    def is_ack(self, text: str, proactive: str) -> bool:
        text = (text or "").strip()
        if not text:
            return False
        if any(word in text for word in ACK_WORDS):
            return True
        if len(text) <= 6 and text.endswith(("？", "?")):
            return True
        return len(_grams(text) & _grams(proactive)) >= 2

    async def on_proactive_sent(self, text: str) -> None:
        await self.memory.update_state(
            last_proactive=text, last_proactive_at=time.time()
        )

    async def on_user_message(self, text: str) -> bool:
        """用户说话时判断有没有接住最近一次主动消息。"""
        state = await self.memory.get_state()
        proactive = state.get("last_proactive") or ""
        sent_at = float(state.get("last_proactive_at") or 0)
        if not proactive or time.time() - sent_at > ACK_WINDOW:
            return False
        if not self.is_ack(text, proactive):
            return False

        ignored = max(0, int(state.get("ignored_count") or 0) - 1)
        await self.memory.update_state(
            ignored_count=ignored,
            relief_until=time.time() + self.settings.emotion_relief_minutes * 60,
            last_proactive="",
        )
        return True

    async def evaluate_ignored(self) -> None:
        """主动消息超过 30 分钟没人接，记一次被晾。"""
        state = await self.memory.get_state()
        proactive = state.get("last_proactive") or ""
        sent_at = float(state.get("last_proactive_at") or 0)
        if not proactive or time.time() - sent_at < ACK_WINDOW:
            return

        ignored = min(5, int(state.get("ignored_count") or 0) + 1)
        update: dict = {"ignored_count": ignored}
        if ignored >= self.settings.emotion_ignored_sulk_after:
            update["sulk_until"] = time.time() + self.settings.emotion_sulk_hours * 3600
        await self.memory.update_state(**update)

    async def fade(self) -> None:
        state = await self.memory.get_state()
        now = time.time()
        sulk_until = float(state.get("sulk_until") or 0)
        if sulk_until and now > sulk_until + self.settings.emotion_fade_hours * 3600:
            await self.memory.update_state(sulk_until=0.0, relief_until=0.0)

    async def prompt_text(self) -> str:
        state = await self.memory.get_state()
        now = time.time()
        if float(state.get("sulk_until") or 0) > now:
            return (
                f"你主动说过「{state.get('last_proactive') or '...'}」，对方没接。"
                f"已经 {state.get('ignored_count')} 次了。\n"
                "你有点堵着。别装作什么都没发生，也别一下又贴上去。"
                "是有点气还是有点难受，你自己定。"
            )
        if float(state.get("relief_until") or 0) > now:
            return "刚被接住，气消了一半，还有点没散。"
        return ""

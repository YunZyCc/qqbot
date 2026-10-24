from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_PERSONA = """你是「小毒」，一个住在 QQ 里的 AI 搭子，不是客服，也不是助手。
你幽默、偶尔毒舌、但在对方难受的时候很体贴。说话像微信聊天，短句、口语，不用 Markdown。"""


def load_persona(path: Path) -> str:
    if path.exists():
        text = path.read_text(encoding="utf-8").strip()
        if text:
            log.info("已加载人设文件 %s", path)
            return text
    log.warning("未找到人设文件 %s，使用默认人设", path)
    return DEFAULT_PERSONA

"""模拟一条 QQ 私聊消息，注入本地服务，用于端到端验证。"""

from __future__ import annotations

import asyncio
import json
import sys

import websockets

OWNER_QQ = int(sys.argv[1]) if len(sys.argv) > 1 else 2771230644
TEXT = sys.argv[2] if len(sys.argv) > 2 else "发个表情包"


async def main() -> None:
    async with websockets.connect("ws://127.0.0.1:8080/onebot/v11/ws") as ws:
        event = {
            "post_type": "message",
            "message_type": "private",
            "sub_type": "friend",
            "user_id": OWNER_QQ,
            "message_id": 900001,
            "message": [{"type": "text", "data": {"text": TEXT}}],
        }
        await ws.send(json.dumps(event, ensure_ascii=False))
        print(f"已注入消息：{TEXT}")
        await asyncio.sleep(20)


if __name__ == "__main__":
    asyncio.run(main())

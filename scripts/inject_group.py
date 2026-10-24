"""模拟一条 QQ 群消息，注入本地服务，用于端到端验证。

用法：
    python scripts/inject_group.py <群号> <发送者QQ> <文本> [--at] [--nick 昵称]

加 --at 会在消息前面插一个 @机器人，用来验证「必回」分支。
"""

from __future__ import annotations

import asyncio
import json
import sys

import websockets

DEFAULT_BOT_QQ = 1802019125


async def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}

    group_id = int(args[0]) if args else 1083370981
    sender_qq = int(args[1]) if len(args) > 1 else 2771230644
    text = args[2] if len(args) > 2 else "大肥鱼在吗"

    nickname = "测试"
    for index, arg in enumerate(sys.argv):
        if arg == "--nick" and index + 1 < len(sys.argv):
            nickname = sys.argv[index + 1]

    segments: list[dict] = []
    if "--at" in flags:
        segments.append({"type": "at", "data": {"qq": str(DEFAULT_BOT_QQ)}})
    segments.append({"type": "text", "data": {"text": text}})

    event = {
        "post_type": "message",
        "message_type": "group",
        "sub_type": "normal",
        "group_id": group_id,
        "user_id": sender_qq,
        "sender": {"user_id": sender_qq, "nickname": nickname, "card": nickname},
        "message_id": 910001,
        "message": segments,
    }

    async with websockets.connect("ws://127.0.0.1:8080/onebot/v11/ws") as ws:
        await ws.send(json.dumps(event, ensure_ascii=False))
        print(f"已注入群消息：群 {group_id} / {nickname}({sender_qq}) / {text}")
        await asyncio.sleep(25)


if __name__ == "__main__":
    asyncio.run(main())

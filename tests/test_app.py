from __future__ import annotations

from fastapi.testclient import TestClient

from qqbot.main import create_app


def test_ws_endpoint_accepts_onebot_event(monkeypatch):
    monkeypatch.setenv("OWNER_QQ", "12345")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    app = create_app()
    with TestClient(app) as client:
        with client.websocket_connect("/onebot/v11/ws") as ws:
            ws.send_text(
                '{"post_type":"message","message_type":"private",'
                '"user_id":999,"message":[{"type":"text","data":{"text":"hi"}}]}'
            )
            # 非白名单用户不应触发回复，连接应保持可用
            ws.send_text('{"post_type":"meta_event","meta_event_type":"heartbeat"}')


def test_ws_endpoint_rejects_malformed_json(monkeypatch):
    monkeypatch.setenv("OWNER_QQ", "12345")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    app = create_app()
    with TestClient(app) as client:
        with client.websocket_connect("/onebot/v11/ws") as ws:
            ws.send_text("not-json")
            ws.send_text('{"post_type":"meta_event","meta_event_type":"heartbeat"}')

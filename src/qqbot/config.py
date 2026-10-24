from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # 机器人自己登录的 QQ 号（仅用于入库记录，可留空）
    bot_qq: int = 0
    # 唯一允许聊天的 QQ 号（你的号）；为 0 时服务拒绝启动
    owner_qq: int = 0

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # NapCat 的 HTTP API 地址（发动作）
    onebot_http_url: str = "http://127.0.0.1:3000"
    # 反向 WS 路径（NapCat 连本服务）
    onebot_ws_path: str = "/onebot/v11/ws"
    onebot_token: str = ""

    host: str = "127.0.0.1"
    port: int = 8080

    data_dir: Path = Path("data")
    persona_file: Path = Path("src/qqbot/persona/persona.md")

    max_context_messages: int = 30
    summary_every: int = 20
    facts_every: int = 6
    retrieve_top_k: int = 5
    reply_max_chars: int = 500
    daily_token_budget: int = 200_000
    request_timeout: float = 60.0


@lru_cache
def get_settings() -> Settings:
    return Settings()

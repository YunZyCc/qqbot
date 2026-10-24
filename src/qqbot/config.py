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
    summary_every: int = 10
    summary_token_budget: int = 6000
    facts_every: int = 6
    episode_every: int = 20
    retrieve_top_k: int = 5
    reply_max_chars: int = 500
    daily_token_budget: int = 200_000
    request_timeout: float = 60.0

    # 日记
    diary_enabled: bool = True
    diary_hour: int = 0
    diary_minute: int = 10
    diary_backfill_days: int = 7
    diary_prompt_days: int = 3

    # 向量记忆
    memory_vector_enabled: bool = True
    embedding_base_url: str = "http://127.0.0.1:11434/v1"
    embedding_api_key: str = "ollama"
    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024
    embedding_batch: int = 16
    embedding_concurrency: int = 2
    embedding_timeout: float = 30.0

    # 启用的功能模块，逗号分隔；默认只有 chat
    enabled_modules: str = "chat"
    tool_max_rounds: int = 4
    # 是否把工具暴露给模型；默认关闭，保持纯聊天行为
    tools_enabled: bool = False
    # MCP server 配置，JSON 数组，空则不加载
    mcp_servers: str = ""

    @property
    def enabled_module_list(self) -> list[str]:
        return [m.strip() for m in self.enabled_modules.split(",") if m.strip()]

    @property
    def mcp_server_list(self) -> list[dict]:
        import json

        if not self.mcp_servers.strip():
            return []
        try:
            data = json.loads(self.mcp_servers)
        except json.JSONDecodeError:
            return []
        return data if isinstance(data, list) else []


@lru_cache
def get_settings() -> Settings:
    return Settings()

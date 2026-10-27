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
    # 图片理解用的模型：DeepSeek 主模型本身就能看图
    deepseek_vision_model: str = "deepseek-flash"

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
    # focus 类记忆（最近在忙/关注什么）的有效期，过期不再进 prompt
    focus_ttl_days: int = 3
    # 人格成长：攒够几次信号才真正改变自己
    growth_enabled: bool = True
    growth_every: int = 10
    growth_promote_after: int = 3
    # 0 = 不限，只记账不拦截
    daily_token_budget: int = 0
    request_timeout: float = 60.0

    # 日记
    diary_enabled: bool = True
    diary_hour: int = 0
    diary_minute: int = 10
    diary_backfill_days: int = 7
    diary_prompt_days: int = 3
    # 每 N 轮刷新一次「当天」日记，别等到次日才有（0 = 关闭）
    diary_live_every: int = 10

    # 向量记忆
    memory_vector_enabled: bool = True
    # 本地 Ollama：启动时自动检查并拉起（图片识别 + 向量检索都靠它）
    ollama_autostart: bool = True
    ollama_exe: str = ""
    embedding_base_url: str = "http://127.0.0.1:11434/v1"
    embedding_api_key: str = "ollama"
    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024
    embedding_batch: int = 16
    embedding_concurrency: int = 2
    embedding_timeout: float = 30.0

    # 回复风格
    reply_segments_max: int = 5
    # 单条字数上限：0 表示不限字数（只按条数拆）。设成 20 就是每条最多 20 字
    reply_segment_max_chars: int = 0
    # 每轮发几条的权重，对应 1/2/3/4/5 条
    reply_segment_weights: str = "30,22,18,18,12"
    reply_delay_enabled: bool = True
    reply_delay_min: float = 0.5
    reply_delay_max: float = 1.0
    segment_interval_min: float = 0.4
    segment_interval_max: float = 0.9

    @property
    def reply_segment_weight_list(self) -> list[float]:
        items: list[float] = []
        for piece in self.reply_segment_weights.split(","):
            piece = piece.strip()
            if not piece:
                continue
            try:
                value = float(piece)
            except ValueError:
                continue
            if value > 0:
                items.append(value)
        return items or [30.0, 22.0, 18.0, 18.0, 12.0]

    # 好友白名单：逗号分隔的 QQ 号。你在 QQ 客户端自己加好友，加完把号填这里
    friend_whitelist: str = ""

    @property
    def friend_whitelist_ids(self) -> list[int]:
        ids: list[int] = []
        for piece in self.friend_whitelist.split(","):
            piece = piece.strip()
            if not piece:
                continue
            try:
                ids.append(int(piece))
            except ValueError:
                continue
        return ids

    # 群聊：记录按 group:<群号> 隔离，不跟私聊混
    group_enabled: bool = True
    # 逗号分隔的群号白名单；空表示不接任何群（只打日志方便你填）
    group_whitelist: str = "1083370981"
    # 群里叫她什么。命中就必回
    group_trigger_names: str = "大肥鱼"
    # 没 @ 没叫名字时，插一句的概率
    group_reply_chance: float = 0.15
    # 概率回复的最小间隔，防止刷屏
    group_reply_cooldown: int = 60
    # 回过话后保持对话的时长，这段时间内群里说话她都会接
    group_active_minutes: int = 5
    # 太短的消息不值得接
    group_min_chars: int = 4
    # 群聊回放的历史条数（群消息碎，比私聊多）
    group_max_context: int = 40
    # prompt 里最多列几个群成员
    group_member_limit: int = 15

    @property
    def group_whitelist_ids(self) -> list[int]:
        ids: list[int] = []
        for piece in self.group_whitelist.split(","):
            piece = piece.strip()
            if not piece:
                continue
            try:
                ids.append(int(piece))
            except ValueError:
                continue
        return ids

    @property
    def group_trigger_name_list(self) -> list[str]:
        return [n.strip() for n in self.group_trigger_names.split(",") if n.strip()]

    # 她说了「去查查」但没真查时，后台补查一次并主动补发一条
    followup_search_enabled: bool = True
    followup_search_delay: float = 3.0   # 查之前先等一会儿，像真的在查

    # 她的一天：每天定时生成一份日程，聊天时知道自己此刻在做什么
    schedule_enabled: bool = True
    schedule_hour: int = 7
    schedule_history_days: int = 3

    # QQ 空间说说：她自己决定发，一天 1~3 条
    qzone_enabled: bool = False
    # 0 = 不限条数 / 不限间隔，想发就发
    qzone_daily_max: int = 0
    qzone_min_gap_minutes: int = 0
    qzone_max_chars: int = 100
    # 1 所有人可见 / 4 好友可见 / 64 仅自己可见
    qzone_visibility: int = 1
    # 当天一条都没发时补一条；她完全自主时可以关掉
    qzone_fallback_enabled: bool = False
    qzone_fallback_hour: int = 20
    qzone_fallback_minute: int = 0
    qzone_history: int = 5
    # 每轮回复后自动发一条说说的概率（她没自己调工具时兜底）
    qzone_auto_rate: float = 0.03

    # 个性签名：每天定时换一次
    signature_enabled: bool = False
    signature_hour: int = 9
    signature_minute: int = 0
    signature_max_chars: int = 30
    signature_daily_max: int = 0   # 0 = 不限
    signature_history: int = 5
    # 每轮回复后自动换签名的概率
    signature_auto_rate: float = 0.02

    # 主动开口
    proactive_enabled: bool = True
    proactive_check_minutes: int = 10
    proactive_daily_max: int = 5
    proactive_min_gap_minutes: int = 90
    proactive_idle_min: int = 30
    proactive_idle_max: int = 90
    proactive_quiet_start: int = 0
    proactive_quiet_end: int = 7
    proactive_probability: float = 0.6
    proactive_miss_hours: int = 6

    # 被晾情绪
    emotion_ignored_sulk_after: int = 2
    emotion_sulk_hours: float = 2.0
    emotion_relief_minutes: int = 30
    emotion_fade_hours: float = 3.0

    # 表情包
    sticker_enabled: bool = True
    sticker_dir: Path = Path("data/stickers")
    sticker_auto_rate: float = 0.15
    sticker_daily_max: int = 20
    sticker_min_turns_gap: int = 2
    sticker_min_score: float = 0.6
    sticker_max_size_kb: int = 2048
    sticker_sub_type: str = "1"
    # 表情包检索：给 nekowhale 那 322 张建向量索引，和关键词混合排序
    sticker_vector_search: bool = True
    sticker_vector_weight: float = 0.5
    # 别人发的表情包自动收进图库
    sticker_auto_import: bool = True
    sticker_auto_import_daily_max: int = 20
    sticker_auto_import_max_kb: int = 2048
    # nekowhale 表情包知识库
    nekowhale_enabled: bool = True
    nekowhale_meta: Path = Path("meta/nekowhale.json")
    nekowhale_site: str = "https://kiriyuki.com"
    nekowhale_gif_base: str = "/media/gif"
    nekowhale_packs: str = "大肥鱼,大肥鱼和GPT娘"

    @property
    def nekowhale_pack_list(self) -> list[str]:
        return [p.strip() for p in self.nekowhale_packs.split(",") if p.strip()]

    # 视觉理解
    vision_enabled: bool = True
    # deepseek = 用主模型的图像理解（快、准、不占内存）；ollama = 本地小模型
    vision_provider: str = "deepseek"
    vision_base_url: str = "http://127.0.0.1:11434/v1"
    vision_api_key: str = "ollama"
    vision_model: str = "minicpm-v:8b"
    vision_timeout: float = 120.0
    vision_max_image_mb: int = 5
    vision_cache_days: int = 7

    # 联网搜索：复用 DEEPSEEK_API_KEY，不需要额外账号
    search_enabled: bool = True
    search_top_k: int = 5
    search_daily_max: int = 50
    search_cache_minutes: int = 60
    search_timeout: float = 15.0
    search_fetch_max_chars: int = 6000

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

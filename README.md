# qqbot

一个只服务单个用户的 QQ AI 搭子：**NapCat（OneBot 11）+ DeepSeek + 长期记忆**。

它不群发、不加好友、不发说说，只和指定的一个人聊天。适合想要一个"有人味"的私人 QQ 搭子，而不是一个机器人管家。

## 特性

- **单用户白名单**：只回复 `OWNER_QQ` 的私聊，其他消息直接丢弃，连模型都不调用。
- **人格可编辑**：`src/qqbot/persona/persona.md` 一个 Markdown 文件定义性格、说话方式、边界。
- **三层记忆**：
  - 滚动会话摘要（每 20 条更新）
  - 结构化事实抽取（每 6 轮异步写入 SQLite）
  - 时间衰减检索（FTS 类字符匹配 + 半衰期 21 天，高置信事实不衰减）
- **长回复分片**：按 500 字 / 句末标点切分，不刷屏。
- **可扩展底座**：事件总线 + 模块注册 + 动作/工具注册 + 记忆 scope，加功能不用改核心（见 [扩展指南](docs/EXTENDING.md)）。
- **完全隐藏运行**：启动无终端窗口，未登录时自动打开浏览器扫码页。
- **零外部服务**：SQLite 单文件，不需要向量数据库。

## 架构

```
QQ 客户端
   │
NapCat（OneBot 11 协议端，登录小号）
   ├── 反向 WebSocket ──▶ qqbot FastAPI (:8080)   收事件
   └── HTTP API ◀──────── qqbot                   发消息
                              │
                    core/bus 事件分发（message / notice / request / meta）
                              │
                    modules/*（chat 默认启用，其余按需）
                              │
              prompt/composer 拼 system
                 ├─ persona
                 ├─ self_state（bot:self）
                 ├─ facts（user:<qq>）
                 ├─ relations（social:global）
                 ├─ summary（session scope）
                 └─ rules
                              │
                    runtime/simple（LLM + 工具循环）
                              │
                    分片 → send_private_msg
                              │
                    异步写 SQLite（摘要 / 事实 / 联系人 / 关系）
```

## 环境要求

- Windows 10 / 11
- Python 3.12（用 [uv](https://docs.astral.sh/uv/) 管理）
- [NapCat](https://github.com/NapNeko/NapCatQQ)（Windows 版，自带运行时）
- 一个 DeepSeek（或任意 OpenAI 兼容）API Key
- 一个不常用的小号（重要，见文末免责）

## 快速开始

### 1. 准备依赖

```powershell
uv sync --python 3.12
```

### 2. 配置

复制 `.env.example` 为 `.env`，至少填：

```ini
OWNER_QQ=你的QQ号
DEEPSEEK_API_KEY=sk-xxxx
BOT_QQ=机器人小号
```

### 3. 启动 NapCat 并登录

下载 NapCat Windows 版解压到 `napcat/`，运行一次登录小号。登录后在 NapCat WebUI 配置：

- HTTP 服务端：`127.0.0.1:3000`
- 反向 WebSocket：`ws://127.0.0.1:8080/onebot/v11/ws`

（也可以直接参考 `napcat/napcat/config/onebot11_<QQ>.json` 的写法。）

### 4. 启动

```powershell
.\scripts\start-hidden.ps1
```

或者双击 `launch.vbs`：无窗口启动，未登录时自动打开浏览器扫码页。

### 5. 停止

```powershell
.\scripts\stop-hidden.ps1
```

或者双击 `stop.vbs`。

## 开机自启

以管理员身份运行一次：

```powershell
.\scripts\install-autostart.ps1
```

会注册一个登录时触发的计划任务。取消：

```powershell
Unregister-ScheduledTask -TaskName qqbot-autostart -Confirm:$false
```

## 配置项

| 变量 | 说明 | 默认 |
|---|---|---|
| `OWNER_QQ` | 唯一允许聊天的 QQ，为 0 时拒绝启动 | `0` |
| `BOT_QQ` | 机器人登录的 QQ（仅记录用） | 空 |
| `DEEPSEEK_API_KEY` | 模型 API Key | 空 |
| `DEEPSEEK_BASE_URL` | OpenAI 兼容地址 | `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | 模型名 | `deepseek-chat` |
| `ONEBOT_HTTP_URL` | NapCat HTTP API | `http://127.0.0.1:3000` |
| `ONEBOT_WS_PATH` | 反向 WS 路径 | `/onebot/v11/ws` |
| `HOST` / `PORT` | 本服务监听地址 | `127.0.0.1:8080` |
| `DAILY_TOKEN_BUDGET` | 每日 token 上限 | `200000` |
| `ENABLED_MODULES` | 启用的模块，逗号分隔 | `chat,diary,maintenance` |
| `SUMMARY_EVERY` | 每多少条更新一次会话摘要 | `10` |
| `SUMMARY_TOKEN_BUDGET` | 上下文涨到多少字也触发摘要 | `6000` |
| `EPISODE_EVERY` | 每多少条生成一段事件记录 | `20` |
| `DIARY_ENABLED` | 是否写日记 | `true` |
| `DIARY_HOUR` / `DIARY_MINUTE` | 每日日记时间 | `0:10` |
| `DIARY_BACKFILL_DAYS` | 启动时最多补写几天 | `7` |
| `DIARY_PROMPT_DAYS` | prompt 里带几篇日记 | `3` |
| `MEMORY_VECTOR_ENABLED` | 是否启用向量检索 | `true` |
| `EMBEDDING_BASE_URL` | embedding 接口（Ollama） | `http://127.0.0.1:11434/v1` |
| `EMBEDDING_MODEL` / `EMBEDDING_DIM` | 模型与维度 | `bge-m3` / `1024` |
| `TOOLS_ENABLED` | 是否把工具暴露给模型 | `false` |
| `TOOL_MAX_ROUNDS` | 工具调用最大轮数 | `4` |
| `MCP_SERVERS` | MCP server 配置（JSON 数组） | 空 |
| `REPLY_DELAY_MIN/MAX` | 回复前随机延迟（秒） | `0.5` / `3.0` |
| `REPLY_SEGMENTS_MAX` | 一次最多回几条 | `3` |
| `PROACTIVE_ENABLED` | 是否主动找你 | `true` |
| `PROACTIVE_IDLE_MIN/MAX` | 空闲多久才可能主动（分钟，随机） | `30` / `90` |
| `PROACTIVE_DAILY_MAX` | 每天主动上限 | `5` |
| `STICKER_DIR` | 本地表情包目录 | `data/stickers` |
| `VISION_ENABLED` | 是否启用图片理解 | `true` |
| `VISION_MODEL` | 视觉模型 | `minicpm-v:8b` |

> 多段回复、主动开口、被晾情绪、表情包、图片理解与多轮追问的完整说明见 [docs/BEHAVIOR.md](docs/BEHAVIOR.md)。

> 完整配置见 `src/qqbot/config.py`。

## 目录

```
src/qqbot/
  main.py           入口（FastAPI + 反向 WS）
  app.py            AppContext 组装与模块加载
  config.py         配置
  core/             事件、消息段、总线、会话、分片
  onebot/           NapCat API 封装、WS
  capabilities/     平台动作注册表（发消息/表情/语音/签名/说说/好友）
  tools/            模型工具注册表 + MCP 骨架
  runtime/          AgentRuntime 协议 + SimpleRuntime
  prompt/           PromptComposer + sections
  memory/           SQLite 存储、scope、联系人、关系、自我记忆、事件、日记、向量
  modules/          功能模块（chat/diary/maintenance/qzone/profile/friends/group/media/self_memory）
  scheduler/        APScheduler 封装
  persona/          persona.md 与人设加载
docs/EXTENDING.md   扩展指南
docs/MEMORY.md      记忆系统说明（六层/写入/检索/日记/向量）
tests/              单元测试（pytest）
scripts/            启动 / 停止 / 安装自启 / 记忆统计
launch.vbs          无窗口启动入口
stop.vbs            无窗口停止入口
login.html          自动刷新的扫码页
```

## 扩展

加功能的标准流程、接口示例、scope 约定见 [docs/EXTENDING.md](docs/EXTENDING.md)。

简单说：

1. 写 `src/qqbot/modules/xxx.py`，实现 `setup(ctx)`；
2. 在 `modules/__init__.py` 的 `MODULES` 里加一行；
3. `.env` 里 `ENABLED_MODULES=chat,xxx`。

## 调试

打印当前真实拼装的 prompt：

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe scripts\print_prompt.py
```

跑测试：

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m pytest -q
```

日志在 `data/qqbot.log`，错误在 `data/errors.log`。

## 免责声明

- **登录个人号机器人违反 QQ 用户协议**，有封号风险。请只用小号，不要用在主号上。
- 本项目不提供任何绕过平台风控的能力，也不鼓励这样做。
- `.env`、`data/`、`napcat/` 均已被 `.gitignore` 排除，请勿把 API Key 或聊天数据提交到仓库。
- 模型输出可能有误，请自行判断。

## License

MIT

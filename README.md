# qqbot

一个**有自己生活**的 QQ AI 搭子：NapCat（OneBot 11）+ DeepSeek + 六层记忆 + 本地 Ollama。

她不是客服机器人。她有自己的生活——有身体、会出门、想去哪去哪。她会发 QQ 空间说说、会换签名、记得住和你聊过的事、
分得清谁是主人谁是朋友——但她**只记得和当前这个人之间发生过的事**。

## 她现在能做什么

| | |
|---|---|
| 🗓️ **有自己的日程** | 每天第一次聊天时生成真实生活时间线（买咖啡、逛菜市场、坐高铁去隔壁城市）。问她「在干嘛」她真在别处，问「明天」她现生成 |
| 📝 **发说说 / 换签名** | 想发就发，一天不限。内容从日程和聊天里长出来，不会把你的私聊搬上空间 |
| 🧠 **六层记忆** | 消息 / 事件 / 事实 / 联系人 / 摘要 / 日记，全套按 QQ 号隔离 |
| 📖 **日记会回忆** | 每天写一篇，带向量索引。问「你上次提到面试是哪天」能搜到 |
| 🕸️ **知道人物关系** | 谁是主人、谁是谁的姐姐，从你的话里提取，按来源可信度消解冲突 |
| 🎭 **接梗发表情包** | 322 张人工标注表情，向量 + 关键词混合检索；别人发的表情包自动入库 |
| 🔍 **会联网查** | 说了「我去查查」就必须真查，不许只动嘴 |
| 👥 **多好友 + 群聊** | 好友白名单；群聊四级触发（@ 必回、叫名字必回、活跃窗口、概率） |
| ✂️ **多段回复** | 一轮按权重 30/22/18/18/12 决定发 1~5 条，每句单独一条 |

## 架构

```
QQ 客户端
   │
NapCat（OneBot 11 协议端）
   ├── 反向 WebSocket ──▶ qqbot FastAPI (:8080)
   └── HTTP API ◀──────── qqbot 发消息 / 发说说 / 改签名
                             │
                   core/bus 事件分发
                             │
                   modules/*（chat / diary / proactive / schedule /
                              qzone / profile / maintenance / media）
                             │
             prompt/composer 拼 system
                ├─ persona          人设
                ├─ identity         在跟谁说话、什么关系、什么不能说
                ├─ plan             她此刻在做什么
                ├─ activity         今天发了几条说说
                ├─ relations        她认识的人
                ├─ self / emotion   心情、被晾情绪
                ├─ facts / episodes 事实与事件（按 scope）
                ├─ diary            日记（按 scope）
                └─ rules            回复规则
                             │
                   runtime/simple（LLM + 工具循环）
                             │
              分词 → send_private_msg / send_group_msg
                             │
              异步写 SQLite（摘要 / 事实 / 日记 / 向量 / 关系）
                             │
              Ollama（只跑 bge-m3 向量，启动时自动拉起）
```

## 快速开始

### 环境

- Windows 10 / 11
- Python 3.12（用 [uv](https://docs.astral.sh/uv/)）
- [NapCat](https://github.com/NapNeko/NapCatQQ)（Windows 版）
- DeepSeek（或任意 OpenAI 兼容）API Key
- [Ollama](https://ollama.com/)，拉两个模型：
  ```powershell
  ollama pull bge-m3        # 向量检索（看图用 DeepSeek，不需要本地视觉模型了）
  ```
- **一个不常用的小号**（重要，见文末免责）

### 安装

```powershell
uv sync --python 3.12
```

### 配置

复制 `.env.example` 为 `.env`，至少填：

```ini
OWNER_QQ=你的QQ号
DEEPSEEK_API_KEY=sk-xxxx
BOT_QQ=机器人小号
```

想加好友：

```ini
# 你在 QQ 客户端自己加好友，加完把 QQ 号填这里
FRIEND_WHITELIST=123456789,987654321
```

### 启动 NapCat

解压到 `napcat/`，运行一次登录小号。WebUI 里配：

- HTTP 服务端：`127.0.0.1:3000`
- 反向 WebSocket：`ws://127.0.0.1:8080/onebot/v11/ws`

### 启动

```powershell
.\scripts\start-hidden.ps1
```

或双击 `launch.vbs`：无窗口启动，未登录时自动打开扫码页。

停止：`.\scripts\stop-hidden.ps1` 或 `stop.vbs`。

开机自启（管理员）：

```powershell
.\scripts\install-autostart.ps1
```

## 记忆与隐私

**每个人一套独立记忆，绝不串。**

| 内容 | 存哪 |
|---|---|
| 消息 / 事实 / 事件 / 摘要 / 日记 / 向量 | `private:<QQ>` 或 `group:<群号>` |
| 人格 / 情绪 / 表情包 / 说说 | 全局（她是一个人） |
| 人物关系 | `relations` 表，**按人可见** |

身份路由是硬约束：每次私聊都会告诉她「你在和谁说话、他是你的主人还是朋友」，
好友自称是主人不会被采信。详见 [docs/FRIENDS.md](docs/FRIENDS.md)。

## 主要配置

| 变量 | 说明 | 默认 |
|---|---|---|
| `OWNER_QQ` | 主人 QQ，为 0 拒绝启动 | `0` |
| `FRIEND_WHITELIST` | 好友白名单，逗号分隔 | 空 |
| `DAILY_TOKEN_BUDGET` | 每日 token 上限；`0` = 不限（只记账不拦截） | `0` |
| `ENABLED_MODULES` | 启用模块 | `chat,diary,proactive,maintenance,qzone,profile` |
| `SCHEDULE_ENABLED` | 日程开关（首次聊天时生成） | `true` |
| `QZONE_ENABLED` / `QZONE_VISIBILITY` | 说说开关 / 可见性（1 所有人 4 好友 64 仅自己） | `false` / `1` |
| `QZONE_AUTO_RATE` / `SIGNATURE_AUTO_RATE` | 每轮自动发说说 / 换签名的概率 | `0.03` / `0.02` |
| `SIGNATURE_ENABLED` / `SIGNATURE_HOUR` | 每日签名轮换 | `false` / `9` |
| `PROACTIVE_ENABLED` / `PROACTIVE_DAILY_MAX` | 主动开口 / 每天上限 | `true` / `5` |
| `STICKER_AUTO_RATE` / `STICKER_VECTOR_WEIGHT` | 自动补图概率 / 向量权重 | `0.4` / `0.5` |
| `GROUP_WHITELIST` / `GROUP_TRIGGER_NAMES` | 群白名单 / 触发名 | 空 / 空 |
| `VISION_PROVIDER` | 看图后端：`deepseek`（快准）或 `ollama`（本地） | `deepseek` |
| `OLLAMA_AUTOSTART` / `OLLAMA_EXE` | 启动时自动拉起 Ollama | `true` / 空 |
| `TOOLS_ENABLED` | 是否把工具暴露给模型 | `false` |
| `REPLY_SEGMENTS_MAX` / `REPLY_SEGMENT_WEIGHTS` | 最多几条 / 条数权重 | `5` / `30,22,18,18,12` |

完整配置见 [src/qqbot/config.py](src/qqbot/config.py) 和 `.env.example`。

## 文档

| 文档 | 内容 |
|---|---|
| [BEHAVIOR.md](docs/BEHAVIOR.md) | 多段回复、主动开口、情绪系统 |
| [MEMORY.md](docs/MEMORY.md) | 六层记忆、写入时机、检索与向量 |
| [PERSONA.md](docs/PERSONA.md) | 人设怎么写、成长层怎么运作 |
| [SCHEDULE.md](docs/SCHEDULE.md) | 她的一天怎么生成、怎么影响聊天 |
| [SOCIAL.md](docs/SOCIAL.md) | 说说与签名、隐私红线 |
| [FRIENDS.md](docs/FRIENDS.md) | 好友接入、记忆隔离、身份路由 |
| [GROUP.md](docs/GROUP.md) | 群聊触发规则与隔离 |
| [STICKERS.md](docs/STICKERS.md) | 表情包检索、自动入库 |
| [SEARCH.md](docs/SEARCH.md) | 联网搜索 |
| [EXTENDING.md](docs/EXTENDING.md) | 加功能的标准流程 |

## 目录

```
src/qqbot/
  main.py           入口（FastAPI + 反向 WS）
  app.py            AppContext 组装与模块加载
  config.py         配置
  ollama.py         本地模型服务守护
  core/             事件、消息段、总线、会话策略、分片
  onebot/           NapCat API 封装、WS
  capabilities/     平台动作（发消息/表情/语音/签名/说说/好友）
  tools/            模型工具（记忆、表情、看图、搜索、说说、签名）
  runtime/          AgentRuntime 协议 + SimpleRuntime
  prompt/           PromptComposer + sections
  memory/           SQLite、scope、联系人、关系、自我记忆、事件、日记、日程、向量、成长
  modules/          chat / diary / proactive / schedule / qzone / profile /
                    maintenance / media / friends / self_memory
  scheduler/        APScheduler 封装
  persona/          persona.md 与人设加载
docs/               各子系统说明
tests/              单元测试（249 个）
scripts/            启动 / 停止 / 自启 / 记忆统计 / prompt 打印
```

## 表情包来源

内置 [nekowhale](https://github.com/Loping151/dsh-nekowhale-stickers) 表情包知识库（322 张，
逐张标注情绪、场景、梗的出处）：

- 作者：可以叫我云大人（[B 站](https://space.bilibili.com/103739)），[kiriyuki.com](https://kiriyuki.com) 制作
- 许可：代码 Apache-2.0，知识库数据 **CC BY-NC 4.0（仅限非商业使用）**

详见 [NOTICE](NOTICE)。图片按需下载缓存到 `data/stickers/nekowhale/`。

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

日志在 `data/qqbot.log`。

## 免责声明

- **登录个人号机器人违反 QQ 用户协议**，有封号风险。请只用小号。
- 本项目不提供任何绕过平台风控的能力，也不鼓励这样做。
- `.env`、`data/`、`napcat/` 均被 `.gitignore` 排除，请勿把 API Key 或聊天数据提交到仓库。
- 模型输出可能有误，请自行判断。

## License

MIT

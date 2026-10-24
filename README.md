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
                        事件路由 → 白名单 → 拼 prompt
                              │
                        DeepSeek / OpenAI 兼容 API
                              │
                        分片 → send_private_msg
                              │
                        异步写 SQLite（摘要 / 事实）
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

> 完整配置见 `src/qqbot/config.py`。

## 目录

```
src/qqbot/
  main.py           入口（FastAPI + 反向 WS）
  config.py         配置
  onebot/           事件解析、NapCat API 封装
  core/             路由、白名单、消息分片
  llm/              OpenAI 兼容客户端、prompt 拼装
  memory/           SQLite 存储、摘要、事实抽取、检索
  persona/          persona.md 与人设加载
tests/              单元测试（pytest）
scripts/            启动 / 停止 / 安装自启
launch.vbs          无窗口启动入口
stop.vbs            无窗口停止入口
login.html          自动刷新的扫码页
```

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

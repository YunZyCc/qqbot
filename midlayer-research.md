# QQ AI 号「中间程序」调研笔记

> 目标：一个 QQ 号背后挂大模型，能聊天、有人格、会改签名/发说说、能处理陌生人加好友。
> 只比较「中间程序」（消息进来之后到调模型、回消息、做运营的那一层），协议端单独说明。

## 一、中间程序实际在做什么

```
QQ 平台
  │  (1) 协议端/官方 API：把消息变成统一事件
  ▼
接入适配层  ── 统一成 OneBot / 平台事件结构
  ▼
编排核心    ── 事件分发、会话隔离、触发判定（@我/关键词/随机插话）
  │
  ├─▶ 上下文/记忆层 ── 短期历史、长期记忆、用户画像
  ├─▶ 模型层       ── 多 provider 适配、prompt 拼装、流式输出、工具调用
  └─▶ 插件/能力层   ── 改签名、发说说、同意好友、定时任务、内容审核
  ▼
回消息 / 执行动作
```

GitHub 项目的差异，本质是**这五层里哪几层做成了产品、哪几层留给你自己写**。

## 二、三条实现路线

| 路线 | 代表 | 特点 |
|---|---|---|
| 一体化平台 | AstrBot、MaiBot、LangBot | 接入+编排+模型+WebUI 全包，装完就能跑 |
| 框架 + 插件 | NoneBot2、Koishi | 只做编排，接入靠适配器、功能靠插件，自由度最高 |
| 协议端 | NapCat、LLOneBot、Lagrange | 只负责把 QQ 登录态转成 OneBot 11 接口 |

成品机器人（真寻等）= 框架 + 一大包插件 + WebUI 的组合。

## 三、项目逐个看

### AstrBot（Python，AGPL-3.0-or-later，v4.29.x）
- 定位：一体化 Agent 聊天机器人平台，多 IM 平台。
- 实现：适配器 `core/platform/sources/*` → 统一事件 → `event_bus` → `core/pipeline` 责任链（唤醒判定 → 白名单 → 限流 → 内容安全 → 会话状态 → 预处理 → LLM/Agent → 结果装饰 → 回发）；插件层 `core/star`；persona_mgr 多人格；知识库 faiss+BM25；MCP/Skills/Agent 沙箱；Quart 后端 + Vue WebUI（:6185）。
- QQ：aiocqhttp（OneBot v11，接 NapCat/Lagrange）+ QQ 官方机器人适配器。
- 记忆：内置会话级（SQLite），**长期记忆靠插件**（iris_memory、livingmemory 等）。
- 空间/资料：`astrbot_plugin_qqprofile` 改头像/昵称/签名/状态（签名同步空间）；`astrbot_plugin_qzone` 发说说/看说说/评论/点赞/定时自动发/LLM 写说说/表白墙审核。
- 优点：离「QQ 生活号」最近，插件市场 1000+，人格/空间/资料都有现成件。
- 缺点：AGPL 传染性；迭代快、有破坏性变更；陌生人私聊要自己配白名单和唤醒策略。

### MaiBot 麦麦（Python，GPL-3.0，约 6.4k star）
- 定位：QQ 群里的「数字生命」，核心是「像人」而不是「有用」。不走 NoneBot 插件路线，是「适配器即插件 + 自研内核」。
- 实现：统一 QQ 连接器（SnowLuma/NapCat 本地登录 + QQ 官方 API）→ `src/platform_io`（去重、放行策略、出站追踪）→ `src/chat`：message_receive → chat_stream → heart_flow → **planner → replyer 两段式**。planner 决定「说不说、什么时候说」：`talk_value`、消息防抖（off/fast/natural/steady）、频率/动态触发、不回复退避、`focus_mode` 一次只专注一个聊天流。
- 人格：`[personality]` 三段式（personality/behavior_style/reply_style），按概率切换风格；表达学习（向量召回）+ 黑话学习，按群/私聊隔离。
- 记忆：`src/A_memorix` 2.0 双路检索（FAISS 向量 + 图谱关系），存段落/关系/Episode/人物画像，带 reinforce/protect/freeze/recycle_bin 的遗忘机制，SQLite FTS5 + 向量库。
- 说说/签名：本体不支持；发说说靠第三方插件 Maizone（发/读/点赞/评论/定时/AI 配图，走 QQ 空间 Web 私有接口 + cookie）；改签名需自调 OneBot 扩展 API。
- 优点：拟人化、记忆、主动插话深度第一，文档/WebUI 完善。
- 缺点：重（Python+FAISS+SQLite，要配嵌入模型）、token 消耗大、行为不可控（会主动插话/不回）、GPL-3.0 + EULA 约束、空间能力靠第三方。

### LangBot（Python，Apache-2.0，v4.11.x）
- 定位：生产级多租户 IM Agent 平台。
- 实现：适配器 → RuntimeBot → MessageAggregator → QueryPool → Controller → RuntimePipeline（数据库配置生成的责任链：规则/封禁/过滤/限流/命令/chat）→ Runner；插件与沙箱独立进程（Plugin Runtime、Box Runtime）；RAG + chromadb/qdrant；MCP 双向；Alembic 迁移；WebUI :5300。
- 优点：工程化最强（多租户、并发控制、限流、监控、迁移），Apache-2.0 商用友好。
- 缺点：企业客服导向，QQ 空间/资料无现成插件，人格要手搓 prompt，架构重。

### NoneBot2（Python，MIT，约 7.7k star）
- 定位：异步机器人框架，不是成品。
- 实现：适配器把平台事件解析成 Event → 按 priority 交给 Matcher（on_command/on_message）→ rule/permission 命中执行 handler，`block=True` 阻断后续；依赖注入按类型注解注入 Bot/Event/State/Matcher，用法接近 FastAPI；插件即模块。
- 接 OneBot：`adapter-onebot`（MIT，v11/v12），推荐反向 WS（ws://127.0.0.1:8080/onebot/v11/ws），也可 HTTP POST / 正向 WS。
- 优点：生态最大（官方商店上千插件）、最灵活、学习价值高。
- 缺点：LLM、记忆、人格、WebUI、空间运营全要自己搭。

### Koishi（TypeScript/Node，MIT，约 6.3k star）
- 定位：跨平台机器人框架 + 控制台。
- 实现：Context + Service 的 IoC 模型，插件声明 `inject`，依赖服务未就绪则不加载、变化则回滚重载；适配器抽象 Bot 与消息元素，`adapter-onebot` 支持多账号；自带 Web 控制台（在线插件市场、配置、日志，插件可注册 Vue 页面），3000+ 插件，模块热重载。
- 优点：TS 开发者体验最好，控制台最顺手，可视化运维开箱即用。
- 缺点：QQ 侧依赖 onebot 适配器 + 协议端；LLM/向量库生态不如 Python 侧。

### Zhenxun_Bot 真寻（Python，AGPL-3.0）
- 定位：基于 NoneBot2 的成品娱乐机器人。
- 实现：大量内置插件 + 插件商店 + WebUI；完整的**好友/群请求管理**（可配置自动同意）、权限系统、CD/阻塞/每日次数限制。
- 优点：功能齐全、请求管理现成，适合当群管家。
- 缺点：功能型机器人，LLM 人格不是主线；AGPL 约束二次分发。

### NapCat（协议端，约 11.3k star）
- 作用：基于 NTQQ 的 OneBot 11 协议端（TypeScript），只负责登录、保活、协议编解码，不做业务。不 hook 客户端，由启动器调 QQ 的 Node 模块，无头、不依赖 Electron，内存约 50–100 MB。
- 部署：Windows 解压即用；Linux 脚本/Docker；登录后在 WebUI 配置 OneBot 连接（HTTP/WS 正反向、token）。
- 关键扩展 API：
  - `set_self_longnick`：改个性签名
  - `set_qq_profile` / `set_qq_avatar`：改昵称/头像
  - `set_online_status`：改在线状态
  - `SendQzoneMsg`：发说说，支持正文/多图/可见范围（`ugc_right`）
  - `set_friend_add_request`（OneBot 标准）：处理好友请求
  - `get/set_doubt_friends_add_request`：处理「可疑好友」请求
- 注意：无数据库，消息按 LRU 约 5000 条过期；官方安全文档只谈社交风控与掉线，不承诺不封号，建议与常用号隔离 IP/设备、控制频率；登录个人号违反平台协议；许可为混合协议，禁止未经授权基于其代码二次开发。
- 同层替代：LLOneBot（现名 LuckyLilliaBot，GPL-2.0，约 3.7k star，支持 OneBot11/Satori/Milky）、Lagrange.Core（纯 C# 协议实现，无需客户端）。
- 自研注意：`aiocqhttp` 已于 2023-06 实质停更，别用它，直接写 WebSocket 客户端。

## 四、对比表

| 维度 | AstrBot | MaiBot | LangBot | NoneBot2 | Koishi | 真寻 |
|---|---|---|---|---|---|---|
| 类型 | 一体化 | 一体化 | 一体化 | 框架 | 框架 | 成品 |
| 许可 | AGPL-3.0 | GPL-3.0 | Apache-2.0 | MIT | MIT | AGPL-3.0 |
| 上手 | 低 | 中 | 中 | 高 | 中高 | 中 |
| 可定制 | 中 | 中 | 中 | 高 | 高 | 中 |
| 人格/记忆 | persona+知识库，长期记忆靠插件 | 强（双路检索/画像/遗忘/主动发言） | 中（RAG） | 自理 | 自理 | 弱 |
| 说说/签名 | 两个现成插件 | Maizone 插件 / 自调 API | 自写 | 自写 | 自写 | 自写 |
| 好友请求 | 自写（API 现成） | 放行策略（自动同意未确认） | 自写 | 自写 | 自写 | **内置自动同意** |
| 多平台 | 强 | 弱（QQ 为主） | 强 | 强 | 强 | 中 |
| 资源占用 | 中 | 高 | 中高 | 低 | 中 | 中高 |
| 适合 | 多平台通用助手/生活号 | 有人味的单号/群友 | 多机器人/客服 | 深度自研 | TS 开发者 | 群管家 |

## 五、针对目标的结论

1. **AstrBot 已覆盖大部分**：人格内置，签名/头像/状态有 qqprofile，说说/评论/点赞/定时/LLM 写稿有 qzone。剩下的主要是「好友请求怎么审」「说说内容怎么把关」「记忆怎么长期化」。
2. **要「像人」加 MaiBot**：它把记忆、情绪、主动发言做得更深，但空间运营要自己补。
3. **要商用/多号运营选 LangBot**：Apache-2.0 + 工程化，但 QQ 生活号玩法要自写插件。
4. **自研的判断标准**：只要一个号、一个人设、一套规则，直接写 OneBot WS 客户端 + SQLite + 定时任务（几百行）反而更清楚。
5. 共同缺口（需要自己补）：
   - 说说内容审核与发布策略（频率、敏感词、草稿确认）
   - 好友请求的人设化审核（自动通过有风控，建议半自动）
   - 聊天/说说/好友画像共享的长期记忆
   - 主动行为调度（定时、事件触发、节流）
   - 风控：频率限制、敏感词、内容审核、异常行为熔断

## 六、参考

- https://github.com/AstrBotDevs/AstrBot
- https://github.com/Mai-with-u/MaiBot
- https://github.com/langbot-app/LangBot
- https://github.com/nonebot/nonebot2
- https://github.com/koishijs/koishi
- https://github.com/HibiKier/zhenxun_bot
- https://github.com/NapNeko/NapCatQQ
- https://github.com/Zhalslar/astrbot_plugin_qqprofile
- https://github.com/Zhalslar/astrbot_plugin_qzone
- https://github.com/internetsb/Maizone
- https://github.com/LLOneBot/LuckyLilliaBot
- https://github.com/nonebot/aiocqhttp
- https://github.com/botuniverse/onebot-11

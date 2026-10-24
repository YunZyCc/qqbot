# 记忆系统

## 六层结构

| 层 | 表 | 写入时机 | 用途 |
|---|---|---|---|
| L0 消息 | `messages` | 每轮同步 | 最近 30 条回放 |
| L1 事件 | `episodes` | 每 20 条 | 客观事件（谁做了什么），进 prompt |
| L2 事实 | `facts` | 信号词触发 + 每 6 轮兜底 | 结构化长期事实 + 近期关注 |
| L3 画像 | `contacts` / `relations` | 每日聚合 | 好友画像与关系 |
| L4 摘要 | `summaries` | 每 10 条 / 超预算 / 每日 | session + rolling 两级 |
| L5 日记 | `diaries` | 每日 + 启动补写 | 第一人称叙事记忆 |

## 事实分两类

`facts.source` 区分：

- `fact`：稳定、可长期复用。偏好、经历、关系、稳定状态、明确承诺。
  `predicate` 会过一遍 `PREDICATE_VOCAB` 收敛（爱→喜欢、在→在做…），保证关键词检索命中。
- `focus`：近期关注，几天到几周过期（`FOCUS_TTL_DAYS`，默认 3）。
  指「最近在看/在玩/在忙什么」。`predicate` **不收敛**，否则「最近在看比赛」和「最近在调机器人」会被压成同一条。

唯一索引是 `(scope, source, subject, predicate)`，所以同一个 predicate 下 fact 和 focus 可以共存。

prompt 里分两段渲染：

```
你记得的关于对方的信息：          ← fact
对方最近在忙/关注的事（可能已经变了，别当成永久设定）：  ← focus
```

## 写入链路

```
收到消息
  ├─ 同步：messages 写入 user 消息
  ├─ 同步：读历史/事实/事件/摘要/日记 → 调模型
  ├─ 同步：messages 写入 assistant 回复
  ├─ 信号词命中（喜欢/讨厌/住在/最近/在看…）→ 立即抽记忆
  │     └─ 只抽 facts_since 之后的新消息，最多 20 条，避免重复抽取
  │     └─ 分 fact / focus → 清洗 object → upsert → 写向量
  ├─ 每 6 轮兜底抽记忆
  ├─ 每 10 条 / 超 6000 字 / 每日 → 更新 session 摘要 + 写向量
  └─ 每 20 条 → 生成 episode + 写向量
```

所有抽取/摘要/事件/向量写入都是 `asyncio.create_task`，不阻塞回复。

抽取结果都会计数到 `settings` 表：

- `facts_attempt:*`：调用次数
- `facts_empty:*`：模型返回空（对话确实没有可复用信息时会这样）
- `facts_parse_error:*`：JSON 解析失败
- `facts_written:*`：成功写入条数

低置信（<0.6）事实写 `status='pending'`，不覆盖已有高置信事实，也不参与检索。

对象清洗：模型抽到「讨厌：对方说行吧」时，`_clean_object` 会把「对方/助手/机器人/小毒」统一成「你」，
变成「讨厌：你说行吧」——这样机器人自己读得懂。

## 读取链路

每次回复前读取：

1. 最近 30 条消息
2. facts → 关键词 + 向量 RRF 混合，取 top 5
3. focus → 取最近 5 条、TTL 内的，补进事实段
4. episodes → 关键词 + 向量 RRF 取 3 条；问句跟历史无关时退化为最近 3 条
5. rolling + session 摘要
6. 最近 3 天日记（每篇截 200 字）
7. 联系人画像、关系、自我状态、情绪

Prompt 顺序：

```
人设 → 自我状态 → 情绪 → 事实(含 focus) → 事件 → 关系 → 图片 → 日记 → 摘要 → 工具提示 → 输出规则 → 历史
```

组装逻辑在 `modules/chat.py::build_reply_messages`，`scripts/print_prompt.py` 走同一个函数，
所以调试看到的就是真实 prompt。

## 日记

- 每天一篇，`diaries(date PK, scope='bot:self', text, mood, highlights, source_msg_count)`。
- **有对话**：回顾式，只基于真实消息，写聊了什么、感受、期待。
- **没对话**：独处式，写整理记忆、翻旧聊天、想小事、期待；不虚构对话，不写物理生活。
- **启动补写**：服务启动 3 秒后，从昨天往前最多 `DIARY_BACKFILL_DAYS` 天，缺哪天补哪天。
- **每日定时**：`DIARY_HOUR:DIARY_MINUTE` 写前一天。
- 已存在则跳过，重复启动不会重写。

## 向量检索

- 后端：Ollama `bge-m3`（1024 维），OpenAI 兼容 `/v1/embeddings`。
- 存储：`embeddings(scope, ref_type, ref_id, model, dim, vector)`，float32 小端。
- 覆盖的 `ref_type`：`fact`、`episode`、`summary`、`sticker`。
- 检索：关键词排名 + 向量余弦排名 → RRF（k=60）→ top-k。
- 降级：Ollama 未启动或探测失败 → `NullEmbedding`，纯关键词，行为与旧版一致。
- 维度不一致直接拒绝写入，换模型需要重建。

### 历史数据补向量

服务启动 2 分钟后跑一次 `maintenance`，会把没有向量的 fact / episode / summary 补上，
所以换模型或新加索引后不用手动重建，等一次启动补跑即可。

### Ollama 准备

```powershell
ollama pull bge-m3
```

配置：

```
MEMORY_VECTOR_ENABLED=true
EMBEDDING_BASE_URL=http://127.0.0.1:11434/v1
EMBEDDING_API_KEY=ollama
EMBEDDING_MODEL=bge-m3
EMBEDDING_DIM=1024
FOCUS_TTL_DAYS=3
```

## 运维

查看各 scope 的记忆量、抽取成功率、日记：

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe scripts\memory_stats.py
```

打印当前真实 prompt（可传一个检索问句）：

```powershell
.\.venv\Scripts\python.exe scripts\print_prompt.py "你还记得我在看什么比赛吗"
```

诊断事实抽取：拿库里真实对话跑一次，打印模型原始返回，不写库：

```powershell
.\.venv\Scripts\python.exe scripts\check_facts.py 12
```

## 迁移

`schema_version` 存在 `settings` 表。加列走 `Store._migrate()` 的 `_ensure_column`，旧数据自动回填 `private:<owner>`。

当前版本 v6：
- v4：新增 `episodes`、`diaries`、`embeddings` 表，`summaries.type`、`facts.source` 列。
- v5：`messages.source`，self_state 情绪列。
- v6：`facts.source` 细分为 `fact` / `focus`，唯一索引改为 `(scope, source, subject, predicate)`，
  旧 `source='extract'` 统一迁移为 `fact`。

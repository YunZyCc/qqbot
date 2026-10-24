# 记忆系统

## 六层结构

| 层 | 表 | 写入时机 | 用途 |
|---|---|---|---|
| L0 消息 | `messages` | 每轮同步 | 最近 30 条回放 |
| L1 事件 | `episodes` | 每 20 条或每日 | 客观事件（谁做了什么） |
| L2 事实 | `facts` | 信号词触发 + 每 6 轮兜底 | 结构化长期事实 |
| L3 画像 | `contacts` / `relations` | 每日聚合 | 好友画像与关系 |
| L4 摘要 | `summaries` | 每 10 条 / 超预算 / 每日 | session + rolling 两级 |
| L5 日记 | `diaries` | 每日 + 启动补写 | 第一人称叙事记忆 |

## 写入链路

```
收到消息
  ├─ 同步：messages 写入 user 消息
  ├─ 同步：读历史/事实/摘要/日记 → 调模型
  ├─ 同步：messages 写入 assistant 回复
  ├─ 信号词命中（喜欢/讨厌/住在/答应/计划…）→ 立即抽事实
  │     └─ 归一化 predicate → upsert（旧值 superseded）→ 写向量
  ├─ 每 6 轮兜底抽事实
  ├─ 每 10 条 / 超 6000 字 / 每日 → 更新 session 摘要
  └─ 每 20 条 → 生成 episode
```

所有抽取/摘要/事件/向量写入都是 `asyncio.create_task`，不阻塞回复。

事实抽取有三种结果，都会计数到 `settings` 表：

- `facts_attempt:*`：调用次数
- `facts_empty:*`：模型返回空
- `facts_parse_error:*`：JSON 解析失败
- `facts_written:*`：成功写入条数

低置信（<0.6）事实写 `status='pending'`，不覆盖已有高置信事实，也不参与检索。

## 读取链路

每次回复前读取：

1. 最近 30 条消息
2. `user:<qq>` 的 facts → 关键词 + 向量 RRF 混合，取 top 5
3. rolling + session 摘要
4. 最近 3 天日记（每篇截 200 字）
5. 联系人画像、关系、自我状态

Prompt 顺序：

```
人设 → 自我状态 → 事实 → 关系 → 日记 → 摘要 → 工具提示 → 输出规则 → 历史
```

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
- 检索：关键词排名 + 向量余弦排名 → RRF（k=60）→ 时间衰减 → top-k。
- 降级：Ollama 未启动或探测失败 → `NullEmbedding`，纯关键词，行为与旧版一致。
- 维度不一致直接拒绝写入，换模型需要重建。

### Ollama 准备

```powershell
ollama pull bge-m3
```

或离线导入 GGUF：

```powershell
ollama create bge-m3 -f Modelfile
```

配置：

```
MEMORY_VECTOR_ENABLED=true
EMBEDDING_BASE_URL=http://127.0.0.1:11434/v1
EMBEDDING_API_KEY=ollama
EMBEDDING_MODEL=bge-m3
EMBEDDING_DIM=1024
```

## 运维

查看各 scope 的记忆量、抽取成功率、日记：

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe scripts\memory_stats.py
```

打印当前真实 prompt：

```powershell
.\.venv\Scripts\python.exe scripts\print_prompt.py
```

## 迁移

`schema_version` 存在 `settings` 表。加列走 `Store._migrate()` 的 `_ensure_column`，旧数据自动回填 `private:<owner>`。

当前版本 v4：新增 `episodes`、`diaries`、`embeddings` 表，`summaries.type`、`facts.source` 列。

# 好友接入与记忆隔离

除了主人，还能有几个人和她私聊，每人一套独立记忆。

## 怎么加好友

**你在 QQ 客户端自己加**，加完把 QQ 号告诉配置，重启生效：

```bash
# 逗号分隔，留空 = 只有主人能聊
FRIEND_WHITELIST=123456789,987654321
```

```powershell
# 改完重启
$c = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
if ($c) { Stop-Process -Id $c.OwningProcess -Force }
Start-Process .venv\Scripts\python.exe -ArgumentList "-m","qqbot.main" `
  -WorkingDirectory "D:\dev\qq-ai-bot" -WindowStyle Hidden `
  -Environment @{PYTHONPATH="src"; PYTHONIOENCODING="utf-8"}
```

启动日志会打：

```
好友白名单：123456789、987654321
```

**不在白名单里的人**：消息完全无视，不回复、不记录，数据库里连痕迹都没有。

## 隔离边界

### 每人独立（绝不共享）

| 内容 | 存储键 |
|---|---|
| 消息 | `private:<qq>` |
| 事实 | `private:<qq>` |
| 事件 | `private:<qq>` |
| 摘要 | `private:<qq>` |
| 向量 | `private:<qq>` |
| 图片描述 | `private:<qq>` |
| **日记** | `private:<qq>` |

### 共享（她是一个人）

| 内容 | 为什么共享 |
|---|---|
| 人格 / 成长 traits | 性格是一个人的，不该对谁换张脸 |
| 情绪状态 | 刚跟别人聊完还带着情绪，这很正常 |
| 表情包库 | 图库是她的收藏 |
| 说说 / 签名 | 那是她自己账号上的东西 |

### 群聊仍按群共享

`group:<群号>`，群里所有人的话混在一起（因为本来就是多人场合）。

## 身份路由（防止串话的关键）

光把数据分开不够。论文 [AFA](https://arxiv.org/abs/2604.25022) 的结论是：

> 只做存储隔离，人格归属准确率 35.7%；加上「明确告诉模型在跟谁说话」才到 61.3%。

所以每次私聊都会往 prompt 里塞一段：

```
你现在是在和「张三」（QQ 123456789）私聊。他是你的朋友。

你只记得和他之间发生的事。别人跟你说过什么、你和别人聊过什么，
一个字都不能说给他听，也不能暗示。
```

对主人则是「他是你的主人」。

群聊走另一段（`chatroom_section`），两段互斥。

## 日记规则

日记也按人拆开了（schema v9，主键 `(date, scope)`）：

| 谁 | 当天聊过 | 当天没聊 |
|---|---|---|
| 主人 | 写「回顾式」 | 写「独处式」（她自己的生活） |
| 好友 | 写「回顾式」 | **不写** |

给每个好友都写一篇独处日记会很怪——那不是她自己的生活，是在凑数。

生成时只读这个人自己的消息：

```python
messages = await store.messages_between(start, end, scope)
```

## 迁移历史

v9 迁移做了这些：

1. 旧 `diaries` 表主键只有 `date`（一天一篇，所有人混在一起）
2. 重建表，主键改成 `(date, scope)`
3. 旧数据 `scope='bot:self'` 全部归到 `private:<owner>`

启动时自动判断，只跑一次。迁移前会打日志：

```
迁移 diaries 主键为 (date, scope)，旧日记归到 private:2771230644
```

## 排查串记忆

### 确认白名单生效

```powershell
Select-String -Path .env -Pattern "FRIEND_WHITELIST"
```

启动日志里要有 `好友白名单：...`。

### 确认某个人的记忆是独立的

```powershell
@'
import sqlite3
c = sqlite3.connect("data/qqbot.db")
for scope in ("private:2771230644", "private:123456789"):
    n = c.execute("select count(*) from messages where scope=?", (scope,)).fetchone()[0]
    d = c.execute("select count(*) from diaries where scope=?", (scope,)).fetchone()[0]
    f = c.execute("select count(*) from facts where scope=?", (scope,)).fetchone()[0]
    print(f"{scope}: 消息 {n} 条 / 日记 {d} 篇 / 事实 {f} 条")
'@ | Set-Content -Encoding UTF8 data\_check.py
.\.venv\Scripts\python.exe data\_check.py
Remove-Item data\_check.py
```

### 看她的 prompt 里到底有什么

```powershell
.\.venv\Scripts\python.exe scripts\print_prompt.py "在吗"
```

检查：
- 有没有「你现在是在和「XX」私聊」
- `【日记】` 段里是不是只有这个人的
- `【关于对方的事实】` 里有没有别人的信息

## 已知局限

1. **隔离靠 scope 过滤，不是靠加密**。数据库是明文，能看到文件的人就能看到所有记忆。
2. **身份路由是软约束**。模型理论上可能自己「联想」出别人的事，但检索层根本查不到，所以概率极低。
3. **情绪是共享的**。A 把她惹生气了，B 来的时候她还在气头上。这是「一个人」的正常表现，不是 bug。
4. **好友看不到日记**。日记不会注入给别人，但她自己心里有数（prompt 里有身份段约束）。

## 人物关系怎么存

关系存在 `relations` 表，本质是一张很小的知识图谱：`contacts` 是节点，`relations` 是边。

```sql
src_qq      INTEGER   -- 一端（通常是主人）
dst_qq      INTEGER   -- 另一端
rel_type    TEXT      -- 枚举：family/friend/lover/colleague/classmate/other
label       TEXT      -- 具体叫法：「姐姐」「朋友」
confidence  REAL      -- 可信度
source_qq   INTEGER   -- 这话是谁说的
PRIMARY KEY(src_qq, dst_qq)
```

### 关系类型收敛

模型的自由文本（「是云海的朋友」）会被归到枚举上，原始说法留在 `label`。这样「姐姐」和「朋友」是两条不同的边，不会糊在一起。

### 冲突消解

同一对人只留一条边。新证据要**比旧的更可信**才能覆盖：

| 来源 | 可信度 |
|---|---|
| 主人说的 | 0.95 |
| 本人自称 | 0.70 |

所以 YY 说「我是你主人的爸爸」盖不掉主人自己说的关系——实测被拒绝了。

### 谁能看到什么

关系**按人可见**：

- 湫的对话 → 能看到「湫 是你的姐姐」
- YY 的对话 → 看不到湫和主人的任何关系，除非 YY 自己和主人有关系
- 主人的对话 → 全都能看到

她自己心里清楚主人是谁，但被要求不主动报给别人。

# 说说与签名

她的"对外发声"功能：发 QQ 空间说说、换个性签名。

## 一件必须先说清楚的事

她的日记、记忆、聊天记录，全都是**对着主人说的话**。里面写着「对方今天没来找我」「我毒了他一句」。

这些内容如果原样搬到 QQ 空间，好友看到会直接穿帮——这个人明明在跟谁聊天，怎么对着空气说话？

所以整套设计里最重要的一条是：

> **素材只提供情绪和氛围，具体事实一律不许照搬。**

代码层还加了一道硬过滤，见下面「隐私红线」。

---

## 说说：她自己决定发

### 主路径：工具

她聊天时自己判断「这事值得发」，调用 `post_qzone` 工具：

```python
post_qzone(content="今天风挺大的，把云吹得很散")
```

工具描述刻意写得克制：

> 发一条 QQ 空间说说，好友都能看到。当你真的想分享一件事、一句心情、一个观察时用。
> 一天最多 3 次，不是每天必须发。没有真正想说的就别调，别为了发而发。
> 发完不用在聊天里特意宣布。

### 流量控制（代码强制，不靠模型自觉）

| 限制 | 默认 | 配置项 |
|---|---|---|
| 每天上限 | 3 条 | `QZONE_DAILY_MAX` |
| 两次间隔 | ≥ 2 小时 | `QZONE_MIN_GAP_MINUTES` |
| 单条字数 | ≤ 100 字 | `QZONE_MAX_CHARS` |
| 可见性 | 所有人 | `QZONE_VISIBILITY` |

超限时工具返回一句话（「今天已经发了 3 条，够了」），不发布。

### 兜底：保证下限

每天 20:00 检查一次：**当天一条都没发 → 补一条**。

这样既有「她自己决定」的主动性，又不会一整天没动静。

### 内容怎么生成

素材三样，都只取情绪：

```
当天日记（心情基调）
+ 会话摘要（最近聊的氛围）
+ 最近事件（发生了什么，只看感觉）
```

再加上最近 5 条发过的说说，避免重复。

提示词里的硬规矩：

```
- 第一人称，像自己在空间里碎碎念，不是在对谁说话
- 不超过 100 字，越短越好，可以只写五六个字
- 不出现具体日期时间，用「今天下午」「刚刚」「夜深了」
- 不许 emoji、不许颜文字
- 不许出现「对方」「你」「主人」「聊天」「私聊」
- 不许指向任何具体的人
- 不许暴露自己是 AI
- 不要升华、不要金句、不要总结性收尾
```

---

## 隐私红线（代码层兜底）

模型不一定听话，所以生成后还要过两道：

**① emoji 过滤**

```python
_EMOJI = re.compile("[\U0001F300-\U0001FAFF...]")
```

**② 隐私词拒绝**

```python
_LEAK_WORDS = ("对方", "私聊", "主人", "聊天记录")
# 「你」单独判：允许「你们」泛指，其余算指向具体某人
```

命中任一条 → **这一次不发**，工具返回提示让模型重写。

---

## 签名：每天定时换

每天 9:00，生成一句 30 字以内的话，调 `set_self_longnick` 换掉。

和说说共用素材和隐私检查，但更短、更抽象。

不做成工具——签名一天换好几次显得神经质。

---

## 存储

新表 `social_posts`（schema v8）：

```sql
CREATE TABLE IF NOT EXISTS social_posts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT NOT NULL,           -- qzone | signature
    content    TEXT NOT NULL,
    tid        TEXT NOT NULL DEFAULT '', -- 空间返回的说说 id
    status     TEXT NOT NULL DEFAULT 'ok', -- ok | failed
    created_at REAL NOT NULL
);
```

用途：限额统计、间隔判断、去重历史、事后查账。

---

## 配置

```bash
# 说说
QZONE_ENABLED=true
QZONE_DAILY_MAX=3
QZONE_MIN_GAP_MINUTES=120
QZONE_MAX_CHARS=100
QZONE_VISIBILITY=1          # 1 所有人 / 4 好友 / 64 仅自己
QZONE_FALLBACK_HOUR=20
QZONE_FALLBACK_MINUTE=0
QZONE_HISTORY=5

# 签名
SIGNATURE_ENABLED=true
SIGNATURE_HOUR=9
SIGNATURE_MINUTE=0
SIGNATURE_MAX_CHARS=30
```

两个开关默认都是 `false`。发说说是对外行为，不该在没授权时自动发生。

---

## 排查

| 日志 | 含义 |
|---|---|
| `qzone 模块已启用（每天 20:00 检查…）` | 正常 |
| `已发说说：xxx` | 成功 |
| `发布qzone失败：xxx` | API 报错，看异常 |
| `这条里提到了私聊里的事` | 隐私过滤拦下了 |
| `今天已经发了 3 条，够了` | 限额 |
| `离上次太近了，还得等 N 分钟` | 冷却 |

查发过的内容：

```powershell
.\.venv\Scripts\python.exe -c "import sqlite3;c=sqlite3.connect('data/qqbot.db');[print(r) for r in c.execute('select kind,status,substr(content,1,50),created_at from social_posts order by id desc limit 10')]"
```

---

## 已知局限

1. **隐私过滤是关键词级的**。换个说法（比如"某个人""那位"）就拦不住。真正的保障是提示词，代码只是兜底。
2. **她可能不发**。工具描述写得克制，她可能好几天不调。兜底只在当天 0 条时触发，所以最低一天 1 条、最高 3 条。
3. **失败不重试**。发说说和聊天不一样，重试可能重复发出去，宁可丢一条。
4. **没有配图**。没有图源，从表情包库拿图发空间很怪。
5. **可见性固定**。改 `QZONE_VISIBILITY` 才能变（1 所有人 / 4 好友 / 64 仅自己）。

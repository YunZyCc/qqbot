# 行为说明：多段回复、主动开口、情绪、表情与图片

## 多段回复

- 模型按 prompt 要求输出 1~3 段，用 `|||` 分隔；
- 太短的段（<10 字）会并进上一段，避免「嗯」单独刷屏；
- 超过 3 段会合并；
- 单段超过 500 字会再按句切分。

## 延迟

```
回复前：random(REPLY_DELAY_DELAY_MIN, REPLY_DELAY_MAX)  默认 0.5 ~ 3 秒
段间隔：random(SEGMENT_INTERVAL_MIN, SEGMENT_INTERVAL_MAX) 默认 1 ~ 2 秒
```

`REPLY_DELAY_ENABLED=false` 可关闭。

## 主动开口

每 `PROACTIVE_CHECK_MINUTES=10` 分钟检查一次：

```
静默时段(0~7点) → 距上次主动≥10分钟
→ 本次随机阈值 random(10,60) 分钟 → 空闲够久？
→ 用户 5 分钟内说过话？→ 概率 0.8 → 生成并发送
```

**不限条数**（`PROACTIVE_DAILY_MAX=0`）。

意图：

| 意图 | 条件 |
|---|---|
| 早安 | 6~9 点 |
| 晚安 | 22~24 点 |
| 想念 | 空闲 ≥ 6 小时 |
| 分享 / 逛到 / 想说话 | 其他情况，三者随机 |

「逛到」是让她说路上看到的小事，「想说话」是没正事也想找你说一句。
三种轮着来，避免每次都走「提上次聊的事」这个套路。

素材：人设 + 当前日程 + 摘要 + 相关事实 + 心情/情绪（**不带日记**）。
因为有日程，「我现在在隔壁城市吃牛肉粉」这类具体句子才写得出来。

主动消息写入 `messages`，`source='proactive'`，下次对话可引用。

## 被晾与赌气

主动消息发出后 30 分钟内，用户的下一条消息决定是否「接住」：

- 「嗯」「然后呢」等短接话 → 接住
- 明着指回（「你刚才说的」）→ 接住
- 与主动消息有共同实词 → 接住
- 聊别的 → 不算

状态机：

| 事件 | 变化 |
|---|---|
| 没被接住 | `ignored_count += 1` |
| 连续 2 次没接 | 堵气 2 小时 |
| 堵气时被接住 | 余味 30 分钟，`ignored_count` 减 1 |
| 正常被接住 | 余味 10 分钟，计数清零 |
| 3 小时没露面 | 情绪淡掉 |

注入 prompt 的只有事实（说了什么、几次没接），是生气还是难受交给模型自己定。

## 表情与表情包

### 识别你发的

- `face` → `[表情:微笑]`（常见 160 个 QQ 表情有名字）
- `mface` → `[表情包:名字]`
- `image` → 视觉模型描述，如 `[图片:一只猫在笑的表情包]`

纯表情/纯图消息也会回复，不会被丢掉。

### 表情包库

```
data/stickers/
  happy/开心.gif
  shy/害羞.png
```

- 子目录名当情绪/分类，文件名当关键词；
- 可选 `index.json` 写更精确的标签和描述；
- 启动时扫描并建立向量索引；
- 工具 `search_stickers(query)` / `send_sticker(query)` 按语义搜索发送；
- 支持 png/jpg/jpeg/gif/webp，单张 ≤2MB。

## 图片理解与多轮追问

- 收到图片：下载 → 缓存到 `data/images/` → 视觉模型生成 1~2 句描述；
- 描述连同 hash 注入 prompt，例如「用户最近发过图片，hash=abc123，描述=…」；
- 你追问「图里右边是什么」「把字念出来」时，模型调用 `look_at_image(hash, question)` 带原图再问一次；
- 视觉模型不可用/超时 → 退回 `[图片]`，不阻塞回复；
- 图片缓存保留 `VISION_CACHE_DAYS=7` 天。

当前视觉模型：本地 Ollama `minicpm-v:8b`（可换 `qwen2.5-vl:7b` 或云端硅基流动）。

## 相关配置

```
REPLY_SEGMENTS_MAX=3
REPLY_DELAY_ENABLED=true
REPLY_DELAY_MIN=0.5
REPLY_DELAY_MAX=3.0
SEGMENT_INTERVAL_MIN=1.0
SEGMENT_INTERVAL_MAX=2.0
PROACTIVE_ENABLED=true
PROACTIVE_CHECK_MINUTES=10
PROACTIVE_DAILY_MAX=5
PROACTIVE_MIN_GAP_MINUTES=90
PROACTIVE_IDLE_MIN=30
PROACTIVE_IDLE_MAX=90
PROACTIVE_QUIET_START=0
PROACTIVE_QUIET_END=7
PROACTIVE_PROBABILITY=0.6
PROACTIVE_MISS_HOURS=6
EMOTION_IGNORED_SULK_AFTER=2
EMOTION_SULK_HOURS=2
EMOTION_RELIEF_MINUTES=30
EMOTION_FADE_HOURS=3
STICKER_ENABLED=true
STICKER_DIR=data/stickers
STICKER_AUTO_RATE=0.15
STICKER_MIN_SCORE=0.6
STICKER_MAX_SIZE_KB=2048
VISION_ENABLED=true
VISION_BASE_URL=http://127.0.0.1:11434/v1
VISION_API_KEY=ollama
VISION_MODEL=minicpm-v:8b
VISION_TIMEOUT=120
VISION_MAX_IMAGE_MB=5
VISION_CACHE_DAYS=7
```

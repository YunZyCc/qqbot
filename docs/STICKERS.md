# 表情包

她在聊天里用的图，来自两个库。

## 两个来源

| 来源 | 数量 | 位置 | 谁来 |
|---|---|---|---|
| **nekowhale 知识库** | **322 张**（66 张带梗注释） | 远程，按需下载缓存 | 主力 |
| **本地库** | 48 张（含自动入库的） | `data/stickers/` | 补充 |

`send_sticker` 先查 nekowhale，查不到再用本地库。

## 检索原理

### 关键词加权（保底）

每张图有一堆标注字段，按区分度给权重：

```
name 6 / tags 5 / emotion 4 / text 4 / meme 3 / use 3 / en 2 / dir 2 / desc 1
```

中文按 bigram 部分匹配，多词查询时按命中率平方衰减（都命中才算好）。

### 向量混合（主力）

`STICKER_VECTOR_SEARCH=true` 时，会给 322 张各算一条 bge-m3 向量，和关键词结果做 RRF 融合：

```
score = (1 - weight) × 关键词排名分 + weight × 向量排名分
```

`STICKER_VECTOR_WEIGHT=0.5` 是实测下来比较平衡的值。

### 为什么需要向量（实测对比）

同一批查询，纯关键词 vs 混合：

| 查询 | 纯关键词 | 混合（weight=0.5） |
|---|---|---|
| 有点尴尬 | 你小子 / 好人 / 打喷嚏 | 你小子 / **害羞** / 好人 |
| 我裂开了 | 碎了 / 超开心 / 猫在么 | 碎了 / 超开心 / **气死偶咧** |
| **好累啊** | **（空，什么都搜不到）** | **难过 / 还不能休息哦 / 趴** |

最后一行是关键：**「好累啊」这种说法，322 张图的标注里根本没有对应字面，关键词完全失效**。向量能捞到语义相近的图。

### 索引存在哪

不常驻内存，落在 `embeddings` 表（`ref_type='sticker_kit'`）：

- 322 条 × 4096 字节 ≈ **1.26 MB**
- 首次建索引约 **3 秒**（批量嵌入，16 条一批）
- 之后只补新增的，不重建
- 搜索时按需加载，毫秒级

## 自动入库

别人发的表情包图片（`sub_type=1`）识别成功后会**自动收进图库**：

```
收到表情包图片
  → vision 描述
  → 存进 data/stickers/auto/<sha256>.<ext>
  → 写 stickers 表 + 向量
```

限制：
- 按 sha256 去重，同一张不会重复入库
- 每天最多 `STICKER_AUTO_IMPORT_DAILY_MAX`（默认 20）张
- 单张不超过 `STICKER_AUTO_IMPORT_MAX_KB`（默认 2048 KB）
- vision 识别失败的不收

这样你们群里发过的图，她以后能拿出来用。

## 配置

```bash
STICKER_ENABLED=true
STICKER_AUTO_RATE=0.2          # 自动补图的概率
STICKER_DAILY_MAX=50           # 每天最多发几张
STICKER_MIN_TURNS_GAP=2        # 两次自动补图至少隔几轮

# 检索
STICKER_VECTOR_SEARCH=true     # 给 322 张建向量索引
STICKER_VECTOR_WEIGHT=0.5      # 向量权重；调到 0 就是纯关键词

# 自动入库
STICKER_AUTO_IMPORT=true
STICKER_AUTO_IMPORT_DAILY_MAX=20
STICKER_AUTO_IMPORT_MAX_KB=2048
```

调参建议：

- 觉得她选图不准 → 把 `STICKER_VECTOR_WEIGHT` 调高（0.7）
- 觉得向量带偏了 → 调低（0.2）或直接关掉
- 不想让图库变脏 → `STICKER_AUTO_IMPORT=false`

## 怎么加自己的图

**方式一：丢文件**

把图片放进 `data/stickers/` 的任意子目录，目录名会当情绪标签用：

```
data/stickers/开心/1.png
data/stickers/无语/2.gif
```

然后在 `data/stickers/index.json` 里可选地写标注：

```json
{
  "开心/1.png": {
    "tags": ["大笑", "开心"],
    "emotion": "开心",
    "description": "一只猫在狂笑"
  }
}
```

重启服务会自动扫描入库并建向量。

**方式二：让她自己收**

发一张表情包给她，识别成功后自动进 `data/stickers/auto/`。

## 排查

| 日志 | 含义 |
|---|---|
| `nekowhale 表情包知识库加载完成：322 张` | 正常 |
| `表情包向量补建完成：N 条（共 322 张）` | 首次建索引，约 3 秒 |
| `表情包向量生成失败` | embedding 服务挂了，退回关键词 |
| `表情包已入库：auto/xxx.png` | 自动收了一张 |
| `表情包下载失败` | nekowhale 远程取图失败，检查网络 |

看索引有没有建好：

```powershell
.\.venv\Scripts\python.exe -c "import sqlite3;c=sqlite3.connect('data/qqbot.db');print(c.execute(\"select ref_type,count(*) from embeddings group by ref_type\").fetchall())"
```

应该看到 `('sticker_kit', 322)`。

## 已知局限

1. **向量有噪声**。实测「无语」会匹配到「黄油」这种奇怪结果。权重调低能缓解。
2. **自动入库的图没有梗注释**。只有 vision 的一句话描述，检索质量不如 nekowhale 那批人工标注的。
3. **GIF 只取第一帧做视觉识别**。动图后面几帧的内容看不到。
4. **自动入库没有人工审核**。收到什么收什么（有去重和限额），图库质量取决于你们发什么。

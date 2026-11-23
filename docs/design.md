# 五笔练习（本地版）详细设计文档

| 项目 | 内容 |
| --- | --- |
| 程序名称 | 五笔练习 · 86 版看图拆字（本地版） |
| 文档版本 | 1.3（v1 基线） |
| 生成日期 | 2026-11-21 |
| 对应代码 | `app.py`、`web/*`、`tools/*` 当前工作区版本 |
| 平台 | Windows 10/11，Python 3.9+（当前使用 conda base 3.9.13），Chrome/Edge 等现代浏览器 |
| 数据位置 | `data/*.json`（构建产物）、`data/progress.db`（SQLite） |
| 文档性质 | 依据现有代码反向整理的详细设计说明，描述“实际怎么实现”，不是需求提案 |

> **v2 变更说明（2026-11-21）**：学习状态与出题策略已升级为按科目记录
> `new / low / error / mastered`，按 45% / 45% / 10% 分桶出题，新增
> `item_state`、`/api/learning`、`/api/attempt`、`/api/learning/reset`。本文档的
> 3.8、4.3、4.5、5.5、5.10、6.4、9 等章节描述的是 v1 行为，v2 的准确设计以
> [`learning-state-design.md`](learning-state-design.md) 为准。
>
> **v3 文章练习说明（2026-11-21）**：新增“文章练习”页面、`article_parser.py`、
> `articles / article_progress / article_chars` 表、文章导入/进度/成绩接口；支持
> txt/docx 结构级排版、五笔码逐字输入与灰/黑/红状态（支持单字与词库中 2–4 字词组）。准确设计见
> [`article-practice-design.md`](article-practice-design.md)；本文档其余章节仍是
> v1 基线与 v2 学习状态的架构说明。

**阅读指引**：想快速了解结构看第 2 章；关心数据与字库看第 3 章；对接接口看第 4 章；
修改练习逻辑看第 5 章与第 6 章；部署、测试、扩展分别见第 9–11 章。

---

## 1 概述

### 1.1 背景与目标

本项目是一个完全本地运行的五笔（86 版）打字练习网页工具，交互结构参考「巧手打字通」的看图拆字页面：屏幕上给出一个汉字或词组，用户凭记忆输入五笔编码，程序即时判定对错、统计速度与正确率，并把练习记录保存在本机。

设计目标：

1. **零外部依赖**：服务端只用 Python 标准库，前端不用框架、不用 CDN，断网可用。
2. **真正练拆字**：默认不显示编码提示，答错一次后才允许按空格查看该码的键位与字根口诀，避免“照着提示敲”。
3. **本地数据**：练习记录写入本地 SQLite，不上传、不登录、不联网。
4. **快速启动**：双击 `run.bat` 或执行 `python app.py`，浏览器自动打开。
5. **数据可重建**：编码来自公开码表，`tools/build_data.py` 可随时重新生成字库与词库。

### 1.2 范围

包含：

- 看图拆字（单字）练习：一级/二级/三级简码、全码字、常用字、通用字、键名字、成字字根、难拆字、错字本。
- 词组练习：二字词、三字词、四字词。
- 字根口诀页：25 键字根表、键位详情、口诀→键位反应练习、末笔识别码规则说明。
- 编码查询：汉字/词语查编码，字母反查同码字词。
- 练习统计：累计字数、正确率、最快速度、今日字数、连续天数、最近练习、错字本。
- 设置：每轮字数、简码/全码、初学模式（始终显示提示）、按键音效。
- 快捷键：空格看提示（需先答错）、Esc 重新开始本轮。

不包含：

- 98 版五笔、拼音/双拼等其他输入方案。
- 识别码专项题库（只有规则讲解）。
- 账号、云同步、排行榜、比赛。
- 移动端软键盘输入。

### 1.3 术语

| 术语 | 含义 |
| --- | --- |
| 简码 | 五笔中不足四码即可上屏的编码，本程序取码表中该字的最短编码 |
| 全码 | 该字在码表中的最长编码，通常为 4 码 |
| 键名字 | 25 个键位各自的代表字（王土大木工…） |
| 成字字根 | 本身是汉字、又能作为字根的字 |
| 码长 | 一个编码包含的字母数（1–4） |
| 字库（pool） | 一组用于出题的单字或词组 |
| 一轮（round） | 连续练习 `perRound` 个字/词，结束后结算并入库 |
| 错字本 | 练习中打错、跳过或使用提示的字，按错误次数排序 |

---

## 2 总体设计

### 2.1 架构

```text
┌────────────────────────── 浏览器（http://127.0.0.1:8765） ──────────────────────────┐
│  index.html + style.css + app.js（单页应用，无框架）                                  │
│    ├─ hash 路由：#/five  #/roots  #/words  #/dict  #/stats                          │
│    ├─ Trainer ×2：单字练习、词组练习（同一套引擎）                                     │
│    ├─ 字根页 / 编码查询 / 统计页                                                      │
│    ├─ 键盘组件（25 键，五区配色、高亮、闪烁）                                          │
│    └─ localStorage：每轮字数、编码模式、初学模式、音效                                  │
└───────────┬───────────────────────────────────────────────┬─────────────────────────┘
            │ fetch 静态 JSON（只读，带版本无关的 no-store）      │ fetch /api/*（读写）
            ▼                                               ▼
┌───────────────────────────────┐               ┌──────────────────────────────────────┐
│ data/keys86.json              │               │ app.py：Python 标准库 HTTP 服务        │
│ data/chars.json               │               │  ThreadingHTTPServer，绑定 127.0.0.1   │
│ data/words.json               │               │  静态文件 + 4 个 JSON 接口             │
│ data/pools.json               │               └───────────────┬──────────────────────┘
└───────────────▲───────────────┘                               │ sqlite3
                │ 由构建脚本生成                                  ▼
┌───────────────┴───────────────┐               ┌──────────────────────────────────────┐
│ tools/build_data.py           │               │ data/progress.db                      │
│ _ref/wubi86.dict.yaml（码表）  │               │  sessions / err_chars                 │
└───────────────────────────────┘               └──────────────────────────────────────┘
```

### 2.2 运行形态

- 单进程、单用户、仅监听回环地址 `127.0.0.1`。
- 服务端不是 MVC 框架，而是“静态文件服务器 + 少量 JSON 接口”。
- 前端是纯静态资源，所有练习逻辑（出题、判定、提示、计时、统计展示）都在浏览器内完成。
- 码表数据在启动时一次性下载到浏览器内存，之后练习过程不再请求码表。
- 只有“一轮结束”时才向服务端写一次记录；离线或服务端异常时仍可继续练习，只是不落库。

### 2.3 技术选型

| 选择 | 原因 | 代价 |
| --- | --- | --- |
| Python 标准库 `http.server` | 零安装、双击即用，符合“conda base 直接跑”的要求 | 无路由框架、无 gzip、无并发压测优化 |
| SQLite | 单文件、零配置、事务可靠，便于本地统计 | 无多用户/远程访问 |
| 原生 JavaScript（IIFE + class） | 代码量小、无构建步骤、调试直接 | 无组件化与响应式框架能力 |
| 静态 JSON 码表 | 前端可离线随机出题，延迟低 | 首屏需解析约 3.5 MB JSON；改数据要重新构建 |
| CSS 变量 + 原生 CSS | 主题统一、五区配色集中管理 | 无预处理器 |
| localStorage | 偏好设置简单持久 | 按 origin 隔离，换端口会丢偏好 |

### 2.4 目录结构

```text
五笔练习/
├─ app.py                 # 本地 HTTP 服务（静态文件 + JSON API + SQLite）
├─ run.bat                # Windows 一键启动（ASCII + CRLF）
├─ README.md              # 用户说明
├─ docs/
│  ├─ design.md           # 本文档
│  └─ preview.png         # 界面截图
├─ web/
│  ├─ index.html          # 页面骨架、五个视图容器、设置面板、弹层
│  ├─ style.css           # 设计令牌、布局、组件、响应式、动效
│  └─ app.js              # 全部前端逻辑（约 1070 行）
├─ data/
│  ├─ keys86.json         # 25 键：字根、口诀、分区、指法
│  ├─ chars.json          # 70781 个单字 → 简码/全码
│  ├─ words.json          # 60897 个词组 → 编码
│  ├─ pools.json          # 13 个字库（单字 10 + 词组 3）
│  └─ progress.db         # SQLite，首次启动自动创建
├─ tools/
│  ├─ build_data.py       # 码表 → data/*.json
│  ├─ e2e_test.py         # CDP 端到端冒烟测试（开发用）
│  └─ test_error_review.py# 错字本连对/移出接口测试（临时库）
└─ _ref/
   └─ wubi86.dict.yaml    # Rime 五笔86 原始码表（构建输入）
```

---

## 3 数据设计

### 3.1 数据源

- 编码与字频：Rime 五笔86 码表 `_ref/wubi86.dict.yaml`，由极点五笔码表转换，含 Google 字频。
- 字根表与口诀：86 版传统字根口诀，硬编码在 `tools/build_data.py` 的 `KEYS` 常量中（25 项）。
- 一级简码：硬编码 `JM1` 25 字；难拆字：硬编码 `HARD` 列表，构建时与码表求交集。
- 词组：来自码表的词组条目，构建时按 GB2312 与字频过滤。

### 3.2 构建管线

```text
_ref/wubi86.dict.yaml
        │ parse_dict()
        ▼
 单字集合 {(code, weight)}          词组映射 {word: (code, weight)}
        │                                   │
        │ 最短码=练习码，最长码=全码          │ 2–4 字、GB2312、码长≥3
        ▼                                   ▼
 chars.json（s/f）                  words.json（全部词）
        │                                   │
        │ 规则筛选                           │ 按字频取前 N
        ▼                                   ▼
 pools.json（单字库 + w2/w3/w4）      （词库并入 pools）
        │
        ▼
 keys86.json（KEYS 常量直出）
```

运行方式：

```powershell
C:\ProgramData\Anaconda3\python.exe tools\build_data.py
```

脚本会打印每个文件的体积与各字库数量，并做两项自检：一级简码是否都是 1 码、码表是否缺少一级简码字。

### 3.3 码表解析与编码归并

`parse_dict()` 的做法：

1. 找到 YAML 头部结束标记 `...`，其后按行解析。
2. 跳过空行与 `#` 注释行；按 `\t` 切分，至少 3 列（`text`、`code`、`weight`）。
3. 编码必须匹配 `^[a-z]{1,4}$`，统一转小写。
4. 单字：同一字可能有多条码（全码与各级简码），用 `set` 收集 `(code, weight)`。
5. 词组：同一词保留权重最高的一条。

单字归并规则：

```python
codes = sorted({code for code, _ in pairs}, key=len)
short = min(codes, key=len)   # 练习码（简码优先）
full  = max(codes, key=len)   # 展示用全码
```

示例：

| 字 | 码表中的码 | short | full | 说明 |
| --- | --- | --- | --- | --- |
| 的 | `r` / `rqy` / `rqyy` | `r` | `rqyy` | 一级简码 |
| 工 | `a` / `aa` / `aaa` / `aaaa` | `a` | `aaaa` | 键名字，全码 4 码 |
| 了 | `b` / `bn` / `bnh` | `b` | `bnh` | 全码 3 码 |
| 编 | `xyna` | `xyna` | `xyna` | 只有全码 |

注意：

- `chars.json` 只下发 `s`（short）与 `f`（full），**不下发字频**；字频只在构建期用于排序。
- `short` 不一定是“官方一级简码”，而是码表中该字出现的最短码；例如二级简码字的 `short` 为 2 码。
- 全码模式使用 `f`，因此键名字会要求 4 码（如「工」= `AAAA`）。

### 3.4 单字库

构建规则（`pools.json`）：

| 字库 id | 名称 | 规则 | 数量 |
| --- | --- | --- | --- |
| `jm1` | 一级简码 | 硬编码 25 字 ∩ 码表 | 25 |
| `jm2` | 二级简码 | `short` 长度 = 2 且 GB2312 可编码 | 604 |
| `jm3` | 三级简码 | `short` 长度 = 3 且 GB2312 可编码 | 3864 |
| `jm4` | 全码字 | `short` 长度 = 4 且 GB2312 可编码 | 2780 |
| `common` | 常用字 | GB2312 字按字频降序取前 1000 | 1000 |
| `common2` | 扩展常用 | 同上取前 2500 | 2500 |
| `gb2312` | 通用字 | 全部 GB2312 可编码字 | 6763 |
| `keyname` | 键名字 | 25 键名中存在于码表的字 | 25 |
| `chengzi` | 成字字根 | 字根表中单字字根，排除键名字 | 121 |
| `hard` | 难拆字 | 硬编码难拆字列表 ∩ 码表 | 64 |

GB2312 判定使用 Python `gb2312` 编解码器；`gb2312` 字库额外要求首字节 ≥ `0xB0`，因此是 6763 个汉字（不含符号）。

> 界面上的「错字本」不写入 `pools.json`，而是由 `/api/errors` 动态提供，属于第 11 个字库。

### 3.5 词库

过滤条件（`word_data`）：

1. 词长 2–4；
2. 编码长度 ≥ 3；
3. 词中每个字都能用 GB2312 编码；
4. 同词多条记录取权重最高者。

`words.json` 保存全部符合条件的 60897 个词（用于编码查询）；练习用的三个词库另存于 `pools.json`：

| 词库 id | 名称 | 规则 | 数量 |
| --- | --- | --- | --- |
| `w2` | 二字词 | 按字频取前 12000 | 12000 |
| `w3` | 三字词 | 按字频取前 10000（实际 4519） | 4519 |
| `w4` | 四字词 | 按字频取前 6000 | 6000 |

### 3.6 输出文件格式

`data/keys86.json`（数组，25 项）：

```json
[
  {
    "key": "G",
    "zone": 1,
    "zoneName": "横区",
    "name": "王",
    "roots": ["王", "龶", "一", "五", "戋"],
    "rhyme": "王旁青头戋（兼）五一",
    "finger": "左食指"
  }
]
```

`data/chars.json`：

```json
{ "chars": { "的": { "s": "r", "f": "rqyy" }, "工": { "s": "a", "f": "aaaa" } } }
```

`data/words.json`：

```json
{ "words": { "中国": "khlg", "五笔": "ggtt", "练习": "xanu" } }
```

`data/pools.json`：

```json
{
  "jm1": ["我", "人", "有"],
  "common": ["的", "一", "是"],
  "w2": ["中国", "我们"],
  "w3": ["大多数", "计算机"],
  "w4": ["社会主义", "高速公路"]
}
```

### 3.7 数据规模

| 文件 | 条目数 | 体积（约） |
| --- | --- | --- |
| `keys86.json` | 25 | 3.9 KB |
| `chars.json` | 70781 | 2.15 MB |
| `words.json` | 60897 | 1.04 MB |
| `pools.json` | 13 个数组 | 359 KB |
| 合计 | — | 约 3.4 MB（356 万字节） |

### 3.8 持久化数据库

文件：`data/progress.db`，启动时由 `init_db()` 创建；连接参数：`timeout=5`、`PRAGMA busy_timeout=3000`、`PRAGMA journal_mode=WAL`。

```sql
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,            -- 本地时间 "YYYY-MM-DD HH:MM:SS"
    mode TEXT NOT NULL,          -- 'char' | 'word'
    pool TEXT NOT NULL,          -- 字库 id，如 common / jm2 / errors
    total INTEGER NOT NULL,      -- 本轮完成的字/词数
    correct INTEGER NOT NULL,    -- 本轮正确按键数（不是字数）
    wrong INTEGER NOT NULL,      -- 本轮错误按键数
    duration REAL NOT NULL,      -- 用时（秒）
    speed REAL NOT NULL          -- total / (duration/60)，服务端计算
);

CREATE TABLE IF NOT EXISTS err_chars (
    char TEXT PRIMARY KEY,       -- 出错的字
    count INTEGER NOT NULL DEFAULT 0,
    last_ts TEXT,
    right_streak INTEGER NOT NULL DEFAULT 0  -- 专项练习连续全对次数，满 3 次移出
);
```

写入规则：

- 每轮结束 POST 一次，插入一条 `sessions`。
- 本轮 `errors` 集合（Set 去重）中的每个字，在 `err_chars` 中 `count + 1`，更新 `last_ts`，并把 `right_streak` 清零。
- 使用 `INSERT ... ON CONFLICT(char) DO UPDATE` 实现 upsert。
- 错字本专项练习中，每个字完成时单独调用 `/api/error-review`：
  - 全对（无错键、无提示、未开初学模式）→ `right_streak + 1`；
  - 满 3 → 删除该行，字移出错字本；
  - 错键/提示/跳过 → `right_streak = 0`。
- 旧库启动时自动迁移：若 `err_chars` 缺少 `right_streak`，执行 `ALTER TABLE ... ADD COLUMN`，原有记录保留、默认 0。

统计语义：

- `total` 是本轮完成的字数/词数；`correct`/`wrong` 是**按键级**计数，因此一次 20 字的练习可能 `correct=57`。
- 速度 = `total / (duration / 60)`，单位“字/分”或“词/分”（展示层区分，数据库中统一存数值）。
- 总正确率 = `Σcorrect / (Σcorrect + Σwrong)`，同样是按键级。

### 3.9 数据一致性

- 码表 JSON 是只读构建产物，运行时不修改；数据库与码表互不依赖。
- 前端出错（如服务端不可用）不会破坏练习，只会跳过入库。
- 删除 `progress.db` 即清空统计；下一次启动会重建空库。
- 内置一处轻量迁移（为旧库补 `err_chars.right_streak`），其余表结构变更仍需手工处理或删库重建。

---

## 4 服务端设计

### 4.1 模块结构（`app.py`）

| 区域 | 内容 |
| --- | --- |
| 常量 | `BASE/WEB/DATA/DB_PATH`、`MIME` 映射 |
| 数据库 | `connect()`、`init_db()`、`local_now()`、`stats_payload()` |
| HTTP 处理 | `Handler`：`send_json`、`send_file`、`resolve`、`safe_join`、`read_payload`、`do_GET`、`do_POST`、`handle_error_review` |
| 启动 | `pick_port()`、`main()` |

### 4.2 启动流程

```text
python app.py [--port 8765] [--no-open]
  ├─ 检查 web/index.html 存在
  ├─ 检查 data/chars.json 存在（缺则提示先跑 build_data.py）
  ├─ init_db()：建目录、建表、开 WAL
  ├─ pick_port()：从 8765 起最多尝试 20 个端口
  ├─ ThreadingHTTPServer(("127.0.0.1", port))
  ├─ 打印地址与数据库路径
  └─ 0.6 秒后 webbrowser.open()（--no-open 时跳过）
```

端口选择：在 `preferred .. preferred+19` 范围内逐个尝试绑定，成功即用；全部占用则退出并提示换端口。

### 4.3 路由表

| 方法 | 路径 | 作用 | 响应 |
| --- | --- | --- | --- |
| GET | `/`、`/index.html` | 主页面 | `web/index.html` |
| GET | `/static/*` | 前端静态资源 | 对应文件 |
| GET | `/data/*` | 码表 JSON | 对应文件 |
| GET | `/api/health` | 健康检查 | `{"ok": true}` |
| GET | `/api/stats` | 统计汇总 | 见 4.5 |
| GET | `/api/errors` | 全部错字（含连对次数） | `{"errors":[...]}` |
| POST | `/api/session` | 上报一轮练习 | 见 4.5 |
| POST | `/api/error-review` | 错字专项单字判定（全对/失败） | 见 4.5 |
| 其他 | 任意 | — | 404 JSON |

静态文件响应头统一 `Cache-Control: no-store`，保证改动后刷新立即生效；`Content-Type` 先查 `MIME` 表，再退回 `mimetypes.guess_type`。

### 4.4 静态文件与路径安全

`resolve(url_path)` 只接受三类路径：

1. 根路径 → `web/index.html`；
2. `/static/<rel>` → `WEB/<rel>`；
3. `/data/<rel>` → `DATA/<rel>`。

`safe_join(root, rel)` 将路径 `abspath` 归一化后，用 `os.path.commonpath([root_abs, target]) == root_abs` 校验，阻止 `../` 越权读取；不匹配返回 `None`，最终以 404 结束。

### 4.5 API 契约

#### GET `/api/stats`

响应：

```json
{
  "sessions": 12,
  "totalChars": 600,
  "totalCorrect": 1720,
  "totalWrong": 96,
  "accuracy": 94.72,
  "bestSpeed": 61.3,
  "todayChars": 150,
  "streak": 4,
  "recent": [
    { "ts": "2026-11-20 19:03:12", "mode": "char", "pool": "jm1",
      "total": 50, "correct": 133, "wrong": 2, "duration": 65.0, "speed": 46.15 }
  ],
  "errors": [ { "char": "不", "count": 3, "streak": 0 } ]
}
```

| 字段 | 说明 |
| --- | --- |
| `sessions` | 总记录条数 |
| `totalChars` | 累计练习字数/词数 |
| `totalCorrect` / `totalWrong` | 累计正确/错误按键数 |
| `accuracy` | 按键级正确率，保留 2 位 |
| `bestSpeed` | 历史最快速度 |
| `todayChars` | 今日练习量（按本地日期比较） |
| `streak` | 连续练习天数 |
| `recent` | 最近 12 条，按 id 倒序 |
| `errors` | 错字 Top 40（按 count 降序、last_ts 降序），含 `streak` |

连续天数算法：

1. 取 `sessions` 中不同日期的降序列表（最多 400 天）。
2. 若最新日期是今天或昨天，`streak = 1`，否则为 0。
3. 从最新日期往前逐日比较，连续则 +1，遇到断档停止。
4. 允许“昨天练过、今天还没练”仍保持连续。

#### GET `/api/errors`

```json
{ "errors": [
  { "char": "折", "count": 2, "streak": 1 },
  { "char": "病", "count": 2, "streak": 0 }
] }
```

返回全部错字（不截断），按 count 降序、last_ts 降序；`streak` 是专项练习中的连续全对次数（0–2）。
前端启动时加载，用于“错字本”字库和统计页。

#### POST `/api/error-review`

错字本专项练习的单字判定。前端在“错字本”字库中每完成一个字调用一次；答错、用提示、跳过时也会调用失败判定。

请求：

```json
{ "char": "龘", "ok": true }
```

| 字段 | 规则 |
| --- | --- |
| `char` | 非空字符串，最多取前 4 个字符 |
| `ok` | `true` = 本次全对；`false` = 错键/提示/跳过 |

处理：

- `ok=true` 且字仍在错字本：`right_streak + 1`；达到 3 时删除该行并返回 `removed=true`；
- `ok=true` 但字已不在错字本：不新增记录，`streak=0`；
- `ok=false`：`right_streak=0`，不增加错误次数（错误次数统一由 `/api/session` 记录）；
- 每次返回错字本剩余数量。

响应：

```json
{ "ok": true, "char": "龘", "streak": 3, "removed": true, "remaining": 29 }
```

| 字段 | 说明 |
| --- | --- |
| `streak` | 本次判定后的连对次数；移除时为 3 |
| `removed` | 是否已移出错字本 |
| `remaining` | 错字本剩余数量 |

规则：连对只在“错字本”专项练习中累计；初学模式（始终显示提示）下不计，避免照着提示把错字本清空。

#### POST `/api/session`

请求：

```json
{
  "mode": "char",
  "pool": "common",
  "total": 50,
  "correct": 133,
  "wrong": 14,
  "duration": 205,
  "errors": ["的", "是"]
}
```

校验与归一化（服务端强制）：

| 字段 | 规则 |
| --- | --- |
| `mode` | 必须是 `char` 或 `word` |
| `total` | 0–5000 |
| `correct` / `wrong` | 0–100000 |
| `duration` | 1–86400 秒 |
| `pool` | 字符串，截断到 32 字符 |
| `errors` | 数组，最多 200 项，每项转字符串截断到 4 字符 |
| 请求体 | `Content-Length` 必须在 1–200000 字节之间，JSON 解析失败返回 400 |

响应：

```json
{
  "ok": true,
  "todayChars": 150,
  "accuracy": 94.72,
  "stats": { "...": "同 /api/stats" }
}
```

### 4.6 统计聚合

`stats_payload()` 在每次 `/api/stats` 和每次成功写入后调用，实时聚合：

- 总量：`COUNT(*)`、`SUM(total)`、`SUM(correct)`、`SUM(wrong)`、`MAX(speed)`。
- 今日：`substr(ts,1,10) = 本地日期`。
- 最近：`ORDER BY id DESC LIMIT 12`。
- 错字：`ORDER BY count DESC, last_ts DESC LIMIT 40`，同时带出 `right_streak AS streak`。

数据量在个人使用规模（数千条 session）下无需索引；表很小，全表扫描足够。

### 4.7 并发与连接管理

- `ThreadingHTTPServer` 每请求一个线程。
- 每次请求新建 SQLite 连接，`with closing(connect()) as conn, conn:` 保证用完即关、事务提交。
- `busy_timeout=3000` 与 WAL 降低并发写锁冲突；个人单用户场景下基本不会触发。
- 写接口都是单事务内的少量语句（insert session、循环 upsert errors、error-review 的读改删），无长事务。

### 4.8 错误处理

| 场景 | 行为 |
| --- | --- |
| 路径不存在或越权 | 404 JSON |
| 文件读取失败 | 500 JSON |
| 请求体过大/过小/非 JSON | 400 JSON |
| mode 非法 | 400 JSON |
| 内部异常 | 由 `BaseHTTPRequestHandler` 默认处理，连接中断；前端对失败静默 |
| 启动缺少数据文件 | `SystemExit` + 中文提示 |
| 端口全占用 | `SystemExit` + 提示换端口 |

日志默认关闭；设置环境变量 `WUBI_VERBOSE=1` 后输出访问日志。

---

## 5 前端设计

### 5.1 页面与视图

单页应用，五个视图容器（`<section class="view" id="view-*">`）：

| 视图 | hash | 内容 |
| --- | --- | --- |
| 看图拆字 | `#/five` | 字库切换、练习台、键位图、四项指标 |
| 字根口诀 | `#/roots` | 25 键字根表、键位详情、键位反应练习、识别码说明 |
| 词组练习 | `#/words` | 与单字同一套练习台，出题源为词库 |
| 编码查询 | `#/dict` | 搜索框、快捷词、结果列表；支持 `#/dict?q=的` |
| 练习统计 | `#/stats` | 五张统计卡、最近练习、错字本 |

视图切换只切 `.active` 类并播放 0.28s 淡入动画；不销毁 DOM，训练进度保留。

### 5.2 前端模块结构（`web/app.js`）

文件是一个立即执行函数 `(() => { ... })()`，内部按职责分区：

| 区域 | 主要内容 |
| --- | --- |
| 工具函数 | `$`、`$$`、`clamp`、`fmt`、`toast`、`beep` |
| 全局数据 | `DATA`（keys/chars/words/pools/集合）、`state`（视图、偏好、词库数组） |
| 数据加载 | `fetchJSON`、`loadData` |
| 键盘 | `keyInfo`、`renderKeyboard`、`setActiveKey`、`flashKey` |
| 练习引擎 | `CHAR_POOLS`、`WORD_POOLS`、`shuffle`、`class Trainer` |
| 结算 | `showSummary`、`updateTodayChip` |
| 字根页 | `const roots = { ... }` |
| 字典 | `codeKeyChain`、`charTags`、`dictRowChar`、`dictRowWord`、`renderDict`、`mountDict` |
| 统计 | `renderStats` |
| 设置/路由 | `applySettingsUI`、`mountSettings`、`route` |
| 启动 | `trainers`、`boot` |

### 5.3 启动时序

```text
DOMContentLoaded
  └─ boot()
       ├─ loadPrefs()                       # localStorage wubi.prefs.v2
       ├─ 插入“正在载入五笔码表…”占位
       ├─ loadData()
       │    ├─ Promise.all([keys86, pools, chars, words, /api/errors])
       │    ├─ 构建 keyByLetter / Set（jm1、keyname、chengzi）
       │    ├─ state.errorChars、state.words2/3/4
       │    └─ GET /api/stats（失败则 null）
       ├─ 移除占位
       ├─ new Trainer(#view-five, 'char')   # 立即开一轮
       ├─ new Trainer(#view-words, 'word')  # 立即开一轮（隐藏）
       ├─ roots.mount() / mountDict() / mountSettings()
       ├─ 注册全局 Esc 处理器
       ├─ updateTodayChip()
       ├─ hashchange → route()
       └─ route() 首次渲染
```

失败处理：任一码表请求失败时，占位文字变为“码表载入失败：…（请确认通过 python app.py 启动）”，不再初始化练习。

### 5.4 全局状态

`state` 字段：

| 字段 | 默认 | 说明 |
| --- | --- | --- |
| `view` | `five` | 当前视图 |
| `pool` | `common` | 单字当前字库 |
| `wordPool` | `w2` | 词组当前字库 |
| `perRound` | `50` | 每轮字数（20/50/100） |
| `mode` | `short` | `short` 简码优先 / `full` 全码 |
| `autoHint` | `false` | 初学模式：始终显示提示 |
| `sound` | `true` | 按键音效 |
| `words2/3/4` | `[]` | 由 pools.w2/w3/w4 填充 |
| `errorChars` | `[]` | 错字本字符数组 |
| `stats` | `null` | 最近一次统计响应 |
| `modalOpen` | `false` | 结算弹层是否打开（拦截练习按键） |

`DATA` 字段：`keys`、`keyByLetter`、`pools`、`chars`、`words`、`jm1/keyname/chengzi` 三个 Set。

### 5.5 练习引擎 `Trainer`

#### 5.5.1 实例字段

| 字段 | 含义 |
| --- | --- |
| `kind` | `char` / `word` |
| `poolId` | 当前字库 id（含 `errors`） |
| `bag` | 洗好的待出题队列；取空后再洗一轮 |
| `item` | 当前题目 `{text, code, short, full, kind}` |
| `pos` | 当前输入到第几码（0 起） |
| `done` | 本轮已完成题数 |
| `correct` / `wrong` | 本轮正确/错误按键数 |
| `streak` / `bestStreak` | 当前/最高连击（按键级） |
| `errors` | 本轮出错题目的 Set |
| `startedAt` | 第一次按键时间戳（null 表示未开始） |
| `timer` | 500ms 指标刷新定时器 |
| `locked` | 完成动画/结算期间锁定输入 |
| `charError` | 当前题是否答错过 |
| `hintShown` | 当前题是否显示提示（含初学模式） |
| `hintUsed` | 当前题是否主动用空格/按钮看过提示（用于判定“全对”） |
| `reviewSent` | 当前题是否已向错字本接口上报过判定 |
| `advanceTimer` | 完成后 500ms 自动换题的定时器 |

#### 5.5.2 题目对象与取码

```js
// 单字
{ text: '的', code: 'r', short: 'r', full: 'rqyy', kind: 'char' }
// 词组
{ text: '中国', code: 'khlg', short: 'khlg', full: 'khlg', kind: 'word' }
```

取码规则：

- `mode === 'short'` → `chars[ch].s`（最短码）；
- `mode === 'full'` → `chars[ch].f`（最长码）；
- 词组的编码固定取自 `words.json`，不受模式影响。

#### 5.5.3 出题算法

1. 点击字库或开始新一轮时，复制该字库数组并用 Fisher–Yates 洗牌，存入 `bag`。
2. 每次 `drawItem()` 从 `bag` 尾部 `pop`，保证一轮内不重复（除非字库小于每轮字数）。
3. `bag` 为空时重新洗牌同字库，允许跨轮重复。
4. 错字本 `errors` 是动态数组：开局时复制 `state.errorChars`，本轮内不加入新错字；若某字连对 3 次被移出，会同时从 `bag` 与 `state.errorChars` 中删除，本轮不再出现。

#### 5.5.4 单题状态机

```text
             nextItem()
┌──────────┐ ─────────► ┌────────────┐  正确键且未满  ┌────────────┐
│ 无当前题  │             │ 输入中(隐藏) │ ─────────────► │ 输入中(隐藏) │
└──────────┘             └─────┬──────┘                └────────────┘
                               │ 错误键
                               ▼
                         ┌────────────┐  空格 / 按钮   ┌────────────┐
                         │ 已答错待提示 │ ────────────► │ 提示显示中  │
                         └────────────┘                └─────┬──────┘
                               ▲                              │ 正确键
                               └──────────────────────────────┘
                                  （同一题内一直显示提示）
   任意输入态 ──Esc──► startRound()（整轮重置）
   最后一码正确 ──500ms──► nextItem() 或 endRound()
```

说明：

- “隐藏”指不显示下一码的字母、键名、口诀，也不高亮键盘。
- 提示一旦通过空格显示，本题后续各码保持显示（`hintShown` 持续为 true），直到换题。
- 提示**只显示，不代填**：对应槽位仍需用户自己按。

#### 5.5.5 输入判定

```text
onKey(e)
 ├─ 视图不匹配 / 弹层打开 / 带 Ctrl·Alt·Meta → 忽略
 ├─ Space → requestHint()
 ├─ 非 a–z → 忽略
 └─ 字母 → input(lowercase)
```

`input(letter)`：

- 若 `locked` 或无题 → 忽略。
- 第一次按键时记录 `startedAt`。
- 正确：`correct++`、`streak++`、`bestStreak` 更新、`pos++`；满码则 `complete()`，否则重绘槽位与提示。
- 错误：`wrong++`、`streak=0`、`errors.add(text)`、`charError=true`、按下的键闪红、提示区转红并提示“按空格查看提示”，**不推进 `pos`，不显示正确键**；若当前是错字本字库，同时调用 `reviewFail()` 把该字的连对次数清零。

#### 5.5.6 提示子系统

| 条件 | 提示区 | 键盘高亮 | “看提示”按钮 |
| --- | --- | --- | --- |
| 新题，`autoHint=false` | `第 N 码 · 输入五笔编码` | 无 | 禁用 |
| 答错后 | `第 N 码 · 按 空格 查看提示`（红色） | 无 | 启用 |
| 按空格/按钮后 | `第 N 码 · 按 X 名键 —— 口诀` | X 键 | 禁用 |
| `autoHint=true` | 始终显示键位与口诀 | 始终高亮 | 禁用 |
| 完成 | `✓ 完成 · CODE（全码 …）` | 无 | 禁用 |

规则：

- `hintVisible() = state.autoHint || hintShown`。
- `requestHint()` 必须满足 `charError && !hintShown && !locked`；否则：
  - 未答错：toast「先自己拆。答错一次后，按空格就能看到这一码的提示」；
  - 已显示/已锁定：静默返回。
- 主动看提示会置 `hintUsed=true`，并在错字本字库中调用 `reviewFail()`（看过提示不算全对）。
- 换题时 `charError=false`、`hintShown=state.autoHint`、`hintUsed=false`、`reviewSent=false`，即初学模式以外一律重新隐藏。

#### 5.5.7 完成、推进与结算

`complete()`：

1. `locked=true`、`done++`，槽位全部标绿，字卡加 `ok` 动画。
2. 生成标签：
   - 单字：一级简码 / N 级简码 / 键名字 / 成字字根 / `全码 XXXX`（当 short ≠ full）。
   - 词组：`编码 XXXX` + 取码规则（二字词各取前两码；三字词前两字首码 + 末字前两码；四字词各取首码）。
3. 提示区显示完成编码；进度条与计数更新。
4. **错字本判定**：仅当字库为 `errors`、未开初学模式、且 `charError/hintUsed` 均为 false 时，调用 `reportReview(true)`；否则不增加连对。接口返回：
   - `streak < 3`：在结果区追加“连对 N/3”标签；
   - `removed`：从 `state.errorChars` 与当前 `bag` 中删除该字，重绘字库 chip，toast「「X」连续 3 次全对，已移出错字本」。
5. `advanceTimer = setTimeout(500ms)`：未满一轮则 `nextItem()`，满一轮则 `endRound()`。

`endRound()`：

- 停掉指标定时器、清除键盘高亮。
- 组装 payload（`mode/pool/total/correct/wrong/duration/errors`），弹出结算层。
- 异步 POST `/api/session`；成功后更新“今日”胶囊、刷新错字本与字号库 chip。

#### 5.5.8 指标计算

| 指标 | 公式 | 说明 |
| --- | --- | --- |
| 速度 | `done / (elapsed/60)` | `elapsed > 1s` 才计算，否则 0；单位字/分或词/分 |
| 正确率 | `correct / (correct + wrong)` | 按键级；无按键时为 100% |
| 连击 | 连续正确按键数 | 错误清零；`bestStreak` 记录本轮最高 |
| 用时 | `now - startedAt` | 从第一次按键开始，不含读题时间 |

`tick()` 每 500ms 刷新一次指标，但当前视图不是对应练习页时直接返回，避免隐藏视图的 DOM 重绘。

### 5.6 键盘组件

- `renderKeyboard(container, {full, clickable})` 生成三行：`QWERTYUIOP`、`ASDFGHJKL`、`ZXCVBNM`。
- 每个键是 `<button type="button" class="key zone-N">`，含字母、键名字、可选字根列表。
- 五区以 `border-bottom` 色条区分；选中/高亮时整键反色。
- `setActiveKey` 清除旧高亮并高亮指定键；`flashKey` 加 260ms 的 `hit`/`wrong` 动画。
- 布局用 flex：`flex:1 1 0; max-width`，随卡片宽度自动收缩，字根页窄栏内也不会溢出。

### 5.7 结算弹层

- 遮罩 `#modalMask` + 卡片 `#modalCard`，`hidden` 控制显隐。
- 内容：SVG 圆环正确率、速度、用时、错误次数、两个按钮「再来一轮」「查看统计」。
- 关闭方式：按钮、点遮罩、Esc。
- 关闭后**一律开始新一轮**（`onAgain()`），避免停在已锁定的最后一字；点「查看统计」会先开新轮再跳转。
- 弹层打开时 `state.modalOpen=true`，练习按键全部被拦截；Esc 由弹层自己的监听器处理，全局 Esc 处理器看到 `modalOpen` 直接返回，不会重复触发。

### 5.8 字根页与键位练习

- 字根表用同一个 `renderKeyboard(full=true, clickable=true)`；点击键调用 `roots.select(letter)`，右侧详情显示键名、分区、指法、口诀、字根 chips。
- 键位反应练习：
  1. 点「开始练习」→ 状态 `drill=true`，显示题目区，随机取一个键。
  2. 提示区显示该键口诀，等待用户按键。
  3. 正确：`ok++`、键闪绿、450ms 后下一题。
  4. 错误：`bad++`、按键闪红、显示正确答案与口诀、高亮正确键，1100ms 后下一题。
  5. 统计正确/错误/正确率；点「结束」或离开视图时停止。
- 末笔识别码卡片是静态说明，不参与计分。

### 5.9 编码查询

输入处理（90ms 防抖）：

| 输入形态 | 处理 | 输出 |
| --- | --- | --- |
| `^[a-zA-Z]{1,4}$` | 反查 | 同码单字（最多 40）、同码词组（最多 30）、以该码开头的单字（最多 24） |
| 含汉字/其他 | 正查 | 若整体是已知词组先显示词组；再逐字显示编码；未收录字单独提示 |
| 空 | 占位提示 | “输入一个汉字、一个词，或者一段五笔编码” |

正查行内容：全码（大号）、简码（若不同）、逐键“字母 + 键名”、标签（一级简码 / N 级简码 / 键名字 / 成字字根）。反查每行同理，词组显示“N 字词”。

快捷词：我、的、中国、五笔、练习、rqyy、khlg。

### 5.10 统计页

- 五张卡：累计字数、总正确率、最快速度、今日、连续练习。
- 最近练习：12 条，显示时间（MM-DD HH:MM）、类型/字库/数量、速度与正确率（由 correct/wrong 现算）。
- 错字本：全部错字 chip（字 + 次数 + 连对进度，如 `连对 2/3`），点击跳到查询页；「练一遍」把单字练习切到 `errors` 字库并立即开一轮。
- 错字本卡片底部提示：专项练习连续 3 次全对（无错键、无提示、无跳过）自动移出。
- 每次进入视图都会重新请求 `/api/stats`，保证数据最新。

### 5.11 设置与偏好

浮层 `#settingsPanel`，点齿轮或点击空白关闭。

| 控件 | 行为 |
| --- | --- |
| 每轮字数 20/50/100 | 更新 `state.perRound`，**两个** Trainer 都 `startRound()` |
| 编码模式 简码优先/全码 | 更新 `state.mode`，单字 Trainer 重开（词组不受影响） |
| 初学模式 | 更新 `state.autoHint`；关闭时把当前题的 `hintShown` 置 false；对所有 Trainer 刷新提示与按钮 |
| 按键音效 | 更新 `state.sound`，立即生效 |

持久化键：`localStorage['wubi.prefs.v2'] = {perRound, mode, autoHint, sound}`。

使用 v2 键的原因：v1 的 `hint` 语义是“始终显示提示”，与新版默认行为冲突，升级键名可避免旧偏好让提示常显。

### 5.12 路由

- `hashchange` → `route()`。
- 解析 `#/<view>?<query>`，非法视图回退到 `five`。
- 切 `.active`、切导航高亮、滚动到顶部。
- 进入 `stats` 拉统计；进入 `dict` 时若带 `q` 参数则直接查询并聚焦输入框。
- 离开 `roots` 时停止键位练习。

### 5.13 事件与优先级

| 事件 | 条件 | 动作 |
| --- | --- | --- |
| 字母键 | 对应练习视图、无弹层 | 输入判定 |
| 空格 | 对应练习视图、无弹层 | 请求提示（需已答错） |
| Esc | 弹层打开 | 由弹层处理：关闭并开新轮 |
| Esc | 设置面板打开 | 收起面板 |
| Esc | five/words 视图 | `startRound()` + toast「已重新开始本轮」 |
| Esc | 其他视图 | 无动作 |
| 字母键 | roots 视图且练习中 | 键位反应判定 |
| 点击键位 | roots 视图 | 查看该键详情 |

注意：两个 Trainer 都注册了 window keydown 监听，但都先判断 `state.view`；同一时刻只有一个生效。Esc 由 boot 中的单一全局监听器处理，避免双 Trainer 重复重开。

---

## 6 关键流程

### 6.1 一轮练习

```text
用户选字库/改设置/按 Esc
   └─ startRound()
        ├─ 复制字库 → shuffle → bag
        ├─ 重置 done/correct/wrong/streak/errors/startedAt
        ├─ 清空旧的 tick 与 advanceTimer，启动 500ms tick
        ├─ 进度 0/perRound、指标清零
        └─ nextItem()：抽题 → 渲染字/槽位 → 提示=隐藏
用户按键 ──► input()
   正确 → 填槽/推进 → 满码 complete()
   错误 → 计数/闪红/进入“待提示”，不推进
满码 → complete() → 500ms → nextItem() 或 endRound()
```

### 6.2 本轮结算与上报

```text
Trainer.complete()（最后一字）
   └─ 500ms 后 endRound()
        ├─ clearInterval(timer)
        ├─ showSummary({...})            # 立即展示，不等网络
        └─ POST /api/session
             ├─ 服务端校验/插入 sessions
             ├─ upsert err_chars
             └─ 返回 {todayChars, accuracy, stats}
                  ├─ 更新“今日 N 字”
                  ├─ 刷新错字本 → renderPools()
                  └─ state.stats 缓存
用户关闭结算层 → startRound()（新一轮）
```

网络失败时静默（`catch` 空处理），本轮成绩不入库，但界面统计仍显示本地计算结果。

错字本的连对判定不等到本轮结算：每个错字完成或出错时即时调用 `/api/error-review`，因此即使用 Esc 中断本轮，连对或清零也已经生效（已移出的字不会因为没结算而复活）。

### 6.3 Esc 重开

```text
keydown Escape
 ├─ modalOpen? → 返回（弹层自己处理）
 ├─ 设置面板开? → 收起，结束
 ├─ 视图不是 five/words? → 结束
 └─ trainer.startRound()
      ├─ clearInterval / clearTimeout(advanceTimer)
      ├─ 重置本轮统计与进度
      └─ toast「已重新开始本轮」
```

清除 `advanceTimer` 是为了避免“完成一字后 500ms 自动换题”的定时器在重开后把新题顶掉。

### 6.4 错字本专项

统计页「练一遍」：

1. 校验 `state.errorChars` 非空。
2. 把单字 Trainer 的 `poolId` 设为 `errors`，同步 `state.pool`。
3. `renderPools()` 更新 chip 高亮，`startRound()` 开练。
4. 跳到 `#/five` 并 toast 提示。

单字判定与移出：

```text
完成一个字（pool=errors）
 ├─ 有错键 / 看过提示 / 初学模式 → 不调用成功判定（错键与提示已调用失败判定）
 └─ 全对 → POST /api/error-review {char, ok:true}
      ├─ streak < 3 → 结果区显示“连对 N/3”
      └─ streak = 3 → 删除数据库记录
            ├─ state.errorChars 移除该字
            ├─ bag 移除该字（本轮不再出现）
            ├─ renderPools() 更新 chip 数量
            └─ toast「X 连续 3 次全对，已移出错字本」
```

答错 / 用提示 / 跳过时调用 `{ok:false}` 立即清零连对，避免“上次连对 2 次、这次答错又蒙对一次就移出”。
若错字本在本轮中被清空，下一题会提示“错字本已清空，切换字库或按 Esc 开始新一轮”。

### 6.5 词库与错字本刷新

- 每轮成功入库后重新 GET `/api/errors`，更新 `state.errorChars`，并重绘单字练习的 chip（错字本数量变化）。
- 统计页每次进入都重新拉取，保证与数据库一致。

---

## 7 UI / 视觉设计

下图是看图拆字页的实际界面（1280×1000 宽屏）：

![看图拆字界面](preview.png)

### 7.1 设计令牌

| 变量 | 值 | 用途 |
| --- | --- | --- |
| `--bg` | `#f4f1ea` | 页面纸色背景 + 点阵纹理 |
| `--paper` | `#fffdf8` | 卡片底色 |
| `--paper-2` | `#fbf7ef` | 次级底色（槽位、提示） |
| `--ink` | `#23201c` | 主文字、主按钮、键帽 |
| `--muted` | `#7d756a` | 次要文字 |
| `--line` / `--line-strong` | `#e7dfd2` / `#d8cebd` | 边框 |
| `--accent` | `#b23a2f` | 强调色（进度、当前槽） |
| `--ok` | `#2f7d5d` | 完成、正确率环 |
| `--bad` | `#c0392b` | 错误提示 |
| `--z1…--z5` | `#c0442f` `#1f7a6b` `#2f6f9f` `#b8791a` `#6a5acd` | 横竖撇捺折五区 |
| `--radius` | `16px` | 卡片圆角 |
| `--kai` | KaiTi/STKaiti/楷体 | 汉字展示 |
| `--mono` | Cascadia/JetBrains/Consolas | 编码与数字 |

### 7.2 布局

- 顶栏 sticky，内容区最大宽度 1180px。
- 练习台：进度头 → 大字卡 → 编码槽 → 提示 → 操作按钮 → 快捷键说明。
- 键盘卡：三行 25 键 + 五区图例。
- 指标：四列网格（移动端两列）。
- 字根页：键盘 + 详情两栏（≤980px 变单栏）。
- 统计页：五列卡片 + 两栏列表（≤980px 单栏）。

### 7.3 组件要点

| 组件 | 类名 | 说明 |
| --- | --- | --- |
| 字库 chip | `.chip` | 选中反色，右侧显示数量；空字库 `disabled` |
| 编码槽 | `.slot` | 虚线待填、实线已填、当前槽呼吸动画、完成绿色 |
| 键帽 | `.key` | 五区底边、键名字、字根（full 模式）、高亮/闪烁 |
| 提示行 | `.hint` | 默认灰、答错红、完成绿勾文本 |
| 指标卡 | `.metric` | 数值用等宽字体 |
| 结果环 | `.ring-wrap` | SVG `stroke-dasharray` 表示正确率 |
| 浮层 | `.popover` | 设置面板 |
| 弹层 | `.modal-mask` | 半透明遮罩 + 卡片动画 |

### 7.4 动效与可访问性

- 视图淡入 0.28s、字卡 pop 0.32s、按键 hit 0.25s、弹层 0.22s。
- `prefers-reduced-motion: reduce` 时所有动画缩短到 0.001ms。
- 键帽带 `aria-label`，toast 带 `role="status" aria-live="polite"`，弹层带 `role="dialog" aria-modal="true"`。
- 键盘操作全部可用，不依赖鼠标；输入框（查询页）可正常聚焦输入。

### 7.5 响应式

| 断点 | 调整 |
| --- | --- |
| ≤980px | 顶栏换行、字根页/统计页单栏、统计卡 3 列 |
| ≤640px | 隐藏副标题与“今日”、槽位与指标缩小、字根文字隐藏、代码网格 2 列 |

桌面为主；移动端可用但无软键盘适配。

---

## 8 非功能设计

### 8.1 性能

| 项 | 现状 | 说明 |
| --- | --- | --- |
| 首屏数据 | 约 3.4 MB JSON | 本机读取，4 个请求并行；解析 7 万单字/6 万词组约几十毫秒 |
| 出题 | O(1) 取 bag 尾部 | 洗牌一次性 O(n)，字库最大 12000 项 |
| 按键响应 | 同步判定 + 少量 DOM 更新 | 每次按键只重绘槽位与提示 |
| 指标刷新 | 500ms 一次 | 隐藏视图直接跳过 |
| 反查 | O(70k + 61k) 全表扫描 | 90ms 防抖；本机毫秒级，结果截断 |
| 服务端 | 全表聚合 | 个人规模无压力；每次请求独立连接 |

### 8.2 安全与隐私

- 仅绑定 `127.0.0.1`，不暴露局域网。
- 路径拼接经过 `safe_join` 越权校验。
- 请求体大小限制 200 KB，字段范围校验，防止异常数据写库。
- 前端不引用任何外部脚本/字体/图片；无埋点、无统计上报。
- 无账号体系；能访问本机端口的人即可读写练习记录（本地单用户假设）。

### 8.3 兼容性

- 浏览器需要支持 ES2017+（模板字符串、async/await、class、Set）。
- 依赖系统字体（楷体用于汉字展示），未安装楷体时退化到宋体。
- 音效使用 WebAudio Oscillator，不需要音频文件。
- Python 3.9 语法（无 `match`），Windows 路径处理使用 `os.path`。

### 8.4 可维护性

- 码表与逻辑分离：改字库规则只动 `tools/build_data.py`，改 UI 只动 `web/*`。
- 无构建步骤，改完刷新即可。
- 字根表是唯一数据源（`KEYS`），键位图、详情页、提示、指法都从它派生。
- 前端所有选择器以 `data-role` / 语义 id 为主，避免样式类耦合。

---

## 9 测试设计

### 9.1 测试策略

- **端到端**：用 Chrome DevTools Protocol 驱动真实浏览器、真实按键，验证交互链路与入库。
- **接口冒烟**：`/api/health`、`/api/stats`、`/api/errors`、`/api/session`、`/api/error-review` 的返回与校验。
- **数据自检**：构建脚本校验一级简码为 1 码、码表不缺字。
- **手工检查**：视觉、响应式、音效、长轮次稳定性。

### 9.2 端到端用例（`tools/e2e_test.py`）

前置：服务运行在 8765；Chrome 以 `--remote-debugging-port=9222` 启动；已安装 `websocket-client`。

| # | 用例 | 断言 |
| --- | --- | --- |
| 1 | 页面加载 | 字库 chip 出现，每轮 20 字（测试写入偏好） |
| 2 | 连续 20 字 | 每个正确键使 `.slot.filled` 递增；完成后出现结果或换题 |
| 3 | 结算 | 弹层显示正确率/再来一轮 |
| 4 | 入库 | `/api/stats` 的 totalChars 增加 20，最近记录 total=20 |
| 5 | 默认无提示 | 提示文案为“输入五笔编码”，无 `.key.active` |
| 6 | 错键 | toast 含“按错了”，提示区含“空格”，不显示正确键 |
| 7 | 空格提示 | 提示出现“X 名键 —— 口诀”，对应键高亮，槽位仍为空（不代填） |
| 8 | Esc 重开 | 完成一字后按 Esc，计数回到 `0 / 20`，toast 含“重新开始” |
| 9 | 跳过 | 当前字切换 |
| 10 | 全码模式 | 槽位数量等于该字 full 码长 |
| 11 | 查询正查/反查 | 的→RQYY，中国→KHLG，rqyy→的 |
| 12 | 键位练习 | 口诀对应键按下后正确数 = 1 |
| 13 | 词组练习 | 连续输入 3 个词，结果区出现编码标签 |
| 14 | 统计页 | 5 张统计卡渲染 |

注意：该测试会真实写入一条练习记录，仅在开发环境使用；正式数据请勿在用户库上跑，或跑完手动删除。

运行：

```powershell
python tools/e2e_test.py
```

### 9.3 错字本接口测试（`tools/test_error_review.py`）

在临时目录建库、随机端口启动临时服务，不接触正式 `progress.db`。覆盖：

- 旧库自动补 `right_streak` 列且保留原记录；
- 连对 1/2/3 次，第 3 次移出并返回剩余数量；
- 已移除的字再次上报正确不会复活；
- 答错、用提示（前端上报 false）、新一轮报错都会清零连对；
- 空 `char` 返回 400；`/api/stats` 的 errors 带 `streak`。

```powershell
python tools/test_error_review.py
```

### 9.4 手工检查清单

- [ ] 首次启动自动打开浏览器，端口被占用时自动 +1。
- [ ] 五个视图切换正常，刷新后停留在同一 hash。
- [ ] 打错后不显示答案；按空格显示；换字后重新隐藏。
- [ ] Esc 在练习中重开、在设置面板打开时只收起面板、在弹层中关闭弹层。
- [ ] 简码/全码切换后槽位数量正确变化。
- [ ] 音效开关即时生效。
- [ ] 一轮结束数据出现在统计页与错字本。
- [ ] 错字本专项连续 3 次全对后自动移出；答错/提示后连对归零，统计页 chip 显示“连对 n/3”。
- [ ] 窗口缩到 640px 以下布局不溢出。

---

## 10 部署与运行

### 10.1 启动方式

```bat
双击 run.bat
:: 或
C:\ProgramData\Anaconda3\python.exe app.py
:: 指定端口
C:\ProgramData\Anaconda3\python.exe app.py --port 9000
:: 不自动开浏览器
C:\ProgramData\Anaconda3\python.exe app.py --no-open
```

`run.bat` 逻辑：切到脚本目录 → 优先使用 `C:\ProgramData\Anaconda3\python.exe` → 找不到则用 PATH 中的 `python` → 都没有则提示安装。文件保存为 ASCII + CRLF，避免 cmd 解析中文/换行问题。

### 10.2 首次部署检查

1. `web/index.html`、`data/chars.json` 存在；
2. 端口 8765 未被占用（或允许自动 +1）；
3. 浏览器允许本机访问；
4. 需要重建数据时执行 `python tools/build_data.py`。

### 10.3 备份与迁移

- 统计：复制 `data/progress.db`（建议连同 `-wal`/`-shm` 一起复制，或先停服务）。
- 偏好：浏览器 localStorage（按 origin 保存），换端口不迁移。
- 码表：重新构建即可，无需备份。

---

## 11 扩展点

| 需求 | 改动位置 | 说明 |
| --- | --- | --- |
| 新增字库 | `build_data.py` 增加池 + `app.js` 的 `CHAR_POOLS` | 数量会自动显示在 chip |
| 换 98 版码表 | `_ref` 放新 dict、改 `build_data.py` 输入与 `KEYS` | 前端键位数据由 JSON 驱动，无需改逻辑 |
| 识别码题库 | 需要新增“末笔+字型”数据，新增字库与提示文案 | 现有 hint 只到键位级 |
| 导出成绩 | 新增 `/api/export`，读取 sessions | 可导出 CSV/JSON |
| 主题 | 修改 `:root` 变量或增加 `[data-theme]` | 五区色也是变量 |
| 在线词库更新 | 前端定时拉 `pools.json` | 需处理版本与缓存 |
| 声音方案 | 替换 `beep()` 或增加语音朗读 | 当前为 WebAudio 方波/正弦 |

---

## 12 已知限制

1. **只有 86 版**：码表、字根、口诀均按 86 版；98 版不适用。
2. **提示是键位级**：显示“该键的全部常见字根 + 口诀”，不是逐字唯一拆法；同一个键可能有多个字根，仍需学习者判断。
3. **不校验所有等价编码**：每题只有一个目标码（简码或全码），用户输入另一种合法编码不会被接受。
4. **`correct` 是按键数**：与 `total`（字数）不同量纲；展示正确率时不会误用，但直接看数据库需要理解这一点。
5. **错字本只通过专项练习移出**：需要连续 3 次全对（且未开初学模式、没用提示）；普通练习答对不会降低错误次数，答错会清零连对。
6. **词库按字频截断**：`w2/w3/w4` 只保留高频部分，可能缺少一些常用专有名词。
7. **无软键盘**：移动端需要外接键盘；页面布局可看但无法触屏打字。
8. **输入法干扰**：中文输入法开启时可能拦截字母，建议切换到英文输入；程序对空格做了 `preventDefault`。
9. **偏好按 origin 保存**：换端口（8765→8766）会重置 localStorage 设置。
10. **数据库无迁移**：表结构变更需手动处理；删库会清空统计。
11. **Esc 无确认**：立即丢弃本轮进度（设计如此）。
12. **两套 Trainer 都在启动时开轮**：词组练习在后台也创建了一轮，只有切到该视图才计时/刷新；对资源影响很小。

---

## 附录 A：25 键字根与口诀

| 键 | 区 | 键名 | 口诀 |
| --- | --- | --- | --- |
| G | 横 | 王 | 王旁青头戋（兼）五一 |
| F | 横 | 土 | 土士二干十寸雨 |
| D | 横 | 大 | 大犬三羊古石厂 |
| S | 横 | 木 | 木丁西 |
| A | 横 | 工 | 工戈草头右框七 |
| H | 竖 | 目 | 目具上止卜虎皮 |
| J | 竖 | 日 | 日早两竖与虫依 |
| K | 竖 | 口 | 口与川，字根稀 |
| L | 竖 | 田 | 田甲方框四车力 |
| M | 竖 | 山 | 山由贝，下框几 |
| T | 撇 | 禾 | 禾竹一撇双人立，反文条头共三一 |
| R | 撇 | 白 | 白手看头三二斤 |
| E | 撇 | 月 | 月彡（衫）乃用家衣底 |
| W | 撇 | 人 | 人和八，三四里 |
| Q | 撇 | 金 | 金勺缺点无尾鱼，犬旁留儿一点夕，氏无七 |
| Y | 捺 | 言 | 言文方广在四一，高头一捺谁人去 |
| U | 捺 | 立 | 立辛两点六门疒 |
| I | 捺 | 水 | 水旁兴头小倒立 |
| O | 捺 | 火 | 火业头，四点米 |
| P | 捺 | 之 | 之宝盖，摘礻（示）衤（衣） |
| N | 折 | 已 | 已半巳满不出己，左框折尸心和羽 |
| B | 折 | 子 | 子耳了也框向上 |
| V | 折 | 女 | 女刀九臼山朝西 |
| C | 折 | 又 | 又巴马，丢矢矣 |
| X | 折 | 纟 | 慈母无心弓和匕，幼无力 |

## 附录 B：一级简码

`我(q) 人(w) 有(e) 的(r) 和(t) 主(y) 产(u) 不(i) 为(o) 这(p) 民(n) 了(b) 发(v) 以(c) 经(x) 工(a) 要(s) 在(d) 地(f) 一(g) 上(h) 是(j) 中(k) 国(l) 同(m)`

## 附录 C：接口调用示例

```powershell
# 统计
curl.exe http://127.0.0.1:8765/api/stats

# 错字本
curl.exe http://127.0.0.1:8765/api/errors

# 上报一轮
curl.exe -X POST http://127.0.0.1:8765/api/session ^
  -H "Content-Type: application/json" ^
  -d "{\"mode\":\"char\",\"pool\":\"common\",\"total\":20,\"correct\":57,\"wrong\":3,\"duration\":45,\"errors\":[\"的\"]}"
```

## 附录 D：关键常量速查

| 常量 | 值 | 位置 |
| --- | --- | --- |
| 默认端口 | 8765 | `app.py` |
| 端口尝试范围 | +20 | `pick_port()` |
| 请求体上限 | 200000 字节 | `do_POST` |
| 会话保留展示 | 12 条 | `stats_payload()` |
| 错字展示 | 40 条 | `stats_payload()` |
| 自动换字 | 500 ms | `complete()` |
| 指标刷新 | 500 ms | `startRound()` |
| 字卡 pop | 340 ms | `nextItem()` |
| 按键闪烁 | 260 ms | `flashKey()` |
| toast | 1600 / 2600 ms | `toast()` |
| 查询防抖 | 90 ms | `mountDict()` |
| 键位练习换题 | 450 / 1100 ms | `roots.onKey` |
| 错字移出阈值 | 3 次连续全对 | `app.py` `handle_error_review` |
| 错字判定接口 | `POST /api/error-review` | `app.py` |
| 偏好键 | `wubi.prefs.v2` | `app.js` |

## 附录 E：文档修订记录

| 版本 | 日期 | 说明 |
| --- | --- | --- |
| 1.1 | 2026-11-20 | 首版：依据当时代码整理架构、数据、接口、前端与测试设计 |
| 1.2 | 2026-11-20 | 增加错字本“专项练习连对 3 次自动移出”的表结构、接口与流程 |
| 1.3 | 2026-11-21 | 按最终代码复核；补充界面截图、测试脚本说明与修订记录 |

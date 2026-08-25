# WordGap — AI Agent 等待间隙背单词工具 设计文档

> 版本:v0.1(设计稿)  日期:2026-08-25  状态:待评审,未开工
>
> 一句话:当 Claude Code / Codex / pi / WorkBuddy 在跑任务时,自动弹出单词卡接着上次的进度背;
> agent 跑完(或需要你确认权限)时,提醒并自动收起。进度全局持久,与任何会话无关。

---

## 1. 目标与非目标

### 1.1 目标(MVP 必须满足)

1. **断点续背**:一本词书一个全局游标。换对话、换 agent、重启电脑,下次弹出时从上次的位置继续。
2. **自动生命周期**:agent 开始跑 → 延迟弹出;agent 跑完 / 请求权限确认 → 提醒 + 软关闭。全程无需手动开关。
3. **多 agent 适配**:MVP 支持 Claude Code + Codex CLI;架构上加一个 agent 只需新增一个 adapter,不改核心。
4. **顺序 / 乱序两种模式**:乱序采用固定种子洗牌,同样可断点续背。
5. **词书**:兼容 qwerty-learner 开源词库 JSON 格式,导入即用。

### 1.2 非目标(明确不做,防止范围蔓延)

- ❌ 间隔重复(FSRS/SM-2)——数据模型预留字段,MVP 不实现调度。
- ❌ 云同步、多设备、账号系统——纯本地单机。
- ❌ 浏览器扩展 / Web 版 agent(Codex Web 等)适配——只做本地 CLI/桌面 agent。
- ❌ 发音音频、例句、AI 生成内容——MVP 只有 词形 + 音标 + 释义。
- ❌ 多用户、多词书并行进度——同一时刻只有一本"当前词书"。

### 1.3 成功标准

连续使用 5 个工作日后:每天在 agent 等待间隙自然背到 ≥30 个词,且没有因为弹窗时机不当而想关掉它。

---

## 2. 总体架构

```
┌─────────────────────────────────────────────────────────┐
│  Adapter 层(每个 agent 一个,只做一件事:上报事件)      │
│  claude-code hooks │ codex notify+log │ pi ext │ workbuddy│
└───────────────┬─────────────────────────────────────────┘
                │ HTTP POST /event  (localhost:8765)
┌───────────────▼─────────────────────────────────────────┐
│  Daemon(FastAPI,常驻)                                  │
│  · 会话状态机:Map<session_id, AgentState>               │
│  · UI 调度状态机:HIDDEN → ARMED → SHOWING → SOFT_CLOSE  │
│  · 定时器:延迟弹出 / 自动收起                            │
└───────────────┬─────────────────────────────────────────┘
                │ 进程内调用 / WebSocket
┌───────────────▼─────────────────────────────────────────┐
│  UI 层(pywebview 置顶悬浮窗,HTML/JS 单词卡)            │
└───────────────┬─────────────────────────────────────────┘
                │
┌───────────────▼─────────────────────────────────────────┐
│  Store 层(SQLite,唯一持久状态)                          │
│  wordbook / progress / word_log / session_stat           │
└─────────────────────────────────────────────────────────┘
```

**核心不变式(整个系统最重要的一条约束):**

> 背单词进度只存在于 Store 层,与任何 agent 会话、任何弹窗生命周期无关。
> Adapter 和 Daemon 永远不写进度;UI 每完成一个词就立刻写库。
> 因此"断点续背"不是一个功能,而是架构的自然结果。

### 2.1 技术栈(定死,不再讨论)

| 层 | 选型 | 理由 |
|----|------|------|
| Daemon | Python 3.11+ / FastAPI / uvicorn | 与使用者现有技术栈一致(天后医美项目同栈) |
| UI | pywebview(HTML/CSS/JS 卡片) | 打字判定和动画用前端做省力;tkinter 备选降级 |
| 存储 | SQLite(stdlib `sqlite3`) | 单文件、零依赖、事务够用 |
| Adapter 脚本 | PowerShell(.ps1)为主 | Windows 平台;**禁止 .bat 含中文**(见 §7) |
| 测试 | pytest + pytest-cov | 核心逻辑(store/状态机)覆盖 ≥80% |
| 打包 | 暂不打包,`python -m wordgap` 启动 | MVP 阶段不折腾 pyinstaller |

### 2.2 目录结构

```
wordgap/
├── spec.md                  # 本文档
├── README.md
├── pyproject.toml
├── wordgap/
│   ├── __main__.py          # python -m wordgap 入口:启动 daemon + UI
│   ├── config.py            # 全部常量与用户配置(唯一允许出现"魔法数字"的文件)
│   ├── daemon/
│   │   ├── app.py           # FastAPI 路由(仅路由,不含业务逻辑,<150 行)
│   │   ├── sessions.py      # 会话状态机(纯函数核心)
│   │   ├── scheduler.py     # UI 调度状态机 + 定时器(纯函数核心 + 薄 IO 壳)
│   │   └── events.py        # 事件数据类(pydantic 模型)
│   ├── store/
│   │   ├── db.py            # 连接管理、建表、迁移
│   │   ├── wordbooks.py     # 词书导入/查询
│   │   ├── progress.py      # 游标读写、洗牌、取下一个词
│   │   └── stats.py         # 学习统计(word_log / session_stat)
│   ├── ui/
│   │   ├── window.py        # pywebview 窗口管理(置顶、不抢焦点、显示/隐藏)
│   │   ├── bridge.py        # JS↔Python 桥(暴露给前端的 API)
│   │   └── web/
│   │       ├── index.html
│   │       ├── card.js      # 单词卡逻辑(打字判定、软关闭横幅)
│   │       └── card.css
│   └── adapters/            # 安装脚本 + 钩子脚本(不是 Python 包)
│       ├── claude_code/
│       │   ├── install.py   # 把 hooks 写入 ~/.claude/settings.json(merge,不覆盖)
│       │   └── notify.ps1   # 钩子实际执行的上报脚本
│       ├── codex/
│       │   ├── install.py   # 写 ~/.codex/config.toml 的 notify 项
│       │   ├── notify.ps1
│       │   └── log_watcher.py  # sessions JSONL 监听(检测"开始",daemon 内加载)
│       ├── pi/
│       │   └── wordgap.ts   # pi extension:turn_start / agent_end → HTTP POST
│       └── workbuddy/
│           └── install.py   # 复用 claude_code 的钩子格式,写 ~/.workbuddy-ai/settings.json
├── dicts/                   # 内置词书(qwerty-learner JSON 原格式)
└── tests/
    ├── test_sessions.py
    ├── test_scheduler.py
    ├── test_progress.py
    └── test_wordbooks.py
```

**文件规模约束**:见 §7.1(单文件硬上限 500 行)。

---

## 3. 数据模型(Store 层)

数据库文件:`%USERPROFILE%\.wordgap\wordgap.db`。全部时间戳存 ISO8601 本地时间字符串。

```sql
-- 词书。words_json 为 qwerty-learner 原格式数组:
-- [{"name":"abandon","trans":["放弃"],"usphone":"ə'bændən"}, ...]
CREATE TABLE wordbook (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    word_count  INTEGER NOT NULL,
    words_json  TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

-- 进度:每本词书一行。这是"断点续背"的全部真相。
CREATE TABLE progress (
    wordbook_id  INTEGER PRIMARY KEY REFERENCES wordbook(id),
    mode         TEXT NOT NULL CHECK (mode IN ('sequential','shuffled')),
    shuffle_seed INTEGER,          -- shuffled 模式下的洗牌种子;sequential 为 NULL
    cursor       INTEGER NOT NULL DEFAULT 0,   -- 已完成的词数(即下一个词的下标)
    updated_at   TEXT NOT NULL
);

-- 每词记录:MVP 只写不读(统计页用),同时为将来 FSRS 预留。
CREATE TABLE word_log (
    id           INTEGER PRIMARY KEY,
    wordbook_id  INTEGER NOT NULL,
    word_index   INTEGER NOT NULL,   -- 洗牌前的原始下标
    word         TEXT NOT NULL,
    result       TEXT NOT NULL CHECK (result IN ('pass','fail','skip')),
    typo_count   INTEGER NOT NULL DEFAULT 0,
    seen_at      TEXT NOT NULL,
    -- FSRS 预留(MVP 全为 NULL):
    stability    REAL, difficulty REAL, due_at TEXT
);

-- 每轮弹窗统计(可选,做"本轮背了 N 个"和日报用)
CREATE TABLE session_stat (
    id          INTEGER PRIMARY KEY,
    agent       TEXT NOT NULL,       -- 'claude-code' | 'codex' | 'pi' | 'workbuddy'
    started_at  TEXT NOT NULL,
    ended_at    TEXT,
    words_done  INTEGER NOT NULL DEFAULT 0
);

-- 全局键值(当前词书 id、上次窗口位置等)
CREATE TABLE kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

### 3.1 顺序与乱序的实现规则

- **sequential**:第 N 个弹出的词 = `words[cursor]`,完成后 `cursor += 1`。
- **shuffled**:导入词书或切换模式时生成 `shuffle_seed`(一次性),
  取词时 `order = seeded_shuffle(range(word_count), seed)`,第 N 个词 = `words[order[cursor]]`。
  seed 不变 ⇒ 顺序确定 ⇒ 断点可续;每个词仍只出现一次。
- 背完一轮(`cursor == word_count`):弹窗显示"本书完成",游标归零并换新 seed,开始第二轮。
- **游标写入时机**:UI 每完成一个词立即写库(单条 UPDATE,含 `updated_at`)。
  崩溃最多丢失当前正在拼的半个词。禁止"关闭时才保存"。

### 3.2 Store 层工程约束

- 所有写操作走参数化 SQL(禁止字符串拼接)。
- `progress.py` 对外只暴露纯数据出入的函数:
  `get_next_word(wordbook_id) -> Word | None`、`commit_word(wordbook_id, result, typo_count) -> None`、
  `get_progress_summary(wordbook_id) -> ProgressSummary`。调用方(UI/daemon)不接触 SQL。
- 只有 daemon 进程访问数据库(UI 通过 bridge 走 daemon),天然串行,无并发写问题。

---

## 4. Daemon 设计

### 4.1 事件协议(Adapter → Daemon)

`POST http://127.0.0.1:8765/event`,body:

```json
{
  "agent":      "claude-code",         // 枚举:claude-code | codex | pi | workbuddy | dsh
  "session_id": "任意稳定字符串",       // 同一次 agent 会话内保持一致即可
  "event":      "running",             // running | done | attention
  "ts":         "2026-08-25T14:30:00"  // 可选,缺省用服务端时间
}
```

- `running`:agent 开始执行一轮任务(用户提交了 prompt)。
- `done`:本轮任务结束,输出已就绪。
- `attention`:agent 停下来等用户(权限确认、提问)。**对 UI 而言与 done 等价**——都意味着"你该回去看了",但横幅文案不同("⏸ Claude Code 在等你确认")。

其他端点:

- `GET /state`:当前全部会话状态 + UI 状态(调试用)。
- `GET /healthz`:存活检查(adapter 安装脚本用它验证 daemon 在跑)。

**安全约束**:daemon 只绑定 `127.0.0.1`;事件体做 pydantic 校验,非法 agent/event 值直接 422;不执行任何来自事件的内容(事件是数据,不是指令)。

### 4.2 会话状态机(`sessions.py`)

维护 `Map<(agent, session_id), SessionState>`,`SessionState ∈ {RUNNING, IDLE}`。

规则:

1. 收到 `running` → 该会话置 RUNNING。
2. 收到 `done`/`attention` → 该会话置 IDLE,并向调度器发一条 `AgentFinished(agent, kind)` 通知。
3. **过期清理**:RUNNING 超过 `SESSION_TTL`(默认 30 分钟)未再收到事件 → 视为孤儿会话,静默清理(agent 崩溃/被 kill 的兜底)。
4. 派生量 `any_running: bool` 供调度器使用。

实现约束:状态机核心为**纯函数** `reduce(state, event) -> (new_state, effects)`,不做 IO;
定时器、HTTP 由外壳注入。这是为了可测试(见 §8)。

### 4.3 UI 调度状态机(`scheduler.py`)

```
            any_running=true                 延迟计时到
  HIDDEN ────────────────────▶ ARMED ─────────────────▶ SHOWING
    ▲                            │                         │
    │      AgentFinished 且       │ any_running=false        │ AgentFinished
    │      当前词已提交            ▼ (计时未到,静默取消)      ▼
    └──────────────────────── SOFT_CLOSING ◀───────────────┘
                              (横幅提示,等当前词完成,
                               展示小结 2s,然后 HIDDEN)
```

关键规则(体验的分水岭,全部可配,默认值见 §6):

1. **延迟弹出**:进入 ARMED 后等 `POPUP_DELAY_SEC`(默认 18s)才真正显示。
   期间任务就结束了 ⇒ 静默取消,用户毫无感知。**这条规则防止"闪弹",是最重要的体验规则。**
2. **软关闭**:SHOWING 中收到 `AgentFinished` ⇒ 不立即关窗,顶部亮横幅
   ("✅ codex 跑完了 / ⏸ claude-code 在等你确认"),允许把当前词拼完;
   当前词提交后显示本轮小结(背了 N 个,累计 X/Y),`SUMMARY_LINGER_SEC`(2s)后隐藏窗口。
3. **多会话**:`AgentFinished` 一律触发软关闭流程,即使还有别的会话在 RUNNING
   (理由:任何一个跑完你都要切走看结果)。若用户没理会横幅继续背、且仍有会话 RUNNING,则保持 SHOWING。
4. **手动逃生**:`Esc` 立即隐藏窗口(当前词按 skip 记录);全局热键(默认 `Ctrl+Alt+W`)手动唤起/隐藏,
   与 agent 状态无关(想主动背也行)。

同 §4.2:核心为纯函数 reducer,定时器作为注入的 effect 执行。

---

## 5. Adapter 设计(每个 agent 的适配细节)

统一原则:**adapter 只上报事件,不包含任何业务逻辑;单个钩子脚本 ≤20 行**;
上报失败(daemon 没开)必须静默吞掉,绝不能影响 agent 本身运行(`try/catch` + 1s 超时)。

### 5.1 Claude Code(M1)

机制:官方 hooks(`~/.claude/settings.json` 的 `hooks` 字段)。

| Hook | 上报事件 |
|------|---------|
| `UserPromptSubmit` | `running` |
| `Stop` | `done` |
| `Notification`(权限请求/空闲提醒) | `attention` |

- `session_id` 直接用 hook 输入 JSON 里的 `session_id` 字段。
- 钩子命令统一为:`powershell -NoProfile -File <安装目录>\notify.ps1 -Event running`,
  脚本内部读 stdin 的 JSON 拿 session_id,`Invoke-RestMethod` POST,超时 1s,出错静默退出 0。
- `install.py` 职责:**merge** 进现有 settings.json(绝不覆盖用户已有 hooks),写入前备份原文件,
  提供 `--uninstall` 精确移除自己写入的条目。

### 5.2 Codex CLI(M3)

机制:两半拼起来。

- **done**:`~/.codex/config.toml` 的 `notify` 配置(官方,任务完成时执行命令)→ `notify.ps1 -Event done`。
- **running**:Codex 无"开始"钩子。用 `log_watcher.py`(daemon 内的后台任务)监听
  `~/.codex/sessions/**/*.jsonl` 的追加:出现新的 user message 条目 ⇒ 上报 `running`。
  watcher 用轮询(2s 间隔)而非文件系统事件,实现简单且 Windows 下更可靠。
- `session_id` 用 JSONL 文件名(即 codex 的 session id)。
- 风险:sessions 日志格式非公开契约,codex 升级可能变。隔离在 `log_watcher.py` 单文件内,
  解析失败时降级为"只有 done 信号"(弹窗改为手动唤起),并在日志中警告。

### 5.3 pi(M4)

机制:官方 extension。`wordgap.ts` 注册 `pi.on('turn_start')` → `running`,
`pi.on('agent_end')` → `done`,fetch POST 到 daemon,1s 超时。安装 = 复制到 pi 的 extensions 目录。

### 5.4 dsh / DeepSeek Harness(M4)

机制:两条路线,优先路线 A。

- **路线 A(零成本)**:dsh 官方提供 Claude Code / Codex 的 **hook bridge**,可直接运行已有的
  hooks.json——即我们为 Claude Code 写的钩子在 dsh 下原样生效,仅 `agent` 字段上报为 `dsh`
  (钩子脚本加 `-Agent dsh` 参数区分)。
- **路线 B(原生插件)**:dsh 是微内核架构(基于 Cordis),万物皆插件,生命周期事件有
  pre-step / turn-end 等;若 bridge 覆盖不全,写一个原生 dsh 插件监听 turn 开始/结束 → HTTP POST。
- 生态调研结论(2026-08):dsh 插件生态(awesome-deepseek-harness / dsh-plugin topic)中
  **没有**背单词/flashcard 类插件,通知类只有 dsh-auto-continue、dsh-web-attention-badge 等;
  WordGap 若发原生插件属生态空白。

### 5.5 WorkBuddy(M4)

机制:WorkBuddy 提供 Claude Code 兼容的 command hooks(`~/.workbuddy-ai/settings.json`)。
`install.py` 复用 claude_code 的钩子脚本与 merge 逻辑,仅目标路径不同。
注意:WorkBuddy 桌面版权限走自己的 GUI,不注册 permission 相关 hook,只接 `running/done`。
(此条待实机验证,列入 §10 开放问题。)

---

## 6. UI 设计(悬浮窗单词卡)

### 6.1 窗口行为

- 尺寸约 380×220,置顶(always-on-top),无边框,记住上次位置(存 kv 表)。
- **不抢焦点**:显示时不夺取键盘焦点(Windows 下创建时带 `WS_EX_NOACTIVATE` 语义;
  pywebview 如无法直接支持,降级方案:显示后立即把前台窗口还给原窗口)。
  用户**点击卡片后**才开始接收键盘;`Esc` 隐藏并把焦点还回去。
- 半透明度可配(默认 0.95)。

### 6.2 交互模式(MVP 只做打字模式)

qwerty-learner 式:显示 释义 + 音标,用户凭记忆敲出单词。

- 敲对一个字母亮一个;敲错整词抖动、`typo_count += 1`、清空重敲。
- 敲完整词 ⇒ `result = pass`(typo_count>0 也算 pass,记录在 typo_count);自动出下一词。
- 不会拼:按 `Tab` 显示答案,抄写一遍,`result = fail`。
- `Esc`:当前词记 skip,隐藏窗口。
- 认读模式(看词点"认识/不认识")留作 M4 之后的可选模式,数据模型已兼容。

### 6.3 软关闭横幅

窗口顶部常驻一条状态栏:平时显示 `355/3674 · CET-6 · 乱序`;
收到 AgentFinished 时变为高亮横幅 `✅ codex 跑完了 — 拼完这个词就收工`,当前词提交后进入小结页。

---

## 7. 工程约束(全项目强制,code review 时逐条检查)

### 7.1 规模约束(硬性)

| 对象 | 目标 | 硬上限 | 超限处理 |
|------|------|--------|---------|
| 单文件 | ≤300 行 | **500 行** | 必须拆分;拆分方案先更新 §2.2 目录结构再动手 |
| 单函数 | ≤30 行 | 50 行 | 提取子函数 |
| 单类 | ≤150 行 | 200 行 | 拆分职责 |
| 嵌套深度 | ≤3 层 | 4 层 | 改早返回 / 提取函数 |
| 单目录文件数 | ≤8 个 | — | 说明模块职责过宽,重新划分模块 |

行数含注释与空行,统计口径 `wc -l`。任何"先超着,以后再拆"的提交不允许合入。

### 7.2 分层与依赖方向(硬性)

依赖箭头只允许:`ui → daemon → store`;`adapters --HTTP--> daemon`(进程外,无代码依赖)。

- `store/` 不得 import `daemon/` 或 `ui/`;`daemon/` 不得 import `ui/`(daemon 通过注入的回调通知 UI)。
- SQL 只允许出现在 `store/`;pywebview API 只允许出现在 `ui/window.py` 与 `ui/bridge.py`;
  字面常量只允许出现在 `config.py` 与测试代码。
- 跨层传数据一律用 frozen dataclass,禁止裸 dict 跨层(词条 JSON 在 store 内解析成 dataclass 再出门)。
- `adapters/` 与主包零共享代码(它们运行在别的进程/运行时),宁可重复十行也不抽公共库。

### 7.3 纯函数内核,薄 IO 外壳

`sessions.py` / `scheduler.py` 的决策逻辑必须是无 IO 纯函数,统一签名约定:

```
reduce_xxx(state, input, now, ...) -> tuple[NewState, list[Effect]]
```

- Effect 是 frozen dataclass,由外壳解释执行(开定时器、发 HTTP、调 UI)。
- reducer 内禁止:读系统时钟(`now` 由外部传入)、取随机数(seed 由外部传入)、任何 IO、修改入参。
- `store/` 的函数允许 IO(它就是 IO 层),但时间参数同样可注入(默认 `now=None` → 取当前时间),保证可测。

### 7.4 不可变数据

状态对象一律 `@dataclass(frozen=True)`,reducer 返回新对象,禁止原地修改。
禁止可变默认参数;禁止模块级可变全局状态(唯一例外:`__main__.py` 组合根持有的对象)。

### 7.5 类型与风格

- 全量 type hints;公开函数缺注解视为未完成。
- 命名:模块/函数 `snake_case`,类 `PascalCase`,常量 `UPPER_SNAKE_CASE`,布尔加 `is_/has_/should_` 前缀。
- docstring:每个公开函数/类一行说明;行内注释只写"代码看不出来的约束",不写"这行在干什么"。

### 7.6 常量与配置

所有阈值/路径/端口只在 `config.py` 定义;其余文件出现裸数字视为违规。

```python
POPUP_DELAY_SEC = 18      # ARMED → SHOWING 的延迟
SUMMARY_LINGER_SEC = 2    # 小结停留
SESSION_TTL_MIN = 30      # 孤儿会话清理
DAEMON_PORT = 8765
ADAPTER_TIMEOUT_SEC = 1   # 钩子上报超时
```

用户可用 `~/.wordgap/config.json` 覆盖(启动时 merge,非法值回退默认并警告)。

### 7.7 错误处理与日志

- 统一 `logging`,禁止 `print`(安装脚本对用户的提示除外)。
- 分级约定:DEBUG=状态机转移明细;INFO=弹出/收起/导入/安装;WARNING=降级(如 codex 日志解析失败);ERROR=异常。
- daemon 日志写 `~/.wordgap/logs/daemon.log`,按天轮转保留 7 天。
- 禁止裸 `except`;捕获必须指明异常类型并记日志。**唯一例外**:adapter 钩子脚本允许 catch-all——
  它的最高使命是"绝不拖累 agent",任何异常静默吞掉、1s 超时、退出码 0。
- UI 侧 bridge 调用失败显示"连接丢失"占位,不崩窗。

### 7.8 数据与编码(Windows 特别约束)

- 一切文件 IO 显式 `encoding="utf-8"`;`json.dump` 一律 `ensure_ascii=False`。
- 如必须生成 .bat,**内容一律纯英文**(全局规则);优先用 .ps1,写文件显式 `-Encoding utf8`。
- 路径一律 `pathlib.Path`,禁止字符串拼路径;用户目录经 `Path.home()`。

### 7.9 安装脚本三原则

merge 不覆盖(绝不动用户已有配置项)、写前备份(`*.bak.<时间戳>`)、`--uninstall` 精确移除自己写入的条目。

### 7.10 依赖最小化

运行时依赖仅 `fastapi`、`uvicorn`、`pywebview`、`pydantic`;
**M0 内核与其测试只用标准库 + pytest**。新增任何依赖需在 §2.1 登记理由。

### 7.11 版本管理

- M0 开工时 `git init`;conventional commits(feat/fix/test/docs/chore)。
- 小步提交:一个模块 + 其测试为一个 commit;每个里程碑完成打 tag(`m0`、`m1`…)。
- 每个里程碑结束做一次 code review,CRITICAL/HIGH 问题修完才进入下一里程碑。

### 7.12 完成定义(Definition of Done)

一个模块"完成" = 单测全绿 + 覆盖率达标(§8) + 规模约束(§7.1)全过 + 依赖方向(§7.2)无违规 +
**若实现与本文档有偏离,先改文档再合入代码**(文档是唯一事实源)。

---

## 8. 测试策略

覆盖率目标:**store + daemon 纯函数核心 ≥80%**(UI 与 adapter 脚本不计入,手测清单代替)。

| 模块 | 方式 | 关键用例 |
|------|------|---------|
| `progress.py` | pytest,内存 SQLite | 顺序/乱序断点续背;同 seed 顺序稳定;背完一轮归零换 seed;崩溃恢复(只丢当前词) |
| `sessions.py` | 纯函数单测 | running/done/attention 转移;多会话;TTL 孤儿清理 |
| `scheduler.py` | 纯函数单测(虚拟时钟) | 延迟期内结束→静默取消;SHOWING 中 finished→软关闭;多会话仍 RUNNING 时不强关;Esc 逃生 |
| `wordbooks.py` | pytest | qwerty-learner JSON 导入;畸形 JSON 报错不入库 |
| adapter 安装 | 手测清单 | merge 不破坏已有 hooks;卸载后 settings 还原;daemon 未启动时 agent 不受影响 |
| UI | 手测清单 | 不抢焦点;打字判定;横幅;窗口位置记忆 |

TDD 流程:每个模块先写用例(RED)再实现(GREEN),见全局 testing 规则。

---

## 9. 里程碑(按序执行,每个里程碑结束做一次 code review)

| 里程碑 | 内容 | 验收标准 | 预估 |
|--------|------|---------|------|
| **M0 内核** | store 全部 + sessions/scheduler 纯函数 + 全部单测 | pytest 全绿,覆盖 ≥80%,无 UI 无网络 | 1 天 |
| **M1 走通** | daemon(FastAPI)+ Claude Code adapter;UI 暂用 Windows toast 通知代替 | 真机:提问 18s 后弹 toast,Stop 后弹"跑完"toast,断点数字正确 | 1 天 |
| **M2 单词卡** | pywebview 悬浮窗 + 打字模式 + 软关闭 + 断点续背全流程 | 真机连续使用一下午无闪弹、无焦点抢夺、进度不丢 | 1~2 天 |
| **M3 Codex** | codex notify + log_watcher | 两个 agent 同开,任一结束都正确软关闭 | 0.5~1 天 |
| **M4 扩展** | pi extension + dsh(hook bridge 路线)+ WorkBuddy + 统计页(今日/累计) | — | 1~1.5 天 |
| M5(可选) | FSRS 间隔重复、认读模式、打包 exe | — | 另行评估 |

**M2 结束后先真实使用 3~5 天再决定是否继续 M3+**(验证"我真的会在等待时背单词"这个前提)。

## 10. 开放问题(实施前需确认或实机验证)

1. pywebview 在 Windows 11 上能否做到真正的"显示但不抢焦点"?若不能,采用 §6.1 的降级方案,M2 首日验证。
2. Codex sessions JSONL 中"user message"条目的准确字段名 —— M3 开工时抓一份真实日志确认。
3. WorkBuddy 的 Claude-Code 兼容 hooks 覆盖哪些事件 —— M4 开工时实机验证。
3b. dsh 的 Claude Code hook bridge 是否透传 UserPromptSubmit/Stop/Notification 三个事件、
    session_id 字段是否一致 —— M4 开工时实机验证;不行则走原生插件路线(§5.4 路线 B)。
4. 词书选哪本作为默认内置?(建议先放 CET-6 + GRE 两本,用户可另导入。)
5. 全局热键库选型(`keyboard` 库需管理员权限的问题)—— M2 时验证,不行就只留托盘图标唤起。

# WordGap

**AI agent 等待间隙的背单词悬浮窗** — 当 Claude Code / Codex 在跑任务时,单词卡自动弹出接着上次的进度背;agent 跑完(或等你确认权限)时提醒并自动收起。进度全局持久,与任何会话无关。

> **EN TL;DR** — A tiny always-on-top vocabulary flashcard window that pops up automatically while your AI coding agent (Claude Code / Codex / pi / dsh / WorkBuddy) is running, and softly closes when the agent finishes or needs your attention. Progress is a single persistent cursor, independent of any agent session. Windows-only for now. MIT licensed.

## 为什么

用 AI coding agent 的人每天都在等:提交任务 → 盯着终端滚动 → 切出去刷手机 → 忘了切回来。WordGap 把这些 30 秒~5 分钟的碎片时间变成背单词时间,而且**任务一结束立刻叫你回去干活**。

## 功能

- **自动生命周期**:提交任务约 18 秒后弹出(快任务不打扰);agent 完成/等确认时横幅提醒,拼完当前词自动收起
- **断点续背**:一本词书一个全局游标,换对话、换 agent、重启机器都接着背;顺序/乱序(固定种子)双模式,切换不丢进度
- **多 agent**:Claude Code(官方 hooks)、Codex(零配置日志监听)、pi / dsh / WorkBuddy(适配模板见 `wordgap/adapters/`)
- **会话面板**:按 agent 分组显示运行中/已完成,已完成会话一键 `claude --resume` 恢复对话
- **打字模式**:qwerty-learner 式拼写,音标+发音(有道音源,可关),Tab 看答案(看过即记入错词),←→ 浏览前后词
- **错词复习 / 每日目标 / AI 新闻轮播条**(卡兹克 [AIHOT](https://aihot.virxact.com) 公开 API)
- **小细节**:跟随系统或手动切换深浅主题、全局热键手动唤醒(Ctrl+Alt+W,被占自动换)、自动唤醒可关、整窗拖拽、不抢焦点

## 快速开始(Windows)

```bash
git clone https://github.com/ktao732084-arch/wordgap && cd wordgap
pip install -e .
python scripts/fetch_dicts.py        # 下载内置词书(CET6 / GRE,来自 qwerty-learner)
python -m wordgap                    # 启动 daemon + 悬浮窗
```

接入 Claude Code(merge 写入 hooks,自动备份,`--uninstall` 可完全还原):

```bash
python wordgap/adapters/claude_code/install.py
```

Codex 无需任何配置——检测到 `~/.codex/sessions` 即自动通过日志监听接入。其余 agent 见 `wordgap/adapters/` 下各目录说明,或在悬浮窗 ⚙ 设置 → Agent 接入 里一键操作。

## 架构(30 秒版)

```
agent 钩子/日志 ──HTTP──▶ daemon(FastAPI :8765)
                           ├─ 会话状态机 + UI 调度状态机(纯函数 reducer)
                           ├─ SQLite:词书/游标/词记录(唯一持久状态)
                           └─ pywebview 置顶悬浮窗(Shell + Panels 小窗框架)
```

核心不变式:**背单词进度只存在于 SQLite,adapter 和调度永远不碰它**——所以"断点续背"不是功能,是架构的自然结果。完整设计见 [spec.md](spec.md)(设计文档即唯一事实源)。

## 开发

```bash
python -m pytest -q          # 142 个测试,核心逻辑覆盖率 100%
```

工程约束(单文件 ≤500 行、纯函数内核、依赖方向单向等)见 spec.md §7。欢迎 issue / PR。

## 致谢与第三方

- 词库数据来自 [qwerty-learner](https://github.com/RealKai42/qwerty-learner)(通过脚本按需下载,不随本仓库分发)
- AI 新闻数据来自数字生命卡兹克的 [AIHOT](https://aihot.virxact.com) 公开 API(免 key,礼貌轮询)
- 发音音源:有道词典(失败自动降级系统 TTS)

## License

MIT

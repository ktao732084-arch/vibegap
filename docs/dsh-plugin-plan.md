# dsh-vibegap 实施方案 v2(P0,供执行 agent 使用)

> 目标:把 VibeGap 做成**自包含的 dsh 原生插件**——dsh 用户一条命令安装,
> 单词卡出现在 dsh web UI 里,agent 运行时自动弹出、完成时提醒收起。
> 不依赖 Python 桌面端;检测到本机 daemon 时升级为共享进度(Phase 2,可选)。
> 关联 issue:#2。本文档是唯一需求来源。
>
> v2 说明:全部技术断言已由维护者对 deepseek-harness 源码逐条验证(2026-08-27),
> **没有开放调研项**。执行时直接采信;若实机行为与本文冲突,停下来报告而不是自行改道。

## 0. 已验证的平台契约(每条带出处)

### 0.1 会话数据(客户端,本插件的核心信号源)

`SessionSummary`(`packages/client/runtime/src/client/sessions/service.ts:42`):

```ts
interface SessionSummary {
  id: SessionId
  title?: string
  displayTitle: string          // 标题 → 项目名 → id 的兜底链
  cwd?: string
  parentId?: SessionId
  origin?: 'subagent'           // 子 agent 会话标记
  running: boolean              // ← 运行中信号(service.ts:58)
  pendingInteraction?: 'approval' | 'plan-review' | 'question'  // 等待用户输入
  completed?: boolean           // 完成且未被打开(侧栏绿色提醒),absent = false
  blank: boolean
  updatedAt: number
}
```

`SessionListState`(同文件 :80):`{ ids: SessionId[], byId: Record<SessionId, SessionSummary>, current, phase, ... }`。

组件在 root 域槽位挂载时,框架把标准 props 注入进来,其中 `useSessions` 是
标准 hook(参考实现 dsh-web-attention-badge 的用法:`var state = props.useSessions(identity)`,
然后遍历 `state.ids` / `state.byId[id]`)。

派生规则:
- `anyRunning = state.ids.some(id => state.byId[id].running)`
- 横幅触发:某会话从 running 翻到 `completed === true` 或出现 `pendingInteraction`;
  **忽略 `origin === 'subagent'` 的行**(子 agent 完成不该打扰,父会话自会翻转)。

### 0.2 槽位

`shell.overlay`(`packages/client/ui-layout/src/client/index.ts:73-83`,官方注释原文要点):
frame 级悬浮层,`kind: 'list'`(**加行不替换**)、`scope: 'root'`;
**层本身点击穿透,条目自行 opt-in pointer-events**——即卡片根元素要自己设
`pointer-events: auto`,隐藏时不设,天然不挡 dsh。

注册方式(照抄 attention-badge `lib/client.js:64-75`):

```js
var inject = ["slots"];
function apply(ctx) {
  ctx.slots.inject("shell.overlay", () =>
    ctx.slots.register({ name: "shell.overlay", id: "vibegap", order: 90000 }, VibegapCard),
  );
}
```

### 0.3 打包与加载(免构建)

- `lib/client.js` 是手写 ModuleLoader bundle,外壳格式(`packages/client/tsdown.client.ts:562`):
  `window.__ModuleLoader__.load({ id: "dsh-vibegap", factory: (require) => { ... } })`,
  **id 必须等于包名**。
- `require()` 可用模块 = 基线 externals(`packages/client/web/src/platform.ts:8-17`):
  `react`、`react/jsx-runtime`、`react-dom`、`react-dom/client`、`@deepseek-ai/cordis`、
  `@deepseek-ai/dsh-client-ui-slots`、`@deepseek-ai/dsh-client-ui-primitives`、
  `@deepseek-ai/dsh-client-runtime/client`(注意:runtime **必须用 /client 子路径**,
  裸包名不在 loader 表里——runtime README "Known Limitations" 明确警告)。
- package.json 关键字段(照抄 attention-badge):
  `"exports": { ".": "./lib/index.js", "./client": "./lib/client.js", "./package.json": "./package.json" }`,
  `"dsh": { "bundle": { "patch": "./cordis.patch.yml" }, "client": { "platform": "web", "inject": ["@deepseek-ai/dsh-client-runtime"] } }`。
- cordis.patch.yml 已在仓库里,格式勿动。

### 0.4 持久化(官方机制,不要手写 localStorage)

`createSnapshotStore<T>(init, { persist: { name } })`
(`packages/client/runtime/src/client/contract/store.ts:86`,从
`@deepseek-ai/dsh-client-runtime/client` 导出,index.ts:70):
localStorage 整值 JSON 持久化,**配额超限/隐私模式只静默关闭持久化,绝不坏 store**,
非浏览器环境自动跳过。进度、偏好全部用它,persist name 用
`vibegap.progress` / `vibegap.prefs`。

### 0.5 视觉

- 组件库:`@deepseek-ai/dsh-client-ui-primitives` 导出 `Button`、`Pill`、`Input`、
  `Modal`、`Tooltip`、`Toast`、`StateDot`、`HoverCard` 等——按钮/输入优先用它,
  与宿主视觉一致。
- 颜色:dsh 主题走 `--dsw-alias-*` CSS 变量(如 `--dsw-alias-label-primary`、
  `--dsw-alias-interactive-bg-hover`、`--dsw-alias-border-l`),卡片配色引用这些变量,
  自动跟随宿主深浅主题;自有 class 一律 `vg-` 前缀,样式用一个注入的 <style> 标签。
- **已确认整个 web 包无 Content-Security-Policy**——外部词库下载(GitHub raw)与
  有道发音(Audio)不会被挡。

### 0.6 服务端(已实现,不改)

`lib/index.js` 事件桥已按 `ctx.on('agent/status', {global:true})` 契约写好
(`packages/core/agent/src/runtime-types.ts:44-50`,AgentStatus = 'idle'|'running'),
Phase 1 保持原样——它给装了桌面版的用户提供双端联动,没装的毫无感知。

## 1. 范围

### Phase 1(本次交付):自包含单词卡

- `lib/client.js`:React 单词卡挂 `shell.overlay`(§0.2),右下角固定定位
- 词库:卡片首次出现且无词库时显示"下载词库(CET6,约 0.5MB)"按钮,
  用户点击后从 `https://raw.githubusercontent.com/RealKai42/qwerty-learner/master/public/dicts/CET6_T.json`
  下载,存入 §0.4 的 store;失败可重试。**禁止把词库文件打进包**(GPL vs MIT)
- 进度:`{ mode, seed, cursor }` 存 store;乱序 = mulberry32 + Fisher-Yates
  固定种子洗牌(自成体系,不要求与桌面版顺序一致)
- 生命周期(常量置顶可调,数据源 §0.1):
  - `anyRunning` 持续 18s → 卡片浮现;18s 内翻回 false → 静默取消(防闪弹,最高优先级规则)
  - 根会话翻到 completed / 出现 pendingInteraction → 顶部横幅
    "会话已完成 · 拼完当前词后收起" / "会话等待确认 · 拼完当前词后收起";
    拼完当前词后若 `anyRunning` 仍真 → 清横幅继续背,否则 2s 后隐藏
  - Esc 或点 ✕ 隐藏,抑制到下一次 anyRunning 从 false→true
- 打字交互(从 `vibegap/ui/web/panels/word_card.js` 移植逻辑,重写为 React,
  只用 useState/useEffect/createElement):字母格 + 焦点门控闪烁光标、敲对亮字母、
  敲错抖动清空计 typo、Tab 开关答案(看过即记 fail;开始拼写答案自动消失)、
  完整拼对 pass 进游标。**键盘监听只在卡片可见且获得焦点时挂 document**,
  卸载/隐藏必须移除,绝不能吃掉 dsh 的快捷键
- 发音:有道 `dictvoice?audio=<word>&type=2` Audio,新词自动读(store 开关,默认开),失败静默

### Phase 2(可选,时间允许再做):daemon 共享进度

- Python 侧:daemon 新增 `/panel/next-word`、`/panel/commit`、`/panel/progress`、
  `/panel/state`,CORS 仅放行 `http(s)://localhost:*` 与 `127.0.0.1:*` Origin;
  现有 `_reject_browser` 防护的端点一律不动
- 客户端启动探测 `/panel/state`(1s 超时):通 → 词与游标走 daemon(与桌面窗共享),
  断 → 回落自包含;运行中断线平滑降级不崩卡片

### 明确不做

复习/每日目标/新闻条/主题切换按钮(桌面版专属);设置界面;构建工具链
(webpack/tsc 一律不引入,`lib/client.js` 纯手写);不改 harness 任何行为;
不动用户 dsh 配置。

## 2. 文件清单与约束

```
vibegap/adapters/dsh/plugin/
├── package.json        # 补 "./client" export 与 dsh.client(§0.3)
├── cordis.patch.yml    # 勿动
├── lib/
│   ├── index.js        # 勿动(事件桥)
│   └── client.js       # 新增,本次主要工作量,≤800 行(专项上限:平台单入口
│                       #   bundle 无法 require 相对文件拆分;内部用分节注释组织)
└── README.md           # 新增:安装/开发说明,附 qwerty-learner attribution
```

工程红线:所有外部交互(fetch/Audio)包 try/catch 且 `AbortSignal.timeout(...)`,
任何异常只影响卡片自身渲染,不冒泡到宿主;文案不用 emoji、不用拟人化语气;
遵守仓库 spec.md §7 通用约束。

## 3. 本地验证(执行者必须走完)

1. 按 https://deepseekdocs.com 安装 dsh 并启动 `dsh web`
2. `dsh plugin --profile web add link:<仓库绝对路径>/vibegap/adapters/dsh/plugin`
3. 验收清单:
   - [ ] dsh web 启动无控制台报错;卡片隐藏时页面点击完全不受影响(穿透验证)
   - [ ] 发起会话任务,约 18s 后卡片浮现;10s 内完成的任务全程无卡片
   - [ ] 打字全流程:亮字母/抖动/Tab 开关/光标只在聚焦时显示/发音
   - [ ] 会话完成 → 横幅 → 拼完当前词 → 收起;另有会话运行时走"继续背"分支
   - [ ] 子 agent(origin='subagent')完成不触发横幅
   - [ ] Esc 隐藏后同批会话不再唤起;新任务重新计时
   - [ ] 刷新页面进度不丢;隐私模式下功能正常(仅不持久)
   - [ ] dsh 快捷键(输入框打字等)不被卡片吃掉
   - [ ] `dsh plugin --profile web remove dsh-vibegap` 干净卸载
4. 桌面 daemon 同时运行时:事件桥照常,桌面悬浮窗不受影响

## 4. 交付

一次提交:`feat: dsh-vibegap self-contained word card plugin (#2)`。
不发布、不建新仓库、不提 awesome PR(发布三件套由维护者执行)。
若实机与本文契约不符(字段名、槽位行为),**停下报告差异**,不要自行绕路。

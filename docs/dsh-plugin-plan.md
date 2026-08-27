# dsh-vibegap 实施方案(P0,供执行 agent 使用)

> 目标:把 VibeGap 做成**自包含的 dsh 原生插件**——dsh 用户一条命令安装,
> 单词卡出现在 dsh web UI 里,agent 运行时自动弹出、完成时提醒收起。
> 不依赖 Python 桌面端;检测到本机 daemon 时升级为共享进度(Phase 2,可选)。
> 关联 issue:#2。本文档是唯一需求来源,与 spec.md §9.1 P0 对应。

## 0. 已完成的调研(直接采信,不要重新调研)

以下结论均已对 deepseek-harness 源码验证(2026-08-26),出处标注:

1. **服务端事件契约**:`ctx.on('agent/status', ({agent, status}) => ...)`;
   `status: 'idle' | 'running'`,每次翻转必发;`{global: true}` 监听全部 agent;
   `agent.session.id` 为会话 id。
   出处:`packages/core/agent/src/runtime-types.ts`(AgentStatus 定义与 emit 注释)。
2. **浏览器半边免构建**:参考 [dsh-web-attention-badge](https://github.com/Luaphes/dsh-web-attention-badge)
   的 `lib/client.js`——手写 ModuleLoader bundle:
   `window.__ModuleLoader__.load({ id, factory: (require) => {...} })`,
   `require("react")` / `require("react/jsx-runtime")` 可用;
   导出 `exports.apply` + `exports.inject = ["slots"]`;
   `ctx.slots.inject("shell.overlay", () => ctx.slots.register({name:"shell.overlay", id, order}, Component))`。
3. **会话感知(客户端)**:组件在 root scope 经 GlobalStandardProps 拿 `useSessions` store;
   行(SessionSummary)已确认字段:`pendingInteraction`('approval'|'plan-review'|'question')、
   `completed`;遍历方式 `state.ids` / `state.byId[id]`。
   **"运行中"的字段名未确认**——执行时在 dsh 源码 `packages/web` 搜 SessionSummary
   定义确认(或运行时 console.log 一次 store),这是本方案唯一需要补的调研。
4. **package.json 关键字段**(照抄 attention-badge 模式):
   `"main": "lib/index.js"`,`"exports": {".": ..., "./client": "./lib/client.js"}`,
   `"dsh": {"bundle": {"patch": "./cordis.patch.yml"}, "client": {"platform": "web", "inject": ["@deepseek-ai/dsh-client-runtime"]}}`。
5. **cordis.patch.yml 格式**(已按实物校正):
   ```yaml
   - insert:
       - id: vibegap
         name: 'dsh-vibegap'
   ```
6. **安装/调试命令**:`dsh plugin --profile web add link:<绝对路径>/plugin`(本地开发)、
   `add "github:owner/repo#ref"`(发布后)、`update` / `remove` 同理。

现有骨架在 `vibegap/adapters/dsh/plugin/`(package.json / cordis.patch.yml / lib/index.js
事件桥已按上述契约写好),在其上扩展,不要推倒。

## 1. 范围

### Phase 1(本次交付):自包含单词卡

- 客户端 `lib/client.js`:React 单词卡组件,挂 `shell.overlay` 槽位
- 词库:首次使用时从 qwerty-learner GitHub raw 下载 CET6(约 470KB),
  缓存进 localStorage;**禁止把词库文件打进包里**(GPL 词库 vs MIT 包,许可冲突)
- 进度:localStorage,键 `vibegap.progress`,值 `{book, mode, seed, cursor}`;
  乱序 = 固定种子洗牌(与桌面版同算法:等价 Python `random.Random(seed).shuffle`
  不可移植,直接用简单的 mulberry32 + Fisher-Yates,种子存进度里,自成体系即可)
- 生命周期(镜像桌面版调度器,常量置顶可调):
  - 任一会话运行中持续 18s → 卡片浮现(右下角固定位,不遮 dsh 主操作区)
  - 运行中会话变 completed / 出现 pendingInteraction → 卡片顶部横幅
    "会话已完成 · 拼完当前词后收起" / "会话等待确认 · 拼完当前词后收起",
    拼完当前词 2s 后自动隐藏;若仍有其他会话运行中,改为清横幅继续背
  - 任务在 18s 延迟内就结束 → 静默取消,零打扰(防闪弹,最重要的体验规则)
  - Esc 或点 ✕ 隐藏,并抑制到下一次"从无运行到有运行"的翻转
- 打字交互(从 `vibegap/ui/web/panels/word_card.js` 移植逻辑,重写为 React):
  字母格 + 闪烁光标、敲对亮字母、敲错抖动清空计 typo、Tab 开关答案
  (看过即记 fail,开始拼写答案自动消失)、完整拼对记 pass 进游标
- 发音:有道 `https://dict.youdao.com/dictvoice?audio=<word>&type=2` 的 Audio 播放,
  新词自动读(localStorage 开关,默认开),失败静默
- 服务端 `lib/index.js`:保持现有事件桥(POST 本机 daemon,1s 超时静默失败)——
  它让装了桌面版的用户获得双端联动,没装的毫无感知

### Phase 2(可选,时间允许再做):daemon 共享进度

- Python 侧:daemon 新增 `/panel/next-word`、`/panel/commit`、`/panel/progress`、
  `/panel/state` 四个端点,**CORS 仅放行 localhost/127.0.0.1 任意端口的 Origin**
  (现有 `_reject_browser` 对 /event、/hook、/toggle 的防护保持原样不动)
- 客户端启动时探测 `/panel/state`:通 → 用 daemon 的词库与游标(与桌面窗共享进度),
  断 → 回落自包含模式;运行中断线要平滑降级不崩卡片

### 明确不做

- 不做复习/每日目标/新闻条/主题切换(桌面版专属,插件保持最小)
- 不做设置界面(常量置顶 + localStorage 开关足够)
- 不做构建工具链(webpack/tsc 一律不引入,纯手写 CJS)
- 不改 deepseek-harness 任何行为;不动用户的 dsh 配置文件

## 2. 文件清单

```
vibegap/adapters/dsh/plugin/
├── package.json        # 已有,补 "./client" export 与 dsh.client 声明
├── cordis.patch.yml    # 已有,格式勿动
├── lib/
│   ├── index.js        # 已有(事件桥),Phase 1 不改
│   └── client.js       # 新增:ModuleLoader bundle,本次主要工作量
└── README.md           # 新增:安装/开发/发布说明(英文为主,附中文)
```

约束:client.js 单文件 ≤500 行(spec §7.1);所有 CSS 内联注入且类名前缀 `vg-`
防止污染 dsh 页面;卡片隐藏时容器 `pointer-events: none`,绝不挡 dsh 的点击。

## 3. 实现要点与坑

1. **绝不破坏宿主**:所有外部交互(词库下载、daemon 探测、Audio)包 try/catch,
   fetch 一律 `AbortSignal.timeout(...)`;任何异常只影响卡片自身渲染,
   不允许冒泡到 dsh(参考 attention-badge 的防御姿态)。
2. **localStorage 容量**:CET6 词库约 470KB,localStorage 限 5MB,可行;
   写入失败(隐私模式等)降级为内存态 + 卡片上提示"进度将不被保存"。
3. **词库下载 UI**:卡片首次出现时若无词库,显示"下载词库(CET6,约 0.5MB)"
   按钮由用户主动点击(不要静默下载),失败可重试。
4. **文案红线**:所有用户可见文案不用 emoji、不用拟人化语气(维护者的硬性要求);
   横幅文案照抄本方案 §1 中的措辞。
5. **`useSessions` 的 running 字段**:见 §0.3,确认后在 client.js 顶部写一行注释
   标明出处(文件+行),这是本方案要求的唯一新调研。
6. **防闪弹计时**:延迟计时基于"从无运行到有运行"的翻转时刻,用 `Date.now()`
   即可(浏览器端无注入时钟约束);翻转回无运行时清计时器。
7. **对 React 版本零假设**:只用 `useState`/`useEffect`/`createElement`
   (attention-badge 同款),不用新特性。

## 4. 本地验证步骤(执行者必须走完)

1. 按 https://deepseekdocs.com 安装 dsh(npm 全局或官方推荐方式),启动 `dsh web`
2. `dsh plugin --profile web add link:<仓库绝对路径>/vibegap/adapters/dsh/plugin`
3. 验收清单:
   - [ ] 安装后 dsh web 正常启动,无控制台报错(卡片代码异常不冒泡)
   - [ ] 发起一个会话任务,约 18s 后卡片浮现;10s 内完成的任务全程无卡片
   - [ ] 打字全流程:亮字母/抖动/Tab 开关/光标/发音
   - [ ] 会话完成 → 横幅 → 拼完当前词 → 2s 后收起;多会话时"仍在运行"分支正确
   - [ ] Esc 隐藏后,同批会话不再唤起;新任务重新计时
   - [ ] 刷新页面进度不丢(localStorage);隐私模式降级提示正确
   - [ ] `dsh plugin --profile web remove dsh-vibegap` 干净卸载
   - [ ] §0.3 的 running 字段出处已注释在 client.js
4. 桌面 daemon 同时运行时(Phase 1):事件桥照常上报,桌面悬浮窗行为不受影响

## 5. 交付物

- client.js + package.json 增量 + plugin README(含一句 attribution:词库来自
  qwerty-learner,按需下载不随包分发)
- 一次提交,commit message:`feat: dsh-vibegap self-contained word card plugin (#2)`
- 不发布、不建新仓库、不提 awesome PR——发布三件套由维护者手动执行

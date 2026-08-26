# dsh (DeepSeek Harness) 接入

两条路线,plugin/ 目录是路线 B 的可安装骨架。

## 路线 A:hook bridge(零代码)

dsh 官方 bridge 可直接运行 Claude-Code 格式钩子。若 bridge 读用户的
~/.claude/settings.json,则已装的 wordgap 钩子天然生效(agent 显示为 claude-code);
若 bridge 有独立配置路径,用:

```bash
python ../claude_code/install.py --settings <dsh hooks 配置路径> --agent dsh
```

## 路线 B:原生插件 dsh-wordgap(plugin/)

Cordis 服务端插件,监听 turn 生命周期 → POST 本机 WordGap daemon。纯 CJS 免构建。

安装(本地开发):

```bash
dsh plugin --profile web add link:<绝对路径>/plugin
```

安装(发布后):

```bash
dsh plugin --profile web add "github:<owner>/dsh-wordgap#main"
```

## 事件契约(已对 dsh 源码验证,2026-08-26)

- `ctx.on('agent/status', ({agent, status}) => ...)`,`status: 'idle' | 'running'`,
  每次状态翻转必发;`{global: true}` 监听全部 agent。
  出处:`packages/core/agent/src/runtime-types.ts`。
- `agent.session.id` 为会话 id;`agent.status` 镜像当前状态。
- cordis.patch.yml 格式已按 dsh-web-attention-badge 实物校正(insert 列表)。
- 唯一待装机确认:AgentOptions 里 cwd 的字段名(代码已做 cwd/workspace 双名兼容)。

## UI 形态(形态 B)参考路径

dsh-web-attention-badge 证明了浏览器半边可以**免构建**:`dsh.client` 声明 +
手写 ModuleLoader bundle(`window.__ModuleLoader__.load`),`inject: ["slots"]`,
`ctx.slots.register({name: "shell.overlay", ...}, Component)` 即挂进 web UI;
组件经 GlobalStandardProps 拿 `useSessions` store(`pendingInteraction` /
`completed` 字段)。WordGap 面板可按此模式做 React 单词卡,数据走本机 daemon
(需给 daemon 加 localhost 限定的 CORS 面板端点)。

## 发布到生态(可选,学习类目前是空白)

GitHub 建仓 `dsh-wordgap` + 打 `dsh-plugin` topic + 按 awesome-deepseek-harness
的 contributing.md 提 PR 收录。

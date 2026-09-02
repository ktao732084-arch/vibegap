# dsh-vibegap

VibeGap 的 DeepSeek Harness 原生插件。Agent 持续运行 18 秒后，dsh web
右下角会出现拼写单词卡；会话完成或等待确认时，完成当前单词后自动收起或继续。
插件可独立运行，不要求安装 VibeGap Python 桌面端。
如果本机 VibeGap Core 正在运行，插件会自动改用桌面端的当前词书和进度游标；
Core 在页面打开后才由另一个 Agent 拉起也能自动接入。为避免两张卡重复出现，
共享模式下页内卡不自动弹出，但仍可用 `Ctrl+Alt+V` 手动呼出。运行中断线时
保留当前词并自动重连，不会误跳到首次下载界面。

## 安装

从 npm 安装：

```bash
dsh plugin --profile web add dsh-vibegap
dsh web
```

也可以从发布镜像仓库
[`dsh-vibegap`](https://github.com/ktao732084-arch/dsh-vibegap) 安装：

```bash
dsh plugin --profile web add "github:ktao732084-arch/dsh-vibegap#main"
dsh web
```

本地开发使用 link 安装：

```bash
dsh plugin --profile web add link:<仓库绝对路径>/vibegap/adapters/dsh/plugin
dsh web
```

> 本目录是开发主场;发布走 dsh-vibegap 镜像仓库(改动合入后同步拷贝过去打 tag)。

卸载：

```bash
dsh plugin --profile web remove dsh-vibegap
```

首次弹出单词卡时，点击“下载词库”获取 CET6 词库。词库、乱序种子、游标和
自动发音偏好通过 dsh 官方 snapshot store 保存在当前浏览器中。无痕模式或浏览器
拒绝持久化时，卡片仍可使用，但刷新后进度可能丢失。

本机 Core 可用时，单词和进度改由 `http://127.0.0.1:8765/panel/*` 提供，
插件每 5 秒低频探测一次，且仅允许来自 `localhost` 或 `127.0.0.1` 的
HTTP(S) 浏览器 Origin。DSH 单独使用时不会因此启动 Python/Core 进程。
共享模式目前只发现默认端口 `8765`；若桌面端修改了 `daemon_port`，DSH 会保持
独立本地模式。

## 使用

- 点击卡片后直接拼写；正确字母会逐个点亮。
- 输入错误会清空当前拼写并计数。
- `Tab` 显示或隐藏答案；看过答案后，本词按 fail 完成并前进。
- `Esc` 或右上角 `×` 隐藏卡片；同一批运行中的会话不会再次弹出。
- `Ctrl+Alt+V` 手动呼出或隐藏卡片（dsh 标签页处于前台时有效，不受 18 秒规则限制）。
- “发音”可手动播放美式发音，“自动发音”可随时开关。

## 开发

浏览器端是手写的 `lib/client.js` ModuleLoader bundle，不需要 webpack、tsc
或其他构建步骤。修改 bundle 后刷新页面；修改 `package.json` 或
`cordis.patch.yml` 后重启 `dsh web`。

纯逻辑与 manifest 兼容性测试：

```bash
npm test
```

服务端 `lib/index.js` 会在本机 VibeGap daemon 存在时继续上报 agent 生命周期；
连接失败会静默降级，不影响 dsh。

## 词库来源与许可

默认 CET6 数据在用户点击后从
[qwerty-learner](https://github.com/RealKai42/qwerty-learner) 下载。该项目使用
GPL-3.0 许可证；词库不会打包进本 MIT 插件。请同时遵守上游项目及词库数据来源的
许可条款。

插件代码使用 MIT 许可证。

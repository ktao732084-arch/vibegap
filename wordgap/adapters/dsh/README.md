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

## 装机后待验证(共 3 处,均已在代码中标注 TODO)

1. turn 级事件名:教程只确认了 `session/created`;`turn/start`、`turn/end`、
   `session/completed` 是按命名惯例的推断,装机开 debug 日志校准 lib/index.js 三行。
2. 事件回调参数里 session id / cwd 的字段名(`sid()`/`dir()` 两个取值函数已做多名兼容)。
3. cordis.patch.yml 的确切格式(参考 dsh-web-attention-badge / turtle-ui 实现)。

## 发布到生态(可选,学习类目前是空白)

GitHub 建仓 `dsh-wordgap` + 打 `dsh-plugin` topic + 按 awesome-deepseek-harness
的 contributing.md 提 PR 收录。

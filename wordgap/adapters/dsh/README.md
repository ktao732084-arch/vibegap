# dsh (DeepSeek Harness) 接入说明

dsh 官方提供 Claude Code hook bridge,可直接运行 Claude-Code 格式的 hooks 配置。
因此 dsh 不需要专用适配代码——复用 claude_code 安装器,把钩子写进 dsh 读取的
settings 文件即可(agent 名上报为 dsh,以便前端区分):

```bash
python ../claude_code/install.py --settings <dsh 的 hooks 配置路径> --agent dsh
```

待实测(本机未安装 dsh,spec 开放问题 #3b):

1. dsh hook bridge 读取的配置文件实际路径;
2. 是否透传 UserPromptSubmit / Stop / Notification 三个事件与 session_id 字段;
3. 若 bridge 直接运行用户的 ~/.claude/settings.json,则 wordgap 钩子已天然生效,
   只是 agent 会显示为 claude-code——届时可改走原生 dsh 插件(pre-step / turn-end
   事件,Cordis 框架)按 dsh 名义上报。

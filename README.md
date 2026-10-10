# WeJot Agent Plugin

WeJot 面向 Codex、Claude Code 与 WorkBuddy/CodeBuddy 的公开插件分发仓库。

插件提供问卷研究设计、问卷和 AI 访谈创建与修改、逻辑与专用题型、答卷数据获取、数据清洗、统计分析和文本分析等 Skills，并通过 WeJot 远程 MCP 服务完成账号授权与业务操作。

## 仓库内容

```text
.agents/plugins/marketplace.json              Codex marketplace
plugins/wejot-agent/                          Codex 插件包
.claude-plugin/marketplace.json               Claude Code marketplace
claude-code/plugins/wejot-agent/              Claude Code 插件包
.codebuddy-plugin/marketplace.json            WorkBuddy marketplace
workbuddy/plugins/wejot-agent/                WorkBuddy 普通插件包
workbuddy/connectors/wejot/                   WorkBuddy Connector 提交包
```

## 安全

不要在 Issue、日志或提交中粘贴访问令牌、OAuth 授权码、用户数据或问卷制品。安全问题请参阅 [SECURITY.md](./SECURITY.md)。

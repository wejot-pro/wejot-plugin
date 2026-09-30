# WeJot Agent Plugin

WeJot 面向 Codex 与 WorkBuddy/CodeBuddy 的公开插件分发仓库。

插件提供问卷研究设计、问卷和 AI 访谈创建与修改、逻辑与专用题型、答卷数据获取、数据清洗、统计分析和文本分析等 Skills，并通过 WeJot 远程 MCP 服务完成账号授权与业务操作。

## 仓库内容

```text
.agents/plugins/marketplace.json              Codex marketplace
plugins/wejot-agent/                          Codex 插件包
.codebuddy-plugin/marketplace.json            WorkBuddy marketplace
workbuddy/plugins/wejot-agent/                WorkBuddy 普通插件包
workbuddy/connectors/wejot/                   WorkBuddy Connector 提交包
```

## Codex 安装

```sh
codex plugin marketplace add https://github.com/wejot-pro/wejot-plugin.git
```

随后从该 marketplace 安装 `wejot-agent`，并按宿主提示完成 WeJot OAuth 登录。

## WorkBuddy / CodeBuddy 安装

在 WorkBuddy/CodeBuddy 中添加 marketplace：

```text
/plugin marketplace add https://github.com/wejot-pro/wejot-plugin.git
/plugin install wejot-agent@wejot-agent-plugins
/reload-plugins
```

安装后按宿主提示连接 WeJot 账号。

## 当前环境

当前公开快照连接 WeJot 公司测试环境：

```text
https://wejot-backend-user-test.xiaotunqifu.com/mcp
```

它不是正式生产入口。测试账号、可用范围和数据处理要求由 WeJot 团队另行管理。

## 安全

不要在 Issue、日志或提交中粘贴访问令牌、OAuth 授权码、用户数据或问卷制品。安全问题请参阅 [SECURITY.md](./SECURITY.md)。

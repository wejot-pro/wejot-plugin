# Changelog

## Unreleased

- **公开测试环境入口 (WorkBuddy 0.1.5 / Codex 0.1.4)**：两端 MCP URL 指向 WeJot 公司测试环境；Codex 不预置产品 Sa-Token header，WorkBuddy 保持顶层 `mcpServers` 格式与 OAuth 引导声明。
- **Bundle submit (0.1.2)**：`validateSurveyArtifacts` 删除；新增 `prepareSubmitBundleUpload`；`submitSurveyArtifacts` 改为 bundle refs；staging 路径 `survey/{code}/mcp/staging/{sha256}.zip`；移除 `client_request_id`；prepare 结构化 `version_conflict`；新会话首次 submit 不再 require surveyId。
- 发布 Codex 与 WorkBuddy/CodeBuddy 插件包及 WorkBuddy Connector 提交包。

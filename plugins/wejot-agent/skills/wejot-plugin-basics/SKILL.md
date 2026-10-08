---
name: wejot-plugin-basics
description: Establish or recover the WeJot plugin and OAuth connection in Codex before using the shared WeJot authoring lifecycle.
---

# WeJot in Codex

Use this skill when WeJot tools are missing, the plugin was just installed or updated, or Codex reports that the WeJot MCP server requires authentication.

## Establish the connection

1. Check whether the installed WeJot plugin exposes its MCP tools in the current chat.
2. If the plugin was just installed or updated but its Skills or tools are not available, ask the user to start a new chat after the host has finished loading the plugin. Do not imitate missing WeJot tools with shell commands or guessed HTTP requests.
3. When Codex presents the WeJot account connection or OAuth action, ask the user to complete the browser login and consent flow. The user, Codex, and the WeJot authorization server own this interaction; never ask the user to paste an access token, authorization code, cookie, or API key into the chat.
4. After Codex reports that the connection succeeded, verify that WeJot tools are available, then continue with `wejot-authoring-lifecycle` and the task-specific Skill.

## Recover safely

- If authentication is required again, use the host's WeJot connection or MCP login surface. Do not construct an authorization URL or call dynamic client registration manually.
- If the browser flow is cancelled, expired, or denied, stop the protected operation and ask the user to reconnect from Codex.
- If tools remain missing after installation or connection, report whether the missing layer is plugin loading, MCP availability, or authentication. Do not claim that a survey was read or changed.
- Keep OAuth credentials and callback parameters out of prompts, artifacts, logs, and survey files.

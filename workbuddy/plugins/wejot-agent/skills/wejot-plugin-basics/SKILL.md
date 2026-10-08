---
name: wejot-plugin-basics
description: Establish or recover the WeJot normal plugin and its MCP account connection in WorkBuddy before using shared WeJot workflows.
---

# WeJot normal plugin in WorkBuddy

Use this skill when the WeJot normal plugin was installed or updated, its Skills or MCP tools are not visible, or WorkBuddy reports that the bundled WeJot MCP server needs authentication.

## Confirmed host behavior

- The normal plugin is loaded from its plugin package. Its `skills/` directory provides agent guidance and its root `.mcp.json` declares the WeJot MCP server.
- During local plugin development, WorkBuddy supports reloading plugins after package changes. Marketplace installation and account connection still require the user to complete the controls shown by WorkBuddy.
- OAuth credentials belong to WorkBuddy and the WeJot authorization server, not to the Skill or agent conversation.

## Establish the connection

1. Confirm that the WeJot plugin is installed and enabled in WorkBuddy.
2. If this is a local development package and recently changed files are not visible, ask the user to reload plugins or reopen the session using the controls available in that WorkBuddy version.
3. If WorkBuddy marks the bundled WeJot MCP server as requiring authentication, ask the user to open its connection control and complete the browser login and consent flow.
4. Do not claim success until WorkBuddy exposes the WeJot tools. Then continue with `wejot-authoring-lifecycle` and the task-specific Skill.

## Manual interaction boundary

The exact marketplace and connection button labels can vary by WorkBuddy build. Do not invent a button name or claim to have clicked it. Tell the user what state is required—plugin installed, MCP connected, browser authorization completed—and let the user perform any host UI action that the current build requires.

Repository maintainers still need to record the exact current UI path and labels after a real normal-plugin installation and OAuth acceptance run. Until that evidence is added, keep guidance state-based rather than button-based.

If authentication is cancelled, expired, or denied, stop the protected operation and ask the user to reconnect. Never ask the user to paste tokens, cookies, authorization codes, or API keys into the chat.

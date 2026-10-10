---
name: wejot-plugin-basics
description: Establish or recover the WeJot plugin and OAuth connection in Claude Code before using the shared WeJot authoring lifecycle.
---

# WeJot in Claude Code

Use this skill when the WeJot plugin was installed or updated, its Skills or MCP tools are missing, or Claude Code reports that the WeJot MCP server needs authentication.

## Identify the failing layer

- Plugin missing: `wejot-agent@wejot` is not installed or enabled.
- Plugin pending reload: the plugin is installed, but the current session has not loaded its Skills or MCP server.
- MCP needs authentication: `plugin:wejot-agent:wejot` exists but is not connected.
- Tool failure: the MCP server is connected and its tools are visible, but a protected operation returned an application or authorization error.

Do not treat these states as interchangeable and do not imitate missing WeJot tools with guessed HTTP requests or shell commands.

## Establish the connection

1. Confirm that `wejot-agent@wejot` is installed and enabled.
2. If the plugin was just installed or updated and its components are not visible, use Claude Code's plugin reload flow. If the current session still has the old component inventory, start a new session.
3. Check the plugin-provided MCP server `plugin:wejot-agent:wejot`. When Claude Code reports that it needs authentication, use the host's `/mcp` flow or `claude mcp login plugin:wejot-agent:wejot` from an interactive terminal.
4. Ask the user to complete WeJot login and consent in the browser. Never ask the user to paste an access token, authorization code, cookie, API key, or callback URL into the conversation.
5. Continue only after Claude Code reports the server as connected and exposes WeJot tools. Then use `wejot-authoring-lifecycle` and the task-specific Skill.

## Recover safely

- If authorization is cancelled, denied, expired, or revoked, stop the protected operation and ask the user to re-authenticate from Claude Code.
- If dynamic registration, metadata discovery, or the loopback callback fails, report the connection-stage error. Do not construct an authorization URL, register a client manually, or fall back to a static token.
- OAuth refresh and credential storage are owned by Claude Code and the WeJot authorization server. Do not expose, cache, log, or copy those credentials into project files.
- Installation alone does not prove that tools are usable. Verify the connected MCP state and a real protected tool call before claiming success.

The explicit Skill command is `/wejot-agent:wejot-plugin-basics`; other WeJot Skills use the same `/wejot-agent:<skill-name>` namespace.

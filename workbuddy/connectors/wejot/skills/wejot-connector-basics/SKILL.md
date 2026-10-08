---
name: wejot-connector-basics
description: Establish or recover the official WeJot MCP Connector in WorkBuddy, including the host-managed OAuth connection, before using shared WeJot workflows.
---

# WeJot Connector in WorkBuddy

Use this skill when WorkBuddy recommends or installs the WeJot Connector, shows that it needs authentication, or loses its connection.

## Host-managed setup

1. Ask the user to install and connect the WeJot Connector from the WorkBuddy Connector surface when it is not already enabled.
2. WorkBuddy owns the standard MCP OAuth client flow. On an unauthenticated MCP response it discovers OAuth metadata, identifies or registers a public client, uses authorization code with PKCE, opens the browser, exchanges the returned code, and attaches the resulting Bearer token to later MCP requests.
3. The user must complete WeJot login and consent in the browser. Do not request credentials in chat and do not construct or open an authorization URL yourself.
4. Continue only after WorkBuddy reports the Connector as connected and exposes WeJot tools. Then use `wejot-authoring-lifecycle` and the task-specific Skill.

## Recovery and safety

- If authorization is cancelled, denied, or expired, ask the user to reconnect the Connector from WorkBuddy.
- If WorkBuddy reports an invalid callback, registration failure, or metadata failure, report that connection-stage error. Do not fall back to a manually supplied token or private API call.
- Access-token refresh is host-managed. Do not expose, cache, log, or ask the user for OAuth tokens, codes, cookies, or API keys.
- Do not claim that a tool call succeeded merely because the Connector package is installed; tools must be available and the protected request must succeed.

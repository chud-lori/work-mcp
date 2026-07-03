# slack-mcp

A local, read-only MCP server that lets Claude Code read Slack.
It authenticates as YOUR user (user token), so it sees exactly what you can
see — no bot to invite anywhere. It cannot post messages, react, or DM —
read-only by design (the token has no write scopes).

## Tools

- `slack_list_channels` — list channels you're in
- `slack_get_channel_history` — read recent messages from a channel
- `slack_get_thread_replies` — read a thread
- `slack_list_users` / `slack_get_user` — workspace members and profiles
- `slack_get_file` — download a shared file; images are returned viewably
- `slack_search_messages` — search messages across the workspace

## Setup

### 1. Create a Slack app and get a user token

1. Go to https://api.slack.com/apps → **Create New App** → **From scratch**.
2. Name it (e.g. `claude-mcp`) and pick your workspace.
3. Under **OAuth & Permissions → Scopes → User Token Scopes** (NOT Bot Token
   Scopes), add (all read-only):
   - `channels:read`, `channels:history` — public channels
   - `groups:read`, `groups:history` — private channels you're in
   - `users:read` — resolve user IDs to names
   - `search:read` — message search
   - `files:read` — download shared files/images
   - (optional) `im:read`, `im:history`, `mpim:read`, `mpim:history` — your DMs
4. Click **Install to Workspace** and copy the **User OAuth Token** (`xoxp-...`).

### 2. Configure the token

```sh
cd ~/Projects/slack-mcp
cp .env.example .env
# edit .env and paste your token(s)
```

### 3. Install deps and register with Claude Code

```sh
npm install
claude mcp add --scope user slack -- node ~/Projects/slack-mcp/index.js
```

Restart Claude Code and run `/mcp` to verify the `slack` server is connected.

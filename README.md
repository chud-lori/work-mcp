# work-mcp

A portable bundle of MCP servers for use with Claude Code (or any MCP client,
e.g. Codex). Clone the repo, run `./setup.sh`, add your own credentials, and
your agent can read Slack, Google Workspace, and Atlassian.

The two local servers (Slack, Google) are **read-only by design** — their
credentials carry read-only scopes, so they cannot send, write, edit, or
delete. The Atlassian server is **not** read-only: it is Atlassian's hosted MCP,
which also exposes write tools (create/edit issues, comments, Confluence pages).
See [Atlassian](#3-atlassian-jira--confluence) for how to block those. All
servers authenticate as *you* and see only what your account can already see.

## What's inside

| Server | Type | What it does |
|---|---|---|
| `slack-mcp/` | local Node | Read-only Slack: channels, threads, users, files/images, message search |
| `google-workspace-mcp/` | local Python | Read-only Gmail, Drive, Docs, Sheets, Calendar |
| atlassian | remote (`mcp-remote`) | Jira + Confluence via Atlassian's hosted MCP — read **and write**; no code here, `setup.sh` just registers it |

No secrets are committed to this repo. You supply your own tokens/credentials
after cloning (see below), and `.gitignore` keeps them out of git.

## Prerequisites

- `node` / `npm`
- `python3`
- `npx`
- the `claude` CLI (Claude Code) on your `PATH`

## Quick start

```sh
git clone <repo-url> ~/Projects/work-mcp
cd ~/Projects/work-mcp
./setup.sh
```

`setup.sh` is idempotent: it installs dependencies, registers each server with
Claude Code (user scope), and **skips any server that's already registered**, so
re-running it is safe.

After it finishes, add credentials for each server (next section), restart
Claude Code, and run `/mcp` — all three should show as connected.

## Credential setup

Secrets are deliberately **not** in this repo. Set them up once per server.

### 1. Slack

Create a Slack app, grant read-only **user** scopes, install it, and copy the
user token (`xoxp-...`) into `slack-mcp/.env`:

```sh
SLACK_USER_TOKEN=xoxp-your-token-here
```

`setup.sh` creates `slack-mcp/.env` from the example for you. Full scope list
and step-by-step app creation instructions are in
[`slack-mcp/README.md`](slack-mcp/README.md).

### 2. Google Workspace

Create a Google Cloud project, enable the Gmail/Drive/Docs/Sheets/Calendar APIs, create
a **Desktop app** OAuth client with read-only scopes, and download the client
secret JSON:

```sh
mkdir -p ~/.config/google-workspace-mcp
mv ~/Downloads/client_secret_*.json ~/.config/google-workspace-mcp/oauth-client.json
chmod 600 ~/.config/google-workspace-mcp/oauth-client.json
```

On first use the server opens an OAuth browser flow and writes
`~/.config/google-workspace-mcp/token.json` — no manual token step needed.
Detailed Google Cloud Console walkthrough is in
[`google-workspace-mcp/COMMANDS.md`](google-workspace-mcp/COMMANDS.md).

### 3. Atlassian (Jira + Confluence)

Nothing to copy. This is Atlassian's hosted MCP registered via `mcp-remote`;
a browser OAuth prompt appears the first time your agent uses it.

Unlike the local servers, its tools include writes (creating and editing Jira
issues, adding comments, transitions, creating and updating Confluence pages),
and this repo cannot scope them down. Claude Code asks before each MCP tool call
unless you have allowed it; to block the write tools outright, add them to
`permissions.deny` in `~/.claude/settings.json` (run `/mcp` to see the exact
tool names), e.g. `"mcp__atlassian__createJiraIssue"`.

## Using with Codex instead of Claude Code

Each local server can also be wired into Codex's `~/.codex/config.toml`. See
[`google-workspace-mcp/COMMANDS.md`](google-workspace-mcp/COMMANDS.md) for an
example MCP server config block.

## Notes

- Servers register at **user scope**, so they're available across all your
  Claude Code projects on this machine.
- To re-run Google OAuth from scratch, delete
  `~/.config/google-workspace-mcp/token.json` and trigger any Google tool.
- To remove a server: `claude mcp remove <name>` (`slack`,
  `google_workspace_local`, or `atlassian`).

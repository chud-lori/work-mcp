# work-mcp

Portable bundle of my work MCP servers for Claude Code. Clone this repo to a
new machine and run `./setup.sh` to install and register everything.

## What's inside

| Server | Type | What it does |
|---|---|---|
| `slack-mcp/` | local Node | Read-only Slack: channels, threads, users, files/images, search |
| `google-workspace-mcp/` | local Python | Read-only Gmail, Drive, Docs, Sheets |
| atlassian | remote (`mcp-remote`) | Jira + Confluence via Atlassian's hosted MCP — no code here, setup.sh just registers it |

## New machine setup

Prereqs: `node`/`npm`, `python3`, and the `claude` CLI installed.

```sh
git clone <repo-url> ~/Projects/work-mcp
cd ~/Projects/work-mcp
./setup.sh
```

Then provide credentials (secrets are deliberately NOT in this bundle):

1. **Slack** — put your user token in `slack-mcp/.env`:
   `SLACK_USER_TOKEN=xoxp-...` (from https://api.slack.com/apps, see
   `slack-mcp/README.md` for the scope list).
2. **Google** — copy `~/.config/codex-google-local-mcp/oauth-client.json`
   and `token.json` from the old machine to the same path on the new one.
   No `token.json`? The server runs the OAuth browser flow on first use.
3. **Atlassian** — nothing to copy; a browser OAuth prompt appears the first
   time Claude uses it.

Restart Claude Code and run `/mcp` — all three should show as connected.

## Notes

- `setup.sh` is idempotent: it skips servers already registered, so running
  it on a machine that already has some of them set up won't disturb them.
- The copies here are snapshots. The originals live at
  `~/Projects/slack-mcp` and `~/repo/google-workspace-mcp` on the source
  machine — re-run the rsync (or just re-copy the dirs) after changing them.

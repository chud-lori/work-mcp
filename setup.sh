#!/usr/bin/env bash
# One-shot installer for all MCP servers in this bundle.
# Safe to re-run: skips servers already registered in Claude Code.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

need() { command -v "$1" >/dev/null || { echo "ERROR: $1 not found — install it first"; exit 1; }; }
need node
need npm
need python3
need npx
need claude

registered() { claude mcp get "$1" >/dev/null 2>&1; }

echo "==> slack-mcp (Node)"
(cd "$DIR/slack-mcp" && npm install --silent)
if [ ! -f "$DIR/slack-mcp/.env" ]; then
  cp "$DIR/slack-mcp/.env.example" "$DIR/slack-mcp/.env"
  echo "    NOTE: put your SLACK_USER_TOKEN in $DIR/slack-mcp/.env"
fi
if registered slack; then
  echo "    already registered, skipping"
else
  claude mcp add --scope user slack -- node "$DIR/slack-mcp/index.js"
fi

echo "==> google-workspace-mcp (Python)"
GW="$DIR/google-workspace-mcp"
# rebuild the venv if missing or broken (e.g. copied from another machine)
if ! "$GW/.venv/bin/python" -c '' >/dev/null 2>&1; then
  rm -rf "$GW/.venv"
  python3 -m venv "$GW/.venv"
fi
"$GW/.venv/bin/pip" install --quiet "$GW"
GCFG="$HOME/.config/google-workspace-mcp"
mkdir -p "$GCFG"
if [ ! -f "$GCFG/oauth-client.json" ]; then
  echo "    NOTE: copy oauth-client.json (and token.json if you have it) into $GCFG/"
  echo "          from the old machine's ~/.config/google-workspace-mcp/"
fi
if registered google_workspace_local; then
  echo "    already registered, skipping"
else
  claude mcp add --scope user google_workspace_local \
    -e GOOGLE_WORKSPACE_CREDENTIALS_FILE="$GCFG/oauth-client.json" \
    -e GOOGLE_WORKSPACE_TOKEN_FILE="$GCFG/token.json" \
    -- "$GW/.venv/bin/google-workspace-mcp"
fi

echo "==> atlassian (remote — Jira + Confluence)"
if registered atlassian; then
  echo "    already registered, skipping"
else
  claude mcp add --scope user atlassian -- npx -y mcp-remote https://mcp.atlassian.com/v1/sse
fi

echo
echo "Done. Remaining manual steps (first run on a new machine):"
echo "  1. Slack token   -> $DIR/slack-mcp/.env"
echo "  2. Google creds  -> $GCFG/ (or delete token.json to re-run OAuth)"
echo "  3. Atlassian     -> browser OAuth prompt appears on first use"
echo "Then restart Claude Code and run /mcp to verify."

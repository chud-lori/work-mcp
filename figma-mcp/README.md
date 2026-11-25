# figma-mcp

Read-only MCP server for Figma. Four tools: find a design file by name, read its
page and frame structure, read its comments, and list the team's projects.

This is a **knowledge-lookup** server, not a design-to-code one. It answers
"which file is the listing-card design, and what did the designer say about it".
If you want the currently selected frame turned into code, that is Figma's own
hosted MCP (`https://mcp.figma.com/mcp`), which needs a Dev or Full seat.

## Tools

| Tool | What it does |
|---|---|
| `figma_list_projects` | Projects in the configured team with a file count each. Also the fastest check that the token and team id work |
| `figma_search_files` | Case-insensitive substring match on file names across the whole team |
| `figma_get_file` | A file's pages and their top-level frames. Takes a file key or any Figma URL |
| `figma_get_comments` | The most recent comments, each with author, node id, and resolved state |

Every call is a `GET`. The server has no code path that writes to Figma.

## Why the team index is cached

The Figma REST API has no file-name search. Finding a file by name means listing
every project in the team, then every file in every project, and matching
client-side. That is 1 + N requests, so the result is cached in process for 15
minutes. `figma_list_projects(refresh=True)` rebuilds it when a file was just
added.

## Setup

1. Create a **scoped** personal access token: Figma, avatar, Settings,
   Security, Personal access tokens, Generate. Give it only:
   - `folders:read` (list projects and their files)
   - `file_content:read` (read a file's structure)
   - `file_comments:read` (read comments)

   An unscoped token can post comments, which would break this server's
   read-only guarantee at the credential level. If the older scope names are
   what your account offers, `projects:read` is the deprecated name for
   `folders:read`; add `teams:read` as well if listing projects returns 403.

2. Find your team id: open the team in Figma and copy the number after `/team/`
   in the URL.

3. Put both in `.env` (created by the repo's `setup.sh` from `.env.example`):

   ```sh
   FIGMA_API_TOKEN=figd_your-token
   FIGMA_TEAM_ID=123456789
   ```

   `chmod 600 .env`. It is gitignored.

4. Restart Claude Code, then `/mcp` should show `figma` connected.

## Tests

```sh
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
```

The venv is installed editable, so an edit to `src/` is live code. A running MCP
process still holds the old module, so reconnect `figma` from `/mcp` after a
change.

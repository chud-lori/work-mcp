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
every folder in the team, then every file in every folder, and matching
client-side. That is 1 + N requests, so the result is cached in process for 15
minutes. `figma_list_projects(refresh=True)` rebuilds it when a file was just
added.

## Team listing may not be available to you

Figma has two APIs for this and a scoped token can easily reach neither.

`GET /v2/teams/{id}/folders` is the current one and takes `folders:read`. It can
still answer `403 You don't seem to have permission to do that`, which is a plan
or team-membership limit, not a scope you can add.

`GET /v1/teams/{id}/projects` is deprecated and takes `files:read` or
`projects:read`. Figma no longer offers either when you mint a scoped token, so
only a legacy unscoped token reaches it.

The server tries v2, falls back to v1, and if both refuse says so in one
sentence naming which of the two refused for which reason. `figma_get_file` and
`figma_get_comments` take a key or URL and do not touch either endpoint, so they
keep working when search does not.

## Setup

1. Create a **scoped** personal access token: Figma, avatar, Settings,
   Security, Personal access tokens, Generate. Give it only:
   - `folders:read` (list projects and their files)
   - `file_content:read` (read a file's structure)
   - `file_comments:read` (read comments)

   An unscoped token can post comments, which would break this server's
   read-only guarantee at the credential level. Add `files:read` or
   `projects:read` too if your account still offers them: they are deprecated
   and usually absent, but they are the only way to reach the team listing when
   the v2 folders API refuses. Tokens expire in 90 days at most.

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

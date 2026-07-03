# Codex Handoff: Google Workspace MCP

This project is a standalone local MCP server outside application repos.

Path:

```bash
/Users/nurchudlori/repo/google-workspace-mcp
```

## Objective

Create a read-only MCP server so Codex can access permitted Google Workspace content:

- Gmail search and message text
- Google Drive files/search
- Google Docs text
- Google Sheets values

Do not add write/delete/update/send/share tools unless explicitly requested later.

## Expected Tools

```text
gmail_search(query, page_size=10, label_ids=None)
gmail_get_message(message_id)
drive_search(query, page_size=10, drive_id=None)
drive_get_file(file_id)
docs_get_text(document_id)
sheets_get_values(spreadsheet_id, range_name="A1:Z1000")
workspace_get_from_url(url)
```

`workspace_get_from_url(url)` detects Docs, Sheets, and Drive file URLs and calls the right reader.

## OAuth Scopes

Keep scopes read-only:

```text
https://www.googleapis.com/auth/gmail.readonly
https://www.googleapis.com/auth/drive.readonly
https://www.googleapis.com/auth/documents.readonly
https://www.googleapis.com/auth/spreadsheets.readonly
```

Never commit:

```text
.env
oauth-client.json
token.json
```

## Setup Commands

The package is installed into the existing pyenv environment `mcp-99`:

```bash
cd /Users/nurchudlori/repo/google-workspace-mcp
/Users/nurchudlori/.pyenv/versions/mcp-99/bin/pip install -e .
```

Do not create a separate local `.venv` unless you intentionally want to change that setup.

## Google Cloud Setup

In Google Cloud Console:

1. Create/select a project.
2. Enable:
   - Gmail API
   - Google Drive API
   - Google Docs API
   - Google Sheets API
3. Configure OAuth consent screen. Prefer internal/company app if available.
4. Create OAuth Client ID with application type `Desktop app`.
5. Download the credentials JSON.
6. Store outside git:

```bash
mkdir -p ~/.config/google-workspace-mcp
mv ~/Downloads/client_secret_*.json ~/.config/google-workspace-mcp/oauth-client.json
chmod 600 ~/.config/google-workspace-mcp/oauth-client.json
```

## Suggested Codex MCP Config

Add this to `/Users/nurchudlori/.codex/config.toml`:

```toml
[mcp_servers.google_workspace_local]
command = "/Users/nurchudlori/.pyenv/versions/mcp-99/bin/google-workspace-mcp"
startup_timeout_sec = 20
tool_timeout_sec = 90
default_tools_approval_mode = "prompt"
enabled = true

[mcp_servers.google_workspace_local.env]
GOOGLE_WORKSPACE_CREDENTIALS_FILE = "/Users/nurchudlori/.config/google-workspace-mcp/oauth-client.json"
GOOGLE_WORKSPACE_TOKEN_FILE = "/Users/nurchudlori/.config/google-workspace-mcp/token.json"
```

Restart Codex after adding the config.

## Security Notes

- Use least privilege and read-only scopes.
- Do not expose all company docs casually; search/read only what is needed.
- Keep OAuth tokens local and out of git.

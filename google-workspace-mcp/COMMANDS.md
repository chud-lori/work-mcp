# Google Workspace MCP Handoff

Goal: standalone read-only MCP server that lets Codex access permitted Gmail, Google Drive, Docs, and Sheets content through your Google account OAuth.

Project path:

```bash
cd /Users/nurchudlori/repo/google-workspace-mcp
```

## 1. Use Existing Environment

```bash
/Users/nurchudlori/.pyenv/versions/mcp-99/bin/pip install -e .
```

This project is installed into the existing pyenv environment `mcp-99`; do not create a separate local `.venv` unless you intentionally want to change that setup.

## 2. Create Google OAuth Credentials

In Google Cloud Console:

1. Create or select a project.
2. Enable these APIs:
   - Gmail API
   - Google Drive API
   - Google Docs API
   - Google Sheets API
3. Configure OAuth consent screen for internal/company use if available.
4. Create OAuth Client ID:
   - Application type: Desktop app
5. Download the client secret JSON.
6. Save it outside git:

```bash
mkdir -p ~/.config/codex-google-local-mcp
mv ~/Downloads/client_secret_*.json ~/.config/codex-google-local-mcp/oauth-client.json
chmod 600 ~/.config/codex-google-local-mcp/oauth-client.json
```

## 3. Configure Env

Use these paths:

```text
GOOGLE_WORKSPACE_CREDENTIALS_FILE=/Users/nurchudlori/.config/codex-google-local-mcp/oauth-client.json
GOOGLE_WORKSPACE_TOKEN_FILE=/Users/nurchudlori/.config/codex-google-local-mcp/token.json
```

## 4. First Auth Run

The first Google API call should open an OAuth browser flow and create `token.json`.

```bash
GOOGLE_WORKSPACE_CREDENTIALS_FILE=/Users/nurchudlori/.config/codex-google-local-mcp/oauth-client.json \
GOOGLE_WORKSPACE_TOKEN_FILE=/Users/nurchudlori/.config/codex-google-local-mcp/token.json \
/Users/nurchudlori/.pyenv/versions/mcp-99/bin/google-workspace-mcp
```

## 5. Add To Codex MCP Config

Add this to `/Users/nurchudlori/.codex/config.toml`:

```toml
[mcp_servers.google_workspace_local]
command = "/Users/nurchudlori/.pyenv/versions/mcp-99/bin/google-workspace-mcp"
startup_timeout_sec = 20
tool_timeout_sec = 90
default_tools_approval_mode = "prompt"
enabled = true

[mcp_servers.google_workspace_local.env]
GOOGLE_WORKSPACE_CREDENTIALS_FILE = "/Users/nurchudlori/.config/codex-google-local-mcp/oauth-client.json"
GOOGLE_WORKSPACE_TOKEN_FILE = "/Users/nurchudlori/.config/codex-google-local-mcp/token.json"
```

Then restart Codex.

## 6. Intended MCP Tools

- `gmail_search(query, page_size=10, label_ids=None)`
- `gmail_get_message(message_id)`
- `drive_search(query, page_size=10, drive_id=None)`
- `drive_get_file(file_id)`
- `docs_get_text(document_id)`
- `sheets_get_values(spreadsheet_id, range_name="A1:Z1000")`
- `workspace_get_from_url(url)` that detects Docs, Sheets, and Drive URLs

## 7. Security Rules

Keep it read-only unless there is an explicit future request.

Use only these OAuth scopes:

```text
https://www.googleapis.com/auth/gmail.readonly
https://www.googleapis.com/auth/drive.readonly
https://www.googleapis.com/auth/documents.readonly
https://www.googleapis.com/auth/spreadsheets.readonly
```

Do not commit:

- `.env`
- `oauth-client.json`
- `token.json`

For company docs, prefer folder/shared-drive restrictions before broad rollout.

# Gmail Progress MCP

Minimal local MCP server for sending Codex progress reports to one fixed Gmail recipient.

## Security model

- The only exposed tool is `send_progress_email`.
- The recipient is fixed to `smartjay1206@gmail.com`.
- The server requests only the Gmail `gmail.send` OAuth scope.
- It does not read mail, create drafts, manage labels, delete messages, or accept arbitrary recipients.
- The OAuth token is stored outside this repository.

## Setup

1. Create a Google Cloud project and enable the Gmail API.
2. Configure the OAuth consent screen.
3. Create an OAuth client ID of type **Desktop app**.
4. Download the JSON file and save it as:

   `~/.config/codex-gmail-progress/client_secret.json`

5. Create the environment and install dependencies:

   ```bash
   cd /workspaces/AREQA/tools/gmail-progress-mcp
   python3 -m venv .venv
   .venv/bin/pip install -e .
   ```

6. Authenticate once:

   ```bash
   .venv/bin/python gmail_progress_mcp.py --auth
   ```

7. Add it to Codex CLI:

   ```bash
   codex mcp add gmail-progress -- /workspaces/AREQA/tools/gmail-progress-mcp/.venv/bin/python /workspaces/AREQA/tools/gmail-progress-mcp/gmail_progress_mcp.py
   ```

8. Verify:

   ```bash
   codex mcp list
   ```

The server intentionally does not ask for an interactive confirmation before sending. Keep Codex's broader approval policy enabled; only this tool is narrowly scoped.

## Manual test

```text
Use the Gmail progress MCP to send a test progress report saying: MCP connection test passed.
```


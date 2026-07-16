"""Fixed-recipient Gmail MCP server for background Codex progress reports."""

from __future__ import annotations

import argparse
import base64
import os
import re
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from mcp.server.fastmcp import FastMCP


RECIPIENT = "smartjay1206@gmail.com"
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
CONFIG_DIR = Path(os.environ.get("CODEX_GMAIL_CONFIG_DIR", "~/.config/codex-gmail-progress")).expanduser()
CLIENT_SECRET_FILE = CONFIG_DIR / "client_secret.json"
TOKEN_FILE = CONFIG_DIR / "token.json"
MAX_BODY_LENGTH = 30_000
SUBJECT_PATTERN = re.compile(r"^\[Codex Progress\] .+")

mcp = FastMCP("gmail-progress")


def _credentials() -> Credentials:
    """Load or create OAuth credentials with send-only scope."""
    CONFIG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    credentials: Credentials | None = None

    if TOKEN_FILE.exists():
        credentials = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    elif not credentials or not credentials.valid:
        if not CLIENT_SECRET_FILE.exists():
            raise RuntimeError(
                f"Missing OAuth client JSON: {CLIENT_SECRET_FILE}. "
                "Download a Desktop app OAuth client JSON from Google Cloud."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
        credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    TOKEN_FILE.write_text(credentials.to_json(), encoding="utf-8")
    TOKEN_FILE.chmod(0o600)
    return credentials


def authenticate() -> None:
    """Complete the one-time OAuth flow without starting the MCP transport."""
    _credentials()
    print(f"Gmail authentication completed; token saved at {TOKEN_FILE}")


def _send_message(subject: str, body: str) -> str:
    credentials = _credentials()
    message = EmailMessage()
    message["To"] = RECIPIENT
    message["Subject"] = subject
    message.set_content(body)
    encoded = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
    result: dict[str, Any] = service.users().messages().send(
        userId="me", body={"raw": encoded}
    ).execute()
    message_id = result.get("id")
    if not message_id:
        raise RuntimeError("Gmail API returned no message id")
    return message_id


@mcp.tool()
def send_progress_email(body: str, subject: str) -> str:
    """Send a Codex progress report to the configured fixed recipient."""
    if not isinstance(body, str) or not body.strip():
        raise ValueError("body must be a non-empty string")
    if len(body) > MAX_BODY_LENGTH:
        raise ValueError(f"body must be at most {MAX_BODY_LENGTH} characters")
    if not isinstance(subject, str) or not SUBJECT_PATTERN.fullmatch(subject.strip()):
        raise ValueError("subject must start with '[Codex Progress] '")
    return f"Progress email sent to {RECIPIENT}; Gmail message id: {_send_message(subject.strip(), body.strip())}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--auth", action="store_true", help="complete one-time Google OAuth")
    args = parser.parse_args()
    if args.auth:
        authenticate()
        return
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()


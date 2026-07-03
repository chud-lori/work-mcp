from __future__ import annotations

import os
import re
import base64
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from mcp.server.fastmcp import FastMCP

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/documents.readonly",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]

mcp = FastMCP("google-workspace")

_DOC_RE = re.compile(r"/document/d/([a-zA-Z0-9_-]+)")
_SHEET_RE = re.compile(r"/spreadsheets/d/([a-zA-Z0-9_-]+)")
_FILE_RE = re.compile(r"/file/d/([a-zA-Z0-9_-]+)")
_OPEN_ID_RE = re.compile(r"[?&]id=([a-zA-Z0-9_-]+)")


def _credentials() -> Credentials:
    credentials_file = os.environ.get("GOOGLE_WORKSPACE_CREDENTIALS_FILE")
    token_file = os.environ.get("GOOGLE_WORKSPACE_TOKEN_FILE")

    if not credentials_file:
        raise RuntimeError("GOOGLE_WORKSPACE_CREDENTIALS_FILE is required")
    if not token_file:
        raise RuntimeError("GOOGLE_WORKSPACE_TOKEN_FILE is required")

    token_path = Path(token_file).expanduser()
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(Path(credentials_file).expanduser()), SCOPES)
        creds = flow.run_local_server(port=0)

    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())
    return creds


def _service(name: str, version: str):
    return build(name, version, credentials=_credentials(), cache_discovery=False)


def _extract_text_from_doc_content(content: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for item in content:
        paragraph = item.get("paragraph")
        if not paragraph:
            continue
        for element in paragraph.get("elements", []):
            text = element.get("textRun", {}).get("content")
            if text:
                parts.append(text)
    return "".join(parts).strip()


def _decode_gmail_body_data(data: str) -> str:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding).decode("utf-8", errors="replace")


def _extract_gmail_text_parts(payload: dict[str, Any]) -> list[str]:
    parts: list[str] = []
    mime_type = payload.get("mimeType")
    body_data = payload.get("body", {}).get("data")
    if body_data and mime_type in {"text/plain", "text/html"}:
        parts.append(_decode_gmail_body_data(body_data))

    for part in payload.get("parts", []):
        parts.extend(_extract_gmail_text_parts(part))
    return parts


def _gmail_headers(payload: dict[str, Any]) -> dict[str, str]:
    wanted = {"From", "To", "Cc", "Bcc", "Subject", "Date"}
    return {
        header.get("name", ""): header.get("value", "")
        for header in payload.get("headers", [])
        if header.get("name") in wanted
    }


def _extract_id_from_url(url: str) -> tuple[str, str] | None:
    parsed_url = urlparse(url)
    host = parsed_url.netloc.lower()
    if host not in {"docs.google.com", "drive.google.com"}:
        return None

    for kind, pattern in (
        ("doc", _DOC_RE),
        ("sheet", _SHEET_RE),
        ("file", _FILE_RE),
        ("file", _OPEN_ID_RE),
    ):
        if kind in {"doc", "sheet"} and host != "docs.google.com":
            continue
        if kind == "file" and host != "drive.google.com":
            continue
        match = pattern.search(url)
        if match:
            return kind, match.group(1)
    return None


@mcp.tool()
def gmail_search(query: str, page_size: int = 10, label_ids: list[str] | None = None) -> dict[str, Any]:
    """Search Gmail messages visible to the authenticated account."""
    service = _service("gmail", "v1")
    result = service.users().messages().list(
        userId="me",
        q=query,
        maxResults=min(max(page_size, 1), 50),
        labelIds=label_ids,
    ).execute()

    messages: list[dict[str, Any]] = []
    for message in result.get("messages", []):
        metadata = service.users().messages().get(
            userId="me",
            id=message["id"],
            format="metadata",
            metadataHeaders=["From", "To", "Subject", "Date"],
        ).execute()
        messages.append(
            {
                "id": metadata.get("id"),
                "thread_id": metadata.get("threadId"),
                "snippet": metadata.get("snippet"),
                "headers": _gmail_headers(metadata.get("payload", {})),
            }
        )

    return {"messages": messages, "next_page_token": result.get("nextPageToken")}


@mcp.tool()
def gmail_get_message(message_id: str) -> dict[str, Any]:
    """Get a Gmail message by id, including readable text parts."""
    service = _service("gmail", "v1")
    message = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    payload = message.get("payload", {})
    return {
        "id": message.get("id"),
        "thread_id": message.get("threadId"),
        "snippet": message.get("snippet"),
        "headers": _gmail_headers(payload),
        "text": "\n".join(part.strip() for part in _extract_gmail_text_parts(payload) if part.strip()),
    }


@mcp.tool()
def drive_search(query: str, page_size: int = 10, drive_id: str | None = None) -> dict[str, Any]:
    """Search Google Drive files visible to the authenticated account."""
    service = _service("drive", "v3")
    params: dict[str, Any] = {
        "q": query,
        "pageSize": min(max(page_size, 1), 50),
        "fields": "files(id,name,mimeType,webViewLink,modifiedTime,owners(displayName,emailAddress))",
        "supportsAllDrives": True,
        "includeItemsFromAllDrives": True,
    }
    if drive_id:
        params.update({"driveId": drive_id, "corpora": "drive"})
    result = service.files().list(**params).execute()
    return {"files": result.get("files", [])}


@mcp.tool()
def drive_get_file(file_id: str) -> dict[str, Any]:
    """Get Google Drive file metadata by file id."""
    service = _service("drive", "v3")
    return service.files().get(
        fileId=file_id,
        fields="id,name,mimeType,webViewLink,modifiedTime,owners(displayName,emailAddress)",
        supportsAllDrives=True,
    ).execute()


@mcp.tool()
def docs_get_text(document_id: str) -> dict[str, Any]:
    """Get plain text from a Google Doc by document id."""
    service = _service("docs", "v1")
    doc = service.documents().get(documentId=document_id).execute()
    text = _extract_text_from_doc_content(doc.get("body", {}).get("content", []))
    return {"document_id": document_id, "title": doc.get("title"), "text": text}


@mcp.tool()
def sheets_get_values(spreadsheet_id: str, range_name: str = "A1:Z1000") -> dict[str, Any]:
    """Get cell values from a Google Sheet range."""
    service = _service("sheets", "v4")
    spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    values = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=range_name).execute()
    return {
        "spreadsheet_id": spreadsheet_id,
        "title": spreadsheet.get("properties", {}).get("title"),
        "range": values.get("range"),
        "values": values.get("values", []),
    }


@mcp.tool()
def workspace_get_from_url(url: str) -> dict[str, Any]:
    """Read supported Google Workspace URLs for Docs, Sheets, or Drive files."""
    parsed = _extract_id_from_url(url)
    if not parsed:
        raise ValueError("Unsupported Google Workspace URL")

    kind, file_id = parsed
    if kind == "doc":
        return {"kind": kind, "data": docs_get_text(file_id)}
    if kind == "sheet":
        return {"kind": kind, "data": sheets_get_values(file_id)}
    return {"kind": kind, "data": drive_get_file(file_id)}


def _event_summary(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": event.get("id"),
        "summary": event.get("summary"),
        "status": event.get("status"),
        "start": event.get("start"),
        "end": event.get("end"),
        "location": event.get("location"),
        "organizer": event.get("organizer"),
        "attendees": [
            {"email": a.get("email"), "responseStatus": a.get("responseStatus")}
            for a in event.get("attendees", [])
        ],
        "hangout_link": event.get("hangoutLink"),
        "html_link": event.get("htmlLink"),
    }


@mcp.tool()
def calendar_list_calendars() -> dict[str, Any]:
    """List calendars visible to the authenticated account."""
    service = _service("calendar", "v3")
    result = service.calendarList().list().execute()
    return {
        "calendars": [
            {"id": c.get("id"), "summary": c.get("summary"), "primary": c.get("primary", False)}
            for c in result.get("items", [])
        ]
    }


@mcp.tool()
def calendar_list_events(
    time_min: str | None = None,
    time_max: str | None = None,
    query: str | None = None,
    calendar_id: str = "primary",
    page_size: int = 10,
) -> dict[str, Any]:
    """List calendar events, expanded and ordered by start time. Times are RFC3339 (e.g. 2026-07-03T00:00:00+07:00); time_min defaults to now."""
    from datetime import datetime, timezone

    service = _service("calendar", "v3")
    params: dict[str, Any] = {
        "calendarId": calendar_id,
        "maxResults": min(max(page_size, 1), 50),
        "singleEvents": True,
        "orderBy": "startTime",
        "timeMin": time_min or datetime.now(timezone.utc).isoformat(),
    }
    if time_max:
        params["timeMax"] = time_max
    if query:
        params["q"] = query
    result = service.events().list(**params).execute()
    return {
        "calendar_id": calendar_id,
        "events": [_event_summary(event) for event in result.get("items", [])],
        "next_page_token": result.get("nextPageToken"),
    }


@mcp.tool()
def calendar_get_event(event_id: str, calendar_id: str = "primary") -> dict[str, Any]:
    """Get a calendar event by id, including description and full attendee list."""
    service = _service("calendar", "v3")
    event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
    detail = _event_summary(event)
    detail["description"] = event.get("description")
    return detail


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

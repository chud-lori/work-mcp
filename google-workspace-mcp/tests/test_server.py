from __future__ import annotations

import unittest
import base64

from google_workspace_mcp import server


class UrlParsingTests(unittest.TestCase):
    def test_extracts_supported_workspace_ids(self) -> None:
        cases = [
            ("https://docs.google.com/document/d/doc_123/edit", ("doc", "doc_123")),
            ("https://docs.google.com/spreadsheets/d/sheet-123/edit#gid=0", ("sheet", "sheet-123")),
            ("https://drive.google.com/file/d/file-123/view", ("file", "file-123")),
            ("https://drive.google.com/open?id=open_123", ("file", "open_123")),
        ]

        for url, expected in cases:
            with self.subTest(url=url):
                self.assertEqual(server._extract_id_from_url(url), expected)

    def test_unsupported_url_returns_none(self) -> None:
        self.assertIsNone(server._extract_id_from_url("https://example.com/document/d/doc_123/edit"))


class TextExtractionTests(unittest.TestCase):
    def test_extracts_doc_paragraph_text(self) -> None:
        content = [
            {
                "paragraph": {
                    "elements": [
                        {"textRun": {"content": "Hello "}},
                        {"textRun": {"content": "world\n"}},
                    ]
                }
            },
            {"sectionBreak": {}},
        ]

        self.assertEqual(server._extract_text_from_doc_content(content), "Hello world")

    def test_extracts_gmail_text_parts(self) -> None:
        data = base64.urlsafe_b64encode(b"Hello from Gmail").decode("ascii").rstrip("=")
        payload = {
            "mimeType": "multipart/alternative",
            "parts": [
                {"mimeType": "text/plain", "body": {"data": data}},
                {"mimeType": "application/pdf", "body": {"data": data}},
            ],
        }

        self.assertEqual(server._extract_gmail_text_parts(payload), ["Hello from Gmail"])

    def test_extracts_gmail_headers(self) -> None:
        payload = {
            "headers": [
                {"name": "From", "value": "sender@example.com"},
                {"name": "Subject", "value": "Test"},
                {"name": "X-Ignored", "value": "ignore me"},
            ]
        }

        self.assertEqual(server._gmail_headers(payload), {"From": "sender@example.com", "Subject": "Test"})

    def test_ignores_empty_doc_elements(self) -> None:
        payload = [
            {
                "paragraph": {
                    "elements": [
                        {"textRun": {"content": "Kept"}},
                        {"textRun": {}},
                    ]
                },
            }
        ]

        self.assertEqual(server._extract_text_from_doc_content(payload), "Kept")


class WorkspaceDispatchTests(unittest.TestCase):
    def test_dispatches_workspace_urls_to_reader(self) -> None:
        calls: list[tuple[str, str]] = []
        originals = {
            "docs_get_text": server.docs_get_text,
            "sheets_get_values": server.sheets_get_values,
            "drive_get_file": server.drive_get_file,
        }

        def fake_docs(file_id: str) -> dict[str, str]:
            calls.append(("doc", file_id))
            return {"id": file_id}

        def fake_sheets(file_id: str) -> dict[str, str]:
            calls.append(("sheet", file_id))
            return {"id": file_id}

        def fake_drive(file_id: str) -> dict[str, str]:
            calls.append(("file", file_id))
            return {"id": file_id}

        try:
            server.docs_get_text = fake_docs
            server.sheets_get_values = fake_sheets
            server.drive_get_file = fake_drive

            self.assertEqual(
                server.workspace_get_from_url("https://docs.google.com/document/d/doc_123/edit"),
                {"kind": "doc", "data": {"id": "doc_123"}},
            )
            self.assertEqual(
                server.workspace_get_from_url("https://docs.google.com/spreadsheets/d/sheet_123/edit"),
                {"kind": "sheet", "data": {"id": "sheet_123"}},
            )
            self.assertEqual(
                server.workspace_get_from_url("https://drive.google.com/file/d/file_123/view"),
                {"kind": "file", "data": {"id": "file_123"}},
            )
        finally:
            server.docs_get_text = originals["docs_get_text"]
            server.sheets_get_values = originals["sheets_get_values"]
            server.drive_get_file = originals["drive_get_file"]

        self.assertEqual(
            calls,
            [
                ("doc", "doc_123"),
                ("sheet", "sheet_123"),
                ("file", "file_123"),
            ],
        )

    def test_rejects_unsupported_urls(self) -> None:
        with self.assertRaises(ValueError):
            server.workspace_get_from_url("https://example.com/not-google")


if __name__ == "__main__":
    unittest.main()

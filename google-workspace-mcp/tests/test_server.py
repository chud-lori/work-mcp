from __future__ import annotations

import os
import unittest
import base64
from unittest import mock

from google_workspace_mcp import server


class _FakeDrive:
    """Minimal stand-in for a Drive service: file_id -> list of parent ids."""

    def __init__(self, parents: dict[str, list[str]]) -> None:
        self._parents = parents
        self.calls = 0

    def files(self):
        return self

    def get(self, fileId: str, fields: str, supportsAllDrives: bool):
        self.calls += 1
        parents = self._parents.get(fileId)
        if parents is None:
            raise RuntimeError(f"not found: {fileId}")
        return mock.Mock(execute=lambda: {"id": fileId, "parents": parents})


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

        def fake_docs(file_id: str, tab_id: str | None = None) -> dict[str, str]:
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


class AllowedFolderTests(unittest.TestCase):
    def test_allowed_folder_ids_parses_and_trims(self) -> None:
        with mock.patch.dict(os.environ, {"GOOGLE_WORKSPACE_ALLOWED_FOLDER_IDS": " a , b ,,c "}):
            self.assertEqual(server._allowed_folder_ids(), {"a", "b", "c"})

    def test_allowed_folder_ids_empty_when_unset(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(server._allowed_folder_ids(), set())

    def test_no_restriction_allows_everything(self) -> None:
        drive = _FakeDrive({})
        self.assertTrue(server._within_allowed_folders(drive, "anything", set(), {}))
        self.assertEqual(drive.calls, 0)  # short-circuits without any API call

    def test_direct_child_is_within_allowed(self) -> None:
        drive = _FakeDrive({"file1": ["root_folder"]})
        self.assertTrue(server._within_allowed_folders(drive, "file1", {"root_folder"}, {}))

    def test_nested_descendant_is_within_allowed(self) -> None:
        drive = _FakeDrive({"file1": ["sub"], "sub": ["root_folder"], "root_folder": []})
        self.assertTrue(server._within_allowed_folders(drive, "file1", {"root_folder"}, {}))

    def test_file_outside_allowed_is_rejected(self) -> None:
        drive = _FakeDrive({"file1": ["other"], "other": []})
        self.assertFalse(server._within_allowed_folders(drive, "file1", {"root_folder"}, {}))

    def test_folder_itself_is_within_allowed(self) -> None:
        drive = _FakeDrive({})
        self.assertTrue(server._within_allowed_folders(drive, "root_folder", {"root_folder"}, {}))

    def test_parent_cycle_terminates(self) -> None:
        drive = _FakeDrive({"a": ["b"], "b": ["a"]})
        self.assertFalse(server._within_allowed_folders(drive, "a", {"root_folder"}, {}))

    def test_enforce_allowed_raises_for_outside_file(self) -> None:
        drive = _FakeDrive({"file1": ["other"], "other": []})
        with mock.patch.dict(os.environ, {"GOOGLE_WORKSPACE_ALLOWED_FOLDER_IDS": "root_folder"}):
            with self.assertRaises(PermissionError):
                server._enforce_allowed("file1", drive)

    def test_enforce_allowed_noop_when_unset(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            server._enforce_allowed("file1")  # must not raise or need a service


if __name__ == "__main__":
    unittest.main()


def _para(text: str) -> dict:
    return {"paragraph": {"elements": [{"textRun": {"content": text}}]}}


def _tab(tab_id: str, title: str, content: list, children: list | None = None) -> dict:
    return {
        "tabProperties": {"tabId": tab_id, "title": title},
        "documentTab": {"body": {"content": content}},
        "childTabs": children or [],
    }


class DocTabsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.doc = {
            "title": "Notes",
            "tabs": [
                _tab("t.0", "Summary", [_para("first\n")]),
                _tab("t.1", "Transcript", [_para("second\n")], [_tab("t.2", "Child", [_para("third\n")])]),
            ],
        }
        service = mock.MagicMock()
        service.documents.return_value.get.return_value.execute.return_value = self.doc
        self.service = service
        patches = [
            mock.patch.object(server, "_service", return_value=service),
            mock.patch.object(server, "_enforce_allowed"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_reads_every_tab_including_children(self) -> None:
        result = server.docs_get_text("doc_1")
        self.service.documents.return_value.get.assert_called_with(documentId="doc_1", includeTabsContent=True)
        self.assertEqual([t["tab_id"] for t in result["tabs"]], ["t.0", "t.1", "t.2"])
        self.assertIn("## Transcript\nsecond", result["text"])
        self.assertIn("## Child\nthird", result["text"])

    def test_reads_one_tab_by_id(self) -> None:
        result = server.docs_get_text("doc_1", tab_id="t.1")
        self.assertEqual(result["text"], "second")
        self.assertNotIn("tabs", result)

    def test_single_tab_doc_returns_plain_text(self) -> None:
        self.doc["tabs"] = [_tab("t.0", "Tab 1", [_para("only\n")])]
        self.assertEqual(server.docs_get_text("doc_1"), {"document_id": "doc_1", "title": "Notes", "text": "only"})

    def test_unknown_tab_raises(self) -> None:
        with self.assertRaises(ValueError):
            server.docs_get_text("doc_1", tab_id="t.missing")

    def test_url_tab_param_is_passed_through(self) -> None:
        result = server.workspace_get_from_url("https://docs.google.com/document/d/doc_1/edit?tab=t.2")
        self.assertEqual(result["data"]["text"], "third")


class DocTableTests(unittest.TestCase):
    def test_extracts_table_cells(self) -> None:
        content = [
            {
                "table": {
                    "tableRows": [
                        {"tableCells": [{"content": [_para("a")]}, {"content": [_para("b")]}]},
                    ]
                }
            },
            _para("after\n"),
        ]
        self.assertEqual(server._extract_text_from_doc_content(content), "a | b\nafter")

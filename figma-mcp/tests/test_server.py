from __future__ import annotations

import os
import unittest
from unittest import mock

from figma_mcp import server


def _reset_index() -> None:
    server._index.update({"team_id": None, "fetched_at": 0.0, "projects": []})


class _FakeApi:
    """Stand-in for the Figma REST API that counts requests per path."""

    def __init__(self, responses: dict[str, dict]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def __call__(self, path: str, **params) -> dict:
        self.calls.append(path)
        return self.responses.get(path, {})


TEAM_RESPONSES = {
    "/teams/42/projects": {"projects": [{"id": "p1", "name": "Web"}, {"id": "p2", "name": "Mobile"}]},
    "/projects/p1/files": {
        "files": [
            {"key": "k1", "name": "Listing Card", "last_modified": "2026-11-01T00:00:00Z"},
            {"key": "k2", "name": "Homepage Redesign", "last_modified": "2026-11-02T00:00:00Z"},
        ]
    },
    "/projects/p2/files": {"files": [{"key": "k3", "name": "Mobile Homepage", "last_modified": ""}]},
}


class FileKeyTests(unittest.TestCase):
    def test_extracts_the_key_from_every_figma_url_shape(self) -> None:
        cases = [
            ("https://www.figma.com/design/abc123/Homepage?node-id=1-2", "abc123"),
            ("https://www.figma.com/file/def456/Old-Style-Link", "def456"),
            ("https://www.figma.com/proto/ghi789/Prototype", "ghi789"),
        ]
        for url, expected in cases:
            with self.subTest(url=url):
                self.assertEqual(server._file_key(url), expected)

    def test_passes_a_bare_key_through(self) -> None:
        self.assertEqual(server._file_key("  abc123 "), "abc123")


class SearchTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_index()
        self.env = mock.patch.dict(os.environ, {"FIGMA_API_TOKEN": "t", "FIGMA_TEAM_ID": "42"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_matches_a_name_regardless_of_case_and_reports_the_project(self) -> None:
        api = _FakeApi(TEAM_RESPONSES)
        with mock.patch.object(server, "_get", api):
            result = server.figma_search_files("homepage")

        self.assertEqual(result["total_matches"], 2)
        self.assertEqual(
            {(f["name"], f["project"]) for f in result["files"]},
            {("Homepage Redesign", "Web"), ("Mobile Homepage", "Mobile")},
        )

    def test_reports_the_full_match_count_when_the_page_is_cut_to_limit(self) -> None:
        api = _FakeApi(TEAM_RESPONSES)
        with mock.patch.object(server, "_get", api):
            result = server.figma_search_files("homepage", limit=1)

        self.assertEqual(result["total_matches"], 2)
        self.assertEqual(len(result["files"]), 1)

    def test_an_empty_query_lists_every_file(self) -> None:
        api = _FakeApi(TEAM_RESPONSES)
        with mock.patch.object(server, "_get", api):
            result = server.figma_search_files("")

        self.assertEqual(result["total_matches"], 3)

    def test_builds_the_team_index_once_and_reuses_it(self) -> None:
        api = _FakeApi(TEAM_RESPONSES)
        with mock.patch.object(server, "_get", api):
            server.figma_search_files("card")
            server.figma_search_files("homepage")
            server.figma_list_projects()

        self.assertEqual(api.calls.count("/teams/42/projects"), 1)
        self.assertEqual(api.calls.count("/projects/p1/files"), 1)

    def test_refresh_rebuilds_the_index(self) -> None:
        api = _FakeApi(TEAM_RESPONSES)
        with mock.patch.object(server, "_get", api):
            server.figma_list_projects()
            server.figma_list_projects(refresh=True)

        self.assertEqual(api.calls.count("/teams/42/projects"), 2)

    def test_a_changed_team_id_is_not_served_from_the_old_cache(self) -> None:
        api = _FakeApi({**TEAM_RESPONSES, "/teams/99/projects": {"projects": []}})
        with mock.patch.object(server, "_get", api):
            server.figma_list_projects()
            with mock.patch.dict(os.environ, {"FIGMA_TEAM_ID": "99"}):
                result = server.figma_list_projects()

        self.assertEqual(result["projects"], [])

    def test_a_missing_team_id_names_the_variable(self) -> None:
        with mock.patch.dict(os.environ, {"FIGMA_TEAM_ID": ""}):
            with self.assertRaisesRegex(RuntimeError, "FIGMA_TEAM_ID"):
                server.figma_search_files("anything")


class FileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env = mock.patch.dict(os.environ, {"FIGMA_API_TOKEN": "t"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_maps_pages_to_their_top_level_frames(self) -> None:
        api = _FakeApi(
            {
                "/files/k1": {
                    "name": "Listing Card",
                    "lastModified": "2026-11-01T00:00:00Z",
                    "document": {
                        "children": [
                            {
                                "name": "Desktop",
                                "children": [{"id": "1:2", "name": "Card / Default", "type": "FRAME"}],
                            }
                        ]
                    },
                }
            }
        )
        with mock.patch.object(server, "_get", api):
            result = server.figma_get_file("https://www.figma.com/design/k1/Listing-Card")

        self.assertEqual(result["file_key"], "k1")
        self.assertEqual(result["name"], "Listing Card")
        page = result["pages"][0]
        self.assertEqual(page["name"], "Desktop")
        self.assertEqual(page["frames"], [{"name": "Card / Default", "type": "FRAME", "node_id": "1:2"}])
        self.assertFalse(page["frames_truncated"])

    def test_caps_the_frames_per_page_and_says_so(self) -> None:
        children = [{"id": str(i), "name": f"Frame {i}", "type": "FRAME"} for i in range(server.MAX_FRAMES_PER_PAGE + 5)]
        api = _FakeApi({"/files/k1": {"document": {"children": [{"name": "Page 1", "children": children}]}}})
        with mock.patch.object(server, "_get", api):
            result = server.figma_get_file("k1")

        page = result["pages"][0]
        self.assertEqual(len(page["frames"]), server.MAX_FRAMES_PER_PAGE)
        self.assertTrue(page["frames_truncated"])


class CommentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env = mock.patch.dict(os.environ, {"FIGMA_API_TOKEN": "t"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_flags_a_resolved_comment_and_keeps_the_newest_within_limit(self) -> None:
        api = _FakeApi(
            {
                "/files/k1/comments": {
                    "comments": [
                        {"user": {"handle": "ana"}, "message": "old", "created_at": "2026-01-01"},
                        {
                            "user": {"handle": "bud"},
                            "message": "spacing is off",
                            "created_at": "2026-02-01",
                            "resolved_at": "2026-02-02",
                            "client_meta": {"node_id": "1:2"},
                        },
                    ]
                }
            }
        )
        with mock.patch.object(server, "_get", api):
            result = server.figma_get_comments("k1", limit=1)

        self.assertEqual(result["total_comments"], 2)
        self.assertEqual(len(result["comments"]), 1)
        comment = result["comments"][0]
        self.assertEqual(comment["author"], "bud")
        self.assertTrue(comment["resolved"])
        self.assertEqual(comment["node_id"], "1:2")

    def test_an_unresolved_comment_without_client_meta_is_not_resolved(self) -> None:
        api = _FakeApi({"/files/k1/comments": {"comments": [{"user": {}, "message": "hi", "client_meta": None}]}})
        with mock.patch.object(server, "_get", api):
            result = server.figma_get_comments("k1")

        self.assertFalse(result["comments"][0]["resolved"])
        self.assertEqual(result["comments"][0]["node_id"], "")


if __name__ == "__main__":
    unittest.main()

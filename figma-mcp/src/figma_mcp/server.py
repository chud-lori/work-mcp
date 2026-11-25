from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Claude Code launches this server by absolute path, so the .env beside the
# package root is the only one it can find.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

API_BASE = "https://api.figma.com/v1"
INDEX_TTL_S = 15 * 60
MAX_FRAMES_PER_PAGE = 50

mcp = FastMCP("figma")

_FILE_KEY_RE = re.compile(r"figma\.com/(?:file|design|proto|board|slides)/([a-zA-Z0-9]+)")

_index: dict[str, Any] = {"team_id": None, "fetched_at": 0.0, "projects": []}


def _token() -> str:
    token = os.environ.get("FIGMA_API_TOKEN")
    if not token:
        raise RuntimeError("FIGMA_API_TOKEN is required")
    return token


def _team_id() -> str:
    team_id = os.environ.get("FIGMA_TEAM_ID")
    if not team_id:
        raise RuntimeError("FIGMA_TEAM_ID is required to list or search a team's files")
    return team_id


def _get(path: str, **params: Any) -> dict[str, Any]:
    with httpx.Client(base_url=API_BASE, headers={"X-Figma-Token": _token()}, timeout=30.0) as client:
        response = client.get(path, params=params or None)
        response.raise_for_status()
        return response.json()


def _file_key(file_key_or_url: str) -> str:
    match = _FILE_KEY_RE.search(file_key_or_url)
    return match.group(1) if match else file_key_or_url.strip()


def _project_index(refresh: bool = False) -> list[dict[str, Any]]:
    """Every project and file name in the team, cached: Figma has no file-name search endpoint."""
    team_id = _team_id()
    cached = _index["team_id"] == team_id and time.monotonic() - _index["fetched_at"] < INDEX_TTL_S
    if cached and not refresh:
        return _index["projects"]

    projects = [
        {
            "id": project["id"],
            "name": project.get("name", ""),
            "files": _get(f"/projects/{project['id']}/files").get("files", []),
        }
        for project in _get(f"/teams/{team_id}/projects").get("projects", [])
    ]
    _index.update({"team_id": team_id, "fetched_at": time.monotonic(), "projects": projects})
    return projects


@mcp.tool()
def figma_list_projects(refresh: bool = False) -> dict[str, Any]:
    """List the projects in the configured Figma team, with a file count each.

    Also the quickest check that FIGMA_TEAM_ID and the token's scopes are right.
    """
    projects = _project_index(refresh=refresh)
    return {
        "team_id": _team_id(),
        "projects": [{"id": p["id"], "name": p["name"], "file_count": len(p["files"])} for p in projects],
    }


@mcp.tool()
def figma_search_files(query: str, limit: int = 10) -> dict[str, Any]:
    """Find a team's Figma files by name, case-insensitive substring match.

    An empty query lists every file. The team index is cached for 15 minutes;
    pass refresh=True to figma_list_projects to rebuild it after a file is added.
    """
    needle = query.strip().lower()
    matches = [
        {
            "name": f.get("name", ""),
            "file_key": f["key"],
            "project": project["name"],
            "last_modified": f.get("last_modified", ""),
            "url": f"https://www.figma.com/design/{f['key']}",
        }
        for project in _project_index()
        for f in project["files"]
        if not needle or needle in f.get("name", "").lower()
    ]
    return {"query": query, "total_matches": len(matches), "files": matches[:limit]}


@mcp.tool()
def figma_get_file(file_key_or_url: str, depth: int = 2) -> dict[str, Any]:
    """Get a Figma file's pages and top-level frames. Takes a file key or any Figma URL.

    depth=2 stops at the frames directly under each page, which is what a
    handoff conversation needs; raising it walks further into the node tree.
    """
    key = _file_key(file_key_or_url)
    data = _get(f"/files/{key}", depth=depth)

    pages = []
    for page in data.get("document", {}).get("children", []):
        children = page.get("children", [])
        pages.append(
            {
                "name": page.get("name", ""),
                "frames": [
                    {"name": c.get("name", ""), "type": c.get("type", ""), "node_id": c.get("id", "")}
                    for c in children[:MAX_FRAMES_PER_PAGE]
                ],
                "frames_truncated": len(children) > MAX_FRAMES_PER_PAGE,
            }
        )

    return {
        "file_key": key,
        "name": data.get("name", ""),
        "last_modified": data.get("lastModified", ""),
        "url": f"https://www.figma.com/design/{key}",
        "pages": pages,
    }


@mcp.tool()
def figma_get_comments(file_key_or_url: str, limit: int = 20) -> dict[str, Any]:
    """Get the most recent comments on a Figma file, oldest of the returned set first."""
    key = _file_key(file_key_or_url)
    comments = _get(f"/files/{key}/comments").get("comments", [])
    return {
        "file_key": key,
        "total_comments": len(comments),
        "comments": [
            {
                "author": c.get("user", {}).get("handle", ""),
                "message": c.get("message", ""),
                "created_at": c.get("created_at", ""),
                "resolved": c.get("resolved_at") is not None,
                "node_id": (c.get("client_meta") or {}).get("node_id", ""),
            }
            for c in comments[-limit:]
        ],
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

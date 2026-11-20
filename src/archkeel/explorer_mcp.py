# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Serve the local Explorer snapshot over MCP stdio."""

import argparse
from pathlib import Path
from typing import Any

from .explorer_queries import Row, query
from .explorer_stories import list_stories, read_story, save_story


def _query_tools(server: Any, path: Path, root: Path) -> None:
    def overview(parent: str = "system", cursor: str = "", limit: int = 50) -> Row:
        """Show system parts, verdict and coverage for the pinned scan."""
        return query(path, root, "overview", {"parent": parent, "cursor": cursor, "limit": limit})

    def map(
        parent: str = "system",
        view: str = "components",
        cursor: str = "",
        limit: int = 50,
        focus: str = "",
    ) -> Row:
        """Show a bounded hierarchy and measured relationships."""
        return query(
            path,
            root,
            "map",
            {"parent": parent, "view": view, "cursor": cursor, "limit": limit, "focus": focus},
        )

    def children(parent: str = "system", cursor: str = "", limit: int = 50) -> Row:
        """List one page of children in the selected scope."""
        return query(path, root, "children", {"parent": parent, "cursor": cursor, "limit": limit})

    def search(text: str, cursor: str = "", limit: int = 50, parent: str = "") -> Row:
        """Find elements by name, or find modules within a map branch."""
        return query(
            path, root, "search", {"text": text, "cursor": cursor, "limit": limit, "parent": parent}
        )

    def relations(
        element: str = "",
        direction: str = "both",
        cursor: str = "",
        limit: int = 50,
        kind: str = "",
        aggregate: str = "",
    ) -> Row:
        """List an element’s relationships or a map aggregate’s contributing relations."""
        return query(
            path,
            root,
            "relations",
            {
                "element": element,
                "direction": direction,
                "cursor": cursor,
                "limit": limit,
                **({"kind": kind} if kind else {}),
                **({"aggregate": aggregate} if aggregate else {}),
            },
        )

    def evidence(relation: str, limit: int = 200, cursor: str = "") -> Row:
        """Read the evidence locations for one relationship."""
        return query(
            path, root, "evidence", {"relation": relation, "limit": limit, "cursor": cursor}
        )

    def source(reference: str, limit: int = 24, start: int | None = None) -> Row:
        """Read a bounded source excerpt at an evidence location."""
        arguments: Row = {"reference": reference, "limit": limit}
        if start is not None:
            arguments["start"] = start
        return query(path, root, "source", arguments)

    def story(id: str) -> Row:
        """Read checked story steps and their coverage."""
        return query(path, root, "story", {"id": id})

    for operation in (overview, map, children, search, relations, evidence, source, story):
        server.tool(operation)


def _story_tools(server: Any, path: Path, root: Path) -> None:
    def stories() -> list[Row]:
        """List saved stories checked against this snapshot."""
        return list_stories(root, path)

    def story_read(id: str) -> Row:
        """Read and check a saved story against this snapshot."""
        return read_story(root, path, id)

    def story_save(spec: Row) -> Row:
        """Save a story candidate and return its checked playback."""
        return save_story(root, path, spec)

    for operation in (stories, story_read, story_save):
        server.tool(operation)


def main() -> None:
    """Bind a trusted snapshot and repository before the client connects."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--root", required=True, type=Path)
    session = parser.parse_args()
    try:
        from fastmcp import FastMCP
    except ModuleNotFoundError as error:
        if error.name != "fastmcp":
            raise
        parser.exit(2, "Install the MCP extra with uv sync --extra mcp.\n")
    path = session.snapshot.resolve(strict=True)
    root = session.root.resolve(strict=True)
    query(path, root, "overview", {"limit": 1})
    server = FastMCP("ArchKeel Explorer")

    _query_tools(server, path, root)
    _story_tools(server, path, root)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()

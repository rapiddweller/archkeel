# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Serve the local Explorer snapshot over MCP stdio."""

import argparse
from pathlib import Path

from .explorer_queries import Row, query


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

    def overview(parent: str = "system", cursor: str = "", limit: int = 50) -> Row:
        """Show system parts, verdict and coverage for the pinned scan."""
        return query(path, root, "overview", {"parent": parent, "cursor": cursor, "limit": limit})

    def children(parent: str = "system", cursor: str = "", limit: int = 50) -> Row:
        """List one page of children in the selected scope."""
        return query(path, root, "children", {"parent": parent, "cursor": cursor, "limit": limit})

    def search(text: str, cursor: str = "", limit: int = 50) -> Row:
        """Find elements by name in the pinned scan."""
        return query(path, root, "search", {"text": text, "cursor": cursor, "limit": limit})

    def relations(
        element: str, direction: str = "both", cursor: str = "", limit: int = 50, kind: str = ""
    ) -> Row:
        """List incoming or outgoing architecture relationships."""
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
            },
        )

    def evidence(relation: str) -> Row:
        """Read the evidence locations for one relationship."""
        return query(path, root, "evidence", {"relation": relation})

    def source(reference: str, limit: int = 24, start: int | None = None) -> Row:
        """Read a bounded source excerpt at an evidence location."""
        arguments: Row = {"reference": reference, "limit": limit}
        if start is not None:
            arguments["start"] = start
        return query(path, root, "source", arguments)

    def story(id: str) -> Row:
        """Read checked story steps and their coverage."""
        return query(path, root, "story", {"id": id})

    for operation in (overview, children, search, relations, evidence, source, story):
        server.tool(operation)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()

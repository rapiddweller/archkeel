# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""SQL directions need both a syntactic connection and an indexed source site."""

from pathlib import Path

from archkeel.explorer_story_sql import _sqlite_direction


def test_sql_direction_requires_same_connection_and_recorded_site(tmp_path: Path) -> None:
    source = tmp_path / "store.py"
    source.write_text(
        "def build():\n    with closing(sqlite3.connect(path)) as connection:\n"
        '        connection.execute("CREATE TABLE a (x)")\n'
    )
    definition = {"path": "store.py", "line": 1, "reference": "definition"}
    sites = {
        "definition": definition,
        "write": {"path": "store.py", "line": 3, "reference": "write"},
    }
    call = {"expression": "connection.execute", "evidence": [{"reference": "write"}]}
    result = _sqlite_direction(tmp_path, definition, [call], sites.get)
    assert result["direction"] == "writes"
    assert result["direction_evidence"] == [sites["write"]]
    assert _sqlite_direction(tmp_path, definition, [], sites.get) == {}
    source.write_text(source.read_text().replace("connection.execute", "other.execute"))
    assert _sqlite_direction(tmp_path, definition, [call], sites.get) == {}

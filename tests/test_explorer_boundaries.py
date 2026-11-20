# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Candidate boundaries retain their anchors and do not claim runtime calls."""

from archkeel.explorer_boundaries import boundary_rows


def test_literal_match_and_open_sites(tmp_path):
    (tmp_path / "client.ts").write_text('axios.get("/health")\ncomHandler.post(url)\n')
    (tmp_path / "server.py").write_text(
        '@router.get("/health")\ndef health(): pass\nsubprocess.run(command)\n'
    )
    modules = [{"name": "client", "path": "client.ts"}, {"name": "server", "path": "server.py"}]
    rows = boundary_rows(tmp_path, modules)
    candidate = next(row for row in rows if row["resolution"] == "candidate")
    assert candidate["target"] == "server"
    assert candidate["evidence"] == [
        {"path": "client.ts", "line": 1},
        {"path": "server.py", "line": 1},
    ]
    assert {row["kind"] for row in rows if row["resolution"] == "open"} == {"http", "process"}


def test_two_calls_on_one_line_have_distinct_ids(tmp_path):
    (tmp_path / "client.ts").write_text("axios.get(a); axios.get(b)\n")
    rows = boundary_rows(tmp_path, [{"name": "client", "path": "client.ts"}])
    assert len(rows) == 2
    assert rows[0]["id"] != rows[1]["id"]

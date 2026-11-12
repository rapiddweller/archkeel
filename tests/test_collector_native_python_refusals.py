# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A native tree must never stand in for a file that the request's CPython refuses."""

from __future__ import annotations

import json
import subprocess
import unicodedata
from pathlib import Path

import pytest
from python_refusal_probes import edge_probes, issue_probes
from test_collector_native_python_parse import _minor, _native, _write
from test_collector_native_python_survey import _native as survey
from test_collector_native_python_survey import _request

from archkeel.analyzer.interpreter import interpreter, python_request
from archkeel.ir.protocol import CollectionError


def _compiles(source: str) -> bool:
    try:
        compile(source, "probe.py", "exec")
    except (SyntaxError, UnicodeError, ValueError, RecursionError):
        return False
    return True


@pytest.mark.parametrize(
    ("name", "source"), sorted(issue_probes().items()), ids=sorted(issue_probes())
)
def test_an_issue_probe_is_a_tree_only_if_cpython_accepts(
    name: str, source: str, tmp_path: Path, python_dump_binary: Path
) -> None:
    rel = "probe.py"
    _write(tmp_path, {rel: source})
    found = _native(python_dump_binary, tmp_path, [rel])[rel]
    accepted = _compiles(source)
    assert accepted or found is not None, (name, _minor(), "CPython refuses; native has facts")
    if found is not None:
        assert found["message"]
    if not accepted:
        result = survey(python_dump_binary, _request(tmp_path, (".",), "probe", False))
        assert result["coverage"]["full_scope"] is False
        assert result["coverage"]["gaps"]
        assert not result["files"] and not result["imports"] and not result["evidence"]
        block = interpreter()
        assert not isinstance(block, CollectionError)
        completed = subprocess.run(
            [str(python_dump_binary), "--dump-symbols"],
            input=python_request(_request(tmp_path, (".",), "probe", False), block),
            capture_output=True,
            check=True,
        )
        symbols = json.loads(completed.stdout)
        assert not symbols["symbols"] and not symbols["evidence"]
        assert symbols["parse_gaps"][0]["data"]["file"] == rel


def test_post_parse_edges_never_accept_a_cpython_refusal(
    tmp_path: Path, python_dump_binary: Path
) -> None:
    probes = edge_probes()
    assert len(probes) >= 150
    rels = _write(tmp_path, {f"{name}.py": source for name, source in probes.items()})
    native = _native(python_dump_binary, tmp_path, rels)
    unsafe = [
        name
        for name, source in probes.items()
        if not _compiles(source) and native[f"{name}.py"] is None
    ]
    assert unsafe == [], (_minor(), unsafe)
    stricter = {
        name: native[f"{name}.py"]["message"]
        for name, source in probes.items()
        if _compiles(source) and native[f"{name}.py"] is not None
    }
    assert all(stricter.values())
    print(
        json.dumps(
            {
                "probes": len(probes),
                "minor": _minor(),
                "equal": len(probes) - len(stricter),
                "stricter": stricter,
                "unsafe": len(unsafe),
            }
        )
    )


@pytest.mark.parametrize("minor", ["10", "15", "999", "oops"])
def test_an_unknown_minor_is_refused_at_dump_decode(
    minor: str, tmp_path: Path, python_dump_binary: Path
) -> None:
    completed = subprocess.run(
        [str(python_dump_binary), "--dump", minor, str(tmp_path)],
        input="",
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "Python minor" in completed.stderr


def test_a_file_past_the_scan_work_limit_has_a_named_gap_and_no_facts(
    tmp_path: Path, python_dump_binary: Path
) -> None:
    source = "#" + "x" * 2_000_001 + "\n"
    assert _compiles(source)
    _write(tmp_path, {"probe.py": source})
    result = survey(python_dump_binary, _request(tmp_path, (".",), "probe", False))
    assert not result["files"] and not result["imports"] and not result["evidence"]
    assert result["coverage"]["full_scope"] is False
    assert "work limit" in result["coverage"]["gaps"][0]["data"]["message"]


def test_the_named_escape_table_matches_this_cpython_unicode_database() -> None:
    table = Path(__file__).parents[1] / "native/python/src/unassigned.txt"
    ranges = table.read_text().splitlines()[_minor() - 11].split()
    found = {
        point
        for text in ranges
        for low, high in [text.split("-")]
        for point in range(int(low, 16), int(high, 16) + 1)
    }
    expected = {point for point in range(0x110000) if unicodedata.category(chr(point)) == "Cn"}
    assert found == expected

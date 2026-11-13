# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-402: a pinned raise site cannot disappear, and each witness must stay invalid."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from native_python import _minor, _native, _write
from python_compile_sites import TAGS, inventory
from test_collector_native_python_survey import _native as survey
from test_collector_native_python_survey import _request

ROOT = Path(__file__).parents[1]
PINS = json.loads((ROOT / "tests/python_compile_messages.json").read_text())
TABLE = json.loads((ROOT / "tests/python_compile_sites.json").read_text())
MINOR = f"3.{_minor()}"
ROWS = [row for row in TABLE["rows"] if row["minor"] == MINOR]


def test_every_pinned_raise_site_has_exactly_one_table_row() -> None:
    assert set(PINS) == set(TAGS)
    expected = {site["id"] for pin in PINS.values() for site in pin["sites"]}
    found = [row["site"] for row in TABLE["rows"]]
    assert len(found) == len(set(found))
    assert set(found) == expected
    for row in TABLE["rows"]:
        assert row["status"] in {"REFUSED", "UNPROVED"}
        assert (row["status"] == "REFUSED") == (row["source"] is not None)
        assert row["reason"]


def test_the_source_extractor_keeps_nested_calls_and_ignores_comments(tmp_path: Path) -> None:
    from python_compile_sites import _call_end, _comments, _strings

    text = 'f(a(b), "x)", /* ) */ "y")'
    clean = _comments(text)
    assert _call_end(clean, 2) == len(text) - 1
    assert _strings(clean) == ["x)", "y"]
    assert _strings('"joined" /* ignored */ "message"'.replace("/* ignored */", "")) == [
        "joinedmessage"
    ]
    for tag in TAGS.values():
        path = tmp_path / tag / "Python/compile.c"
        path.parent.mkdir(parents=True)
        path.write_text('int\nf(void)\n{\n PyErr_SetString(PyExc_ValueError, "test");\n}\n')
    found = inventory(tmp_path)
    assert all(pin["sites"][0]["messages"] == ["test"] for pin in found.values())
    assert all(pin["sites"][0]["function"] == "f" for pin in found.values())


def test_pinned_sources_match_when_the_read_only_checkout_is_available() -> None:
    source = os.environ.get("ARCHKEEL_CPYTHON_SOURCES")
    if source is None:
        pytest.skip("ARCHKEEL_CPYTHON_SOURCES is unset; no gate supplies the CPython source trees")
    assert inventory(Path(source)) == PINS


def check_witness(row) -> None:
    with pytest.raises(
        (SyntaxError, ValueError, OverflowError, RecursionError, MemoryError, UnicodeError)
    ) as raised:
        compile(row["source"], "p.py", "exec", dont_inherit=True)
    error = raised.value
    assert getattr(error, "msg", str(error)) == row["compiler_message"], (
        row["site"],
        "compiler message changed",
        str(error),
    )
    assert type(error).__name__ == row["exception"]


def test_a_different_compiler_message_cannot_share_a_native_reason() -> None:
    row = next(
        row
        for row in ROWS
        if row.get("compiler_message") == "nonlocal declaration not allowed at module level"
    ).copy()
    row["source"] = "def f():\n nonlocal x"
    with pytest.raises(AssertionError, match="compiler message changed"):
        check_witness(row)


def test_the_optional_source_check_reports_its_skip_reason() -> None:
    env = dict(os.environ)
    env.pop("ARCHKEEL_CPYTHON_SOURCES", None)
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-n",
            "0",
            f"{__file__}::test_pinned_sources_match_when_the_read_only_checkout_is_available",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "SKIPPED" in done.stdout
    assert "ARCHKEEL_CPYTHON_SOURCES is unset" in done.stdout


def test_each_raise_site_witness_is_still_a_compiler_refusal(
    tmp_path: Path, python_dump_binary: Path
) -> None:
    assert sys.getrecursionlimit() == TABLE["recursion_limit"] == 1000
    witnessed = [row for row in ROWS if row["source"] is not None]
    for row in witnessed:
        check_witness(row)
    rels = _write(tmp_path, {f"r{index}.py": row["source"] for index, row in enumerate(witnessed)})
    native = _native(python_dump_binary, tmp_path, rels)
    for index, row in enumerate(witnessed):
        found = native[f"r{index}.py"]
        assert found is not None, (row["site"], "CPython refuses; native gives a tree")
        assert found["message"] == row["reason"]
        assert row["native_check"].startswith("native/python/src/")
    result = survey(python_dump_binary, _request(tmp_path, (".",), "probe", False))
    assert result["coverage"]["full_scope"] is False
    assert not result["files"] and not result["imports"] and not result["evidence"]
    assert {gap["data"]["file"] for gap in result["coverage"]["gaps"]} == set(rels)


def test_unproved_sites_keep_the_entry_condition_closed() -> None:
    # A witness for one message does not prove every path to that raise site.
    assert TABLE["complete"] is False
    assert TABLE["unproved"] == sum(row["status"] == "UNPROVED" for row in TABLE["rows"])
    assert TABLE["unproved"] > 0

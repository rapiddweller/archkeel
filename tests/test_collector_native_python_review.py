# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-402: each review refusal must be a gap, not a native tree."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from python_refusal_probes import compiler_refuses
from test_collector_native_python_parse import _minor, _native, _write

ROOT = Path(__file__).parents[1]
CASES = json.loads((ROOT / "tests/python_compile_refusals.json").read_text())["sources"]
MINOR = f"3.{_minor()}"


def test_the_review_corpus_keeps_all_one_hundred_sources() -> None:
    assert len({row["id"] for row in CASES}) == len(CASES) == 100
    assert all(set(row["cpython"]) == {"3.11", "3.12", "3.13", "3.14"} for row in CASES)


def _source(row: dict[str, Any]) -> str | bytes:
    text = row["source"]
    return bytes.fromhex(text["hex"]) if isinstance(text, dict) else text


@pytest.mark.parametrize("row", CASES, ids=[row["id"] for row in CASES])
def test_the_review_corpus_records_the_real_compiler(row: dict[str, Any]) -> None:
    try:
        compile(_source(row), "p.py", "exec", dont_inherit=True)
    except (SyntaxError, UnicodeError, ValueError, RecursionError) as error:
        actual = {
            "accepted": False,
            "exception": type(error).__name__,
            "message": str(error),
            "line": getattr(error, "lineno", None),
        }
    else:
        actual = {"accepted": True}
    assert actual == row["cpython"][MINOR]


@pytest.fixture(scope="module")
def reviewed_native(
    python_dump_binary: Path, tmp_path_factory: pytest.TempPathFactory
) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("review-refusals")
    rels = _write(root, {f"{row['id']}.py": _source(row) for row in CASES})
    return _native(python_dump_binary, root, rels)


@pytest.mark.parametrize("row", CASES, ids=[row["id"] for row in CASES])
def test_a_reviewed_compiler_refusal_is_not_a_native_tree(
    row: dict[str, Any], reviewed_native: dict[str, Any]
) -> None:
    found = reviewed_native[f"{row['id']}.py"]
    if row["cpython"][MINOR]["accepted"]:
        assert found is None
    else:
        assert found is not None, row["id"]
        assert found["message"]


REVIEW_SCOPE_SOURCES = {
    "generator-await-module": "(await x for x in y)",
    "generator-await-function": "def f():\n    return (await x for x in y)",
    "handler-nonlocal": (
        "def f():\n    try: pass\n    except E as x: pass\n    def g():\n        nonlocal x"
    ),
    "lambda-global": "def f():\n    lambda: x\n    global x",
    "comprehension-global": "[x for x in y]\nglobal x",
    "walrus-comprehension-global": "[x := y for y in values]\nglobal x",
    "lambda-default-comprehension-global": "[lambda a=(x := y): a for y in values]\nglobal x",
    "lambda-default-global": "def f():\n    lambda a=x: a\n    global x",
    "lambda-local-walrus-global": "def f():\n    lambda: (x := 1)\n    global x",
    "debug-augment": "a.__debug__ += 1",
    "debug-delete": "del a.__debug__",
    "debug-delete-tuple": "del (a.__debug__, b.__debug__)",
    "relative-future": "from .__future__ import annotations\nfrom __future__ import division",
}
for name, pattern in {
    "capture": "x",
    "star": "[*x]",
    "mapping": "{**x}",
    "as": "1 as x",
}.items():
    REVIEW_SCOPE_SOURCES[f"pattern-{name}-nonlocal"] = (
        f"def f():\n    match value:\n        case {pattern}: pass\n"
        "    def g():\n        nonlocal x"
    )


@pytest.mark.parametrize("name", REVIEW_SCOPE_SOURCES)
def test_a_reviewed_source_matches_the_compiler(
    name: str, python_dump_binary: Path, tmp_path: Path
) -> None:
    source = REVIEW_SCOPE_SOURCES[name]
    accepted = not compiler_refuses(source)
    rels = _write(tmp_path, {"p.py": source})
    assert (_native(python_dump_binary, tmp_path, rels)["p.py"] is None) == accepted, name


@pytest.mark.parametrize(
    ("source", "reason"),
    [
        ("await x", "await outside an async function"),
        ("return", "return outside a function"),
        ("continue", "loop control outside a loop"),
    ],
)
def test_a_gap_names_the_check_that_refuses_the_source(
    source: str, reason: str, python_dump_binary: Path, tmp_path: Path
) -> None:
    with pytest.raises(SyntaxError):
        compile(source, "p.py", "exec", dont_inherit=True)
    rels = _write(tmp_path, {"p.py": source})
    assert _native(python_dump_binary, tmp_path, rels)["p.py"]["message"] == reason

# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-269: one too-deep Python module is a coverage gap, never a stopped scan."""

from __future__ import annotations

import ast
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from test_language_collectors import _request

from archkeel.analyzer.python.source import MAX_AST_DEPTH, _ast_depth
from archkeel.ir.facts import SourceFacts
from archkeel.ir.facts_codec import decode_response, encode_request

# The collector walkers failed between 6,500 and 7,500 operators with the entry's limits.
BEYOND_OLD_CRASH = 12_000

SHAPES: dict[str, Callable[[int], str]] = {
    "sum": lambda n: "TOTAL = " + " + ".join(["a"] * n),
    "attribute": lambda n: "TOTAL = a" + ".b" * n,
    "call_chain": lambda n: "TOTAL = a" + "()" * n,
    # CPython raises MemoryError in its parser for this shape.
    "conditional": lambda n: "TOTAL = " + "1 if a else " * n + "2",
}


def _project(tmp_path: Path, **modules: str) -> None:
    package = tmp_path / "src" / "sample"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "ok.py").write_text("def run():\n    return 1\n")
    for name, source in modules.items():
        (package / f"{name}.py").write_text(source + "\n")


def _collect(tmp_path: Path) -> tuple[subprocess.CompletedProcess[bytes], SourceFacts]:
    completed = subprocess.run(
        [sys.executable, "-I", "-B", "-m", "archkeel.analyzer.python.entry"],
        input=encode_request(_request(tmp_path, "python")),
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")[-2000:]
    assert completed.stderr == b""
    return completed, decode_response(completed.stdout).facts


def _gap_files(facts: SourceFacts) -> list[str]:
    return sorted(str(gap) for gap in facts.coverage.gaps)


def _chain_with_depth(depth: int) -> str:
    # One operator adds one level; the formula is checked against the real measure below.
    operators = depth - _ast_depth(ast.parse("TOTAL = a + a")) + 1
    return SHAPES["sum"](operators + 1)


def test_chain_formula_matches_the_measured_depth() -> None:
    assert _ast_depth(ast.parse(_chain_with_depth(100))) == 100
    assert _ast_depth(ast.parse(_chain_with_depth(500))) == 500


@pytest.mark.parametrize("shape", SHAPES)
def test_a_module_far_beyond_the_old_crash_becomes_one_gap(tmp_path: Path, shape: str) -> None:
    _project(tmp_path, deep=SHAPES[shape](BEYOND_OLD_CRASH))
    _, facts = _collect(tmp_path)
    gaps = _gap_files(facts)
    assert len(gaps) == 1
    assert "src/sample/deep.py" in gaps[0]
    assert facts.coverage.files_parsed == len(facts.coverage.selected_files) - 1
    assert not facts.coverage.full_scope


def test_the_ceiling_is_exact_at_the_boundary(tmp_path: Path) -> None:
    _project(tmp_path, at_ceiling=_chain_with_depth(MAX_AST_DEPTH))
    _, facts = _collect(tmp_path)
    assert _gap_files(facts) == []
    assert facts.coverage.full_scope

    over = tmp_path / "over"
    over.mkdir()
    _project(over, one_over=_chain_with_depth(MAX_AST_DEPTH + 1))
    _, facts = _collect(over)
    gaps = _gap_files(facts)
    assert len(gaps) == 1
    assert "src/sample/one_over.py" in gaps[0]
    assert f"exceeds {MAX_AST_DEPTH}" in gaps[0]


def test_a_parser_stack_overflow_far_past_any_ceiling_is_a_gap(tmp_path: Path) -> None:
    _project(tmp_path, huge=SHAPES["sum"](300_000))
    _, facts = _collect(tmp_path)
    assert len(_gap_files(facts)) == 1


def test_other_modules_keep_their_facts_beside_a_deep_one(tmp_path: Path) -> None:
    _project(
        tmp_path,
        deep=SHAPES["sum"](BEYOND_OLD_CRASH),
        user="from sample.ok import run\n\ndef use():\n    return run()",
    )
    _, facts = _collect(tmp_path)
    symbols = [section for section in facts.sections if section.name == "symbols"]
    text = str(symbols)
    assert "sample.ok" in text
    assert "sample.user" in text
    assert "sample.deep" not in text


def test_two_deep_modules_give_two_gaps_in_a_stable_order(tmp_path: Path) -> None:
    _project(tmp_path, b_deep=SHAPES["sum"](9_000), a_deep=SHAPES["attribute"](9_000))
    first, facts = _collect(tmp_path)
    again, _ = _collect(tmp_path)
    assert len(_gap_files(facts)) == 2
    assert first.stdout == again.stdout


def test_a_wide_module_is_not_a_deep_module(tmp_path: Path) -> None:
    # 200,000 elements in one list: huge, but only a few levels deep.
    _project(tmp_path, wide="TABLE = [" + ", ".join(["1"] * 200_000) + "]")
    _, facts = _collect(tmp_path)
    assert _gap_files(facts) == []
    assert facts.coverage.full_scope


def test_a_deep_but_allowed_module_is_still_analyzed(tmp_path: Path) -> None:
    _project(tmp_path, deep_ok=SHAPES["sum"](2_000))
    _, facts = _collect(tmp_path)
    assert _gap_files(facts) == []
    assert "src/sample/deep_ok.py" in facts.coverage.selected_files

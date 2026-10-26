# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-269: the depth ceiling holds for every expression shape, not only for sums."""

from __future__ import annotations

import ast
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from test_language_collectors import _request

from archkeel.analyzer.python.source import MAX_AST_DEPTH, _ast_depth
from archkeel.ir.facts_codec import decode_response, encode_request

# Each shape grows with n. The call, method, decorator and dict-merge chains cost time that
# grows with the square of the depth (`ast.unparse` of every nested subtree), so they only run
# at a moderate depth here (issue #711); the "one over" test still covers their ceiling.
SHAPES: dict[str, Callable[[int], str]] = {
    "sum": lambda n: "X = " + " + ".join(["a"] * n),
    "string_concat": lambda n: "X = " + " + ".join(['"s"'] * n),
    "attribute_chain": lambda n: "X = a" + ".b" * n,
    "subscript_chain": lambda n: "X = a" + "[0]" * n,
    "call_chain": lambda n: "X = a" + "()" * n,
    "method_chain": lambda n: "X = a" + ".m(1)" * n,
    "unary_not": lambda n: "X = " + "not " * n + "a",
    "unary_minus": lambda n: "X = " + "- " * n + "a",
    "conditional_chain": lambda n: "X = " + "1 if a else " * n + "2",
    "annotation_union": lambda n: "X: " + " | ".join(["int"] * n) + " = 1",
    "default_argument": lambda n: "def g(p=" + " + ".join(["1"] * n) + "):\n    return p",
    "decorator": lambda n: "@d" + "()" * n + "\ndef g():\n    return 1",
    "class_body": lambda n: "class K:\n    X = " + " + ".join(["1"] * n),
    "function_body": lambda n: "def g():\n    return " + " + ".join(["1"] * n),
    "if_condition": lambda n: "if " + " + ".join(["1"] * n) + ":\n    pass",
    "all_list_sum": lambda n: "__all__ = " + " + ".join(["['x']"] * n),
    "fstring_concat": lambda n: "X = " + " + ".join(['f"{a}"'] * n),
    "dict_merge": lambda n: "X = " + " | ".join(["{}"] * n),
}
QUADRATIC = ["call_chain", "method_chain", "decorator", "dict_merge"]
# Same code path as another shape, but slow at the ceiling: covered by the "one over" test only.
REDUNDANT_AT_CEILING = ["class_body", "fstring_concat"]
FAST = [name for name in SHAPES if name not in QUADRATIC + REDUNDANT_AT_CEILING]
# The CPython parser itself refuses these long before the ceiling (it raises MemoryError).
PARSER_LIMITED = {"lambda_chain": lambda n: "X = " + "lambda: " * n + "1"}
FLAT = {
    "boolean_chain": lambda n: "X = " + " and ".join(["a or b"] * n),
    "comparison_chain": lambda n: "X = a" + " < a" * n,
    "list_literal": lambda n: "X = [" + ", ".join(["1"] * n) + "]",
    "dict_literal": lambda n: "X = {" + ", ".join(f"{i}: 1" for i in range(n)) + "}",
    "implicit_string_concat": lambda n: "X = " + " ".join(['"s"'] * n),
}


def _size_for_depth(make: Callable[[int], str], depth: int) -> int:
    """The largest n whose tree is at most `depth` levels, from the slope at small sizes."""
    small, large = _ast_depth(ast.parse(make(100))), _ast_depth(ast.parse(make(200)))
    slope = (large - small) / 100
    return int((depth - (small - slope * 100)) / slope)


def _collect(tmp_path: Path, source: str) -> tuple[int, list[str]]:
    package = tmp_path / "src" / "sample"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "deep.py").write_text(source + "\n")
    completed = subprocess.run(
        [sys.executable, "-I", "-B", "-m", "archkeel.analyzer.python.entry"],
        input=encode_request(_request(tmp_path, "python")),
        capture_output=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")[-1500:]
    gaps = decode_response(completed.stdout).facts.coverage.gaps
    return len(decode_response(completed.stdout).facts.coverage.selected_files), [
        str(gap) for gap in gaps
    ]


@pytest.mark.parametrize("shape", SHAPES)
def test_one_level_over_the_ceiling_is_a_gap_for_every_shape(tmp_path: Path, shape: str) -> None:
    make = SHAPES[shape]
    size = _size_for_depth(make, MAX_AST_DEPTH) + 1
    while _ast_depth_of(make, size) <= MAX_AST_DEPTH:
        size += 1
    _, gaps = _collect(tmp_path, make(size))
    assert len(gaps) == 1
    assert "src/sample/deep.py" in gaps[0]


def _ast_depth_of(make: Callable[[int], str], size: int) -> int:
    # Parsing a tree this deep needs the entry's large stack, so measure it in a thread.
    import threading

    result: list[int] = []

    def work() -> None:
        sys.setrecursionlimit(20_000)
        result.append(_ast_depth(ast.parse(make(size))))

    threading.stack_size(64 * 1024 * 1024)
    thread = threading.Thread(target=work)
    thread.start()
    thread.join()
    return result[0]


@pytest.mark.parametrize("shape", FAST)
def test_a_tree_exactly_at_the_ceiling_is_analyzed_for_every_fast_shape(
    tmp_path: Path, shape: str
) -> None:
    make = SHAPES[shape]
    size = _size_for_depth(make, MAX_AST_DEPTH)
    while _ast_depth_of(make, size) > MAX_AST_DEPTH:
        size -= 1
    assert MAX_AST_DEPTH - 2 <= _ast_depth_of(make, size) <= MAX_AST_DEPTH
    _, gaps = _collect(tmp_path, make(size))
    assert gaps == []


@pytest.mark.parametrize("shape", QUADRATIC)
def test_the_quadratic_shapes_are_analyzed_at_a_moderate_depth(tmp_path: Path, shape: str) -> None:
    _, gaps = _collect(tmp_path, SHAPES[shape](300))
    assert gaps == []


@pytest.mark.parametrize("shape", FLAT)
def test_flat_shapes_stay_flat_however_long(tmp_path: Path, shape: str) -> None:
    source = FLAT[shape](20_000)
    assert _ast_depth(ast.parse(source)) < 20
    _, gaps = _collect(tmp_path, source)
    assert gaps == []


@pytest.mark.parametrize("shape", PARSER_LIMITED)
def test_a_shape_the_parser_refuses_is_a_gap_too(tmp_path: Path, shape: str) -> None:
    _, gaps = _collect(tmp_path, PARSER_LIMITED[shape](20_000))
    assert len(gaps) == 1
    assert "src/sample/deep.py" in gaps[0]

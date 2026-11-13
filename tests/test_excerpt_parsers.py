# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The one owner of the numeric excerpt parser (#880 step S3, AD-322)."""

import ast
import re
from pathlib import Path

import pytest

from archkeel.ir.facts import MAX_NUMERIC_EVIDENCE_CHARS
from archkeel.ir.source_proofs import parse_numeric_evidence_excerpt

_SRC = Path(__file__).resolve().parents[1] / "src" / "archkeel"


def _shape(excerpt: str) -> tuple[list[str], int] | None:
    parsed = parse_numeric_evidence_excerpt(excerpt)
    return None if parsed is None else ([type(node).__name__ for node in parsed[0]], parsed[1])


@pytest.mark.parametrize(
    ("excerpt", "expected"),
    [
        ("x = 1", (["Assign"], 0)),
        ("    x = 1", (["Assign"], 1)),
        ("\tx = 1", (["Assign"], 1)),
        ("if x > 3:", (["If"], 0)),
        ("    if x > 3:", (["If"], 1)),
        ("    for item in items:", (["For"], 1)),
        ("async def f():", (["AsyncFunctionDef"], 0)),
        ("    class A:", (["ClassDef"], 1)),
        ("@decorator", (["FunctionDef"], 0)),
        ("    @decorator(1)", (["If"], 1)),  # an indented excerpt keeps its `if True:` wrapper
        ("elif x > 3:", (["If"], 2)),
        ("    elif x:", (["If"], 3)),
        ("elif(x):", (["If"], 2)),
        ("elifx", (["Expr"], 0)),
        ("else:", None),
        ("a\nb", None),
        ("", None),
        ("x" * (MAX_NUMERIC_EVIDENCE_CHARS + 1), None),
        ("foo(1,", None),
    ],
)
def test_the_parser_reads_one_line_as_the_statements_it_starts(
    excerpt: str, expected: tuple[list[str], int] | None
) -> None:
    """An excerpt is one source line. A header gets a synthetic body, a decorator a function."""
    assert _shape(excerpt) == expected


def test_the_parser_returns_the_nodes_of_the_excerpt() -> None:
    parsed = parse_numeric_evidence_excerpt("    total = a + 1")
    assert parsed is not None
    assert ast.unparse(parsed[0][0]) == "total = a + 1"


@pytest.mark.parametrize(
    ("file", "names"),
    [
        (
            "ir/facts_validation.py",
            (
                "_parse_numeric_evidence_excerpt",
                "_parse_numeric_decorator_excerpt",
                "_numeric_elif_start",
                "_parse_indented_numeric_excerpt",
                "_numeric_header_has_synthetic_body",
                "_parse_numeric_elif_excerpt",
            ),
        ),
    ],
)
def test_the_copies_of_the_excerpt_parser_are_gone(file: str, names: tuple[str, ...]) -> None:
    """Only `source_proofs` defines the parser. Another definition is a second copy."""
    text = (_SRC / file).read_text(encoding="utf-8")
    for name in names:
        assert re.search(rf"^def {name}\b", text, re.MULTILINE) is None, f"{file} defines {name}"

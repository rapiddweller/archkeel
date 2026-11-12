# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The native parse of a Python file equals the parse of the Python collector (AD-334).

The oracle is the unmodified `source.parse_sources` of the running interpreter; the native parse
gets the minor version from the interpreter block. Both must accept or refuse each file, with the
same exception class (a parser error stays in the `SyntaxError` family). The line and the message
must be equal for the limits that the native
collector copies from CPython: 200 brackets, 100 indentation levels, the tab rule, the unindent
rule, null bytes, a bracket that is never closed and `MAX_AST_DEPTH`. Other syntax errors keep
the message of `ruff_python_parser`, a closed difference of AD-334.

Where CPython runs out of its own parser stack (a version-dependent limit), the native parse also
refuses the file with `TooDeepError`; only the message differs (AD-323 point 6, AD-334).

`ARCHKEEL_PYTHON_PARSE_CORPUS` names a directory of `.py` files to compare as well, for example
the 3 000 mutated files of the PR 5 design.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

from archkeel.analyzer.interpreter import interpreter
from archkeel.analyzer.python.source import RECURSION_LIMIT, parse_sources
from archkeel.ir.protocol import CollectionError

# The messages that the native parse copies from CPython: line and message must be equal.
_COPIED = (
    "too many nested parentheses",
    "too many levels of indentation",
    "inconsistent use of tabs and spaces in indentation",
    "unindent does not match any outer indentation level",
    "source code string cannot contain null bytes",
    "was never closed",
    "does not match opening parenthesis",
    "levels exceeds 5000",
)
_PARSER_STACK = "expression nesting exceeds the parser stack"


def _minor() -> int:
    block = interpreter()
    assert not isinstance(block, CollectionError), block
    return int(block.version.split(".")[1])


def _python(root: Path, rels: list[str]) -> dict[str, Any]:
    """The failure of `parse_sources` for each file; `None` for a tree."""
    found: dict[str, Any] = {}

    def work() -> None:
        for rel in rels:
            parsed = parse_sources([root / rel], root=root, namespace="zz_absent")
            # The namespace is absent on purpose: `module_for` then fails after the parse.
            failures = [
                item
                for item in parsed.failures
                if not (item["kind"] == "ValueError" and item["data"]["message"] == "ValueError")
            ]
            found[rel] = (
                {
                    "exception": failures[0]["kind"],
                    "line": failures[0]["data"]["line"],
                    "message": failures[0]["data"]["message"],
                }
                if failures
                else None
            )

    # The collector entry parses on a thread with a big stack and a high recursion limit.
    limit, stack = sys.getrecursionlimit(), threading.stack_size()
    sys.setrecursionlimit(RECURSION_LIMIT)
    threading.stack_size(64 * 1024 * 1024)
    try:
        worker = threading.Thread(target=work)
        worker.start()
        worker.join()
    finally:
        threading.stack_size(stack)
        sys.setrecursionlimit(limit)
    return found


def _native(binary: Path, root: Path, rels: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        [str(binary), "--dump", str(_minor()), str(root)],
        input="".join(f"{rel}\n" for rel in rels),
        capture_output=True,
        text=True,
        check=True,
    )
    # JSON keeps U+2028 and U+0085 raw, and `splitlines` would split there.
    rows = [json.loads(line) for line in completed.stdout.split("\n") if line]
    return {row["file"]: row["outcome"] for row in rows}


# A parser error of ruff can name another place than CPython, and so another class of this family.
_SYNTAX = {"SyntaxError", "IndentationError", "TabError"}


# Limits that no parser error can come before: the file has no other error.
_ALONE = ("levels exceeds 5000", "too many levels of indentation", "null bytes")


def _agrees(expected: Any, found: Any, copied: tuple[str, ...] = _COPIED) -> bool:
    if expected is None or found is None:
        return expected is found
    if _PARSER_STACK in (expected["message"], found["message"]):
        # The stack bound comes before the parse, so it can replace the depth of the tree.
        return bool(expected["exception"] == found["exception"] == "TooDeepError")
    if any(text in expected["message"] for text in copied):
        return bool(expected == found)
    if expected["exception"] in _SYNTAX:
        return found["exception"] in _SYNTAX
    return bool(expected["exception"] == found["exception"])


def _differences(
    binary: Path, root: Path, rels: list[str], copied: tuple[str, ...] = _COPIED
) -> list[tuple[str, Any, Any]]:
    from python_refusal_probes import compiler_refuses, validation_depth_gap

    python, native = _python(root, rels), _native(binary, root, rels)
    return [
        (rel, python[rel], native[rel])
        for rel in rels
        if not _agrees(python[rel], native[rel], copied)
        and not (
            python[rel] is None
            and native[rel] is not None
            and (
                validation_depth_gap((root / rel).read_bytes(), native[rel]["message"])
                or compiler_refuses((root / rel).read_bytes())
            )
        )
    ]


def _write(root: Path, cases: dict[str, str | bytes]) -> list[str]:
    for name, text in cases.items():
        data = text.encode("utf-8") if isinstance(text, str) else text
        (root / name).write_bytes(data)
    return sorted(cases)


_CASES: dict[str, str | bytes] = {
    "plain.py": "import os\nfrom . import x\n",
    "bom.py": b"\xef\xbb\xbfimport os\n",
    "bad_utf8.py": b"x = '\xff'\n",
    "null.py": "x = 1\0\n",
    "brackets_120.py": "x = " + "(" * 120 + "1" + ")" * 120 + "\n",
    "brackets_201.py": "x = 1\ny = " + "[" * 201 + "]" * 201 + "\n",
    "indent_100.py": "".join(" " * level + "if 1:\n" for level in range(99)) + " " * 99 + "x\n",
    "indent_101.py": "".join(" " * level + "if 1:\n" for level in range(101)) + " " * 101 + "x\n",
    "tabs.py": "if 1:\n\tif 1:\n        pass\n",
    "tabs_same.py": "if 1:\n        x = 1\n\ty = 2\n",
    "unindent.py": "def f():\n    x\n  y\n",
    "never_closed.py": "x = 1\nf(a,\n  [b,\n",
    "mismatch.py": "x = (1,\n  2]\n",
    "mismatch_line.py": "x = [1, 2)\n",
    "unmatched.py": "x = 1)\n",
    "elif_chain.py": "if a:\n    pass\n" + "elif b:\n    pass\n" * 6000 + "else:\n    pass\n",
    "plus_4990.py": "x = " + "+".join(["a"] * 4990) + "\n",
    "plus_5000.py": "x = " + "+".join(["a"] * 5000) + "\n",
    "attr_6000.py": "x = a" + ".b" * 6000 + "\n",
    "not_2900.py": "x = " + "not " * 2900 + "a\n",
    "not_40000.py": "x = " + "not " * 40000 + "a\n",
    "neg_list.py": "x = [" + ", ".join(f"-{n}" for n in range(20000)) + "]\n",
    "lambda_6000.py": "f = " + "lambda: " * 6000 + "0\n",
    "fstring.py": 'x = f"{a!r:>{w}}" f"{b}" "c"\n',
    "match.py": "match x:\n    case [1, *rest] | {'k': _} if rest:\n        pass\n",
    "type_alias.py": "type X = int\n",
    "generic.py": "def f[T](x: T) -> T:\n    return x\n",
    "except_group.py": "try:\n    pass\nexcept* ValueError:\n    pass\n",
    "except_bare_tuple.py": "try:\n    pass\nexcept ValueError, TypeError:\n    pass\n",
    "template.py": 'x = t"{a}"\n',
    "nested_fstring.py": "x = f\"{f'{1}'}\"\n",
    "decorators.py": "@a.b(c)\n@d\nclass E(F, metaclass=G):\n    x: int = 1\n",
    "indented_block.py": "if ok:\npass\n",
    "unexpected_indent.py": "x = 1\n    y = 2\n",
}


def test_each_case_has_the_outcome_of_the_python_collector(
    tmp_path: Path, python_dump_binary: Path
) -> None:
    rels = _write(tmp_path, _CASES)
    assert _differences(python_dump_binary, tmp_path, rels) == []


def test_the_parse_follows_the_grammar_of_the_minor_version(
    tmp_path: Path, python_dump_binary: Path
) -> None:
    rels = _write(tmp_path, {"type_alias.py": "type X = int\n", "template.py": 'x = t"{a}"\n'})
    outcomes = {}
    for minor in (11, 14):
        completed = subprocess.run(
            [str(python_dump_binary), "--dump", str(minor), str(tmp_path)],
            input="".join(f"{rel}\n" for rel in rels),
            capture_output=True,
            text=True,
            check=True,
        )
        outcomes[minor] = {
            row["file"]: row["outcome"] for row in map(json.loads, completed.stdout.splitlines())
        }
    assert outcomes[11]["type_alias.py"]["exception"] == "SyntaxError"
    assert outcomes[11]["template.py"]["exception"] == "SyntaxError"
    assert outcomes[14] == {"template.py": None, "type_alias.py": None}


@pytest.mark.skipif(not os.environ.get("ARCHKEEL_PYTHON_PARSE_CORPUS"), reason="no corpus is named")
def test_a_named_corpus_has_the_outcomes_of_the_python_collector(python_dump_binary: Path) -> None:
    # In a file with many errors, CPython can replace a parser error with a later tokenizer error
    # (`_PyPegen_tokenize_full_source_to_check_for_errors`), so only the limits that stand alone
    # must have the same line and message here.
    root = Path(os.environ["ARCHKEEL_PYTHON_PARSE_CORPUS"])
    rels = sorted(path.relative_to(root).as_posix() for path in root.rglob("*.py"))
    assert _differences(python_dump_binary, root, rels, _ALONE) == []

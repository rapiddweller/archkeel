# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
# ruff: noqa: E402
"""Hostile sources: the native parse accepts or refuses each one as the running CPython does.

A deterministic generator writes each class of source that a review found or that the parse
copies from CPython: the integer digit limit, the parser stack, invisible characters, the f-string
limits of each version, `__future__`, the tokenizer limits. The oracle is the unmodified
`source.parse_sources` of the running interpreter (run it on 3.11 to 3.14). A file that CPython
refuses must have no native tree. A file that only native refuses is allowed only when its case is
in `STRICTER`, the closed list of AD-334 point 6.
"""

from __future__ import annotations

import pytest
from oracle_support import ORACLE_UNAVAILABLE

pytest.skip(ORACLE_UNAVAILABLE, allow_module_level=True)

import sys
import threading
from collections.abc import Iterator
from pathlib import Path

from archkeel.analyzer.python.source import RECURSION_LIMIT, parse_sources

from tests.test_collector_native_python_parse import _minor, _native, _write

# Case prefix -> why native may refuse a file that CPython accepts (AD-334 point 6).
_BOUND = "the stack bound is above the real CPython parser stack (AD-334 point 6 (b))"
STRICTER = {
    "stack-": _BOUND,
    "brackets-199": _BOUND,
    "brackets-200": _BOUND,
    # Python 3.11 does not count the braces of an f-string, so 200 brackets around one are valid.
    "brackets-201-fstring": _BOUND,
    "fstring-nested-149": _BOUND,
    "fstring311-brackets-150": _BOUND,
    "fstring311-brackets-199": _BOUND,
    "future-barry-diamond": "ruff has no `<>` operator (AD-334 point 6 (c))",
}

DIGITS = 4300


def _ints() -> Iterator[tuple[str, str]]:
    for size in (DIGITS - 1, DIGITS, DIGITS + 1, 6000):
        digits = "7" * size
        yield f"int-{size}", f"x = {digits}\n"
        yield f"int-{size}-fstring", f"x = f'{{{digits}}}'\n"
        yield f"int-{size}-case", f"match x:\n    case {digits}:\n        pass\n"
        yield f"int-{size}-annotation", f"x: {digits} = 1\n"
        yield f"int-{size}-default", f"def f(a={digits}):\n    pass\n"
        yield f"int-{size}-dead", f"if 0:\n    x = [{digits}]\n"
        yield f"int-{size}-lambda", f"f = lambda: -{digits}\n"
        yield f"int-{size}-underscores", f"x = {'1_' * (size - 1)}1\n"
        yield f"int-{size}-zeros", f"x = {'0' * size}\n"
        yield f"int-{size}-hex", f"x = 0x{'f' * size}\n"
        yield f"int-{size}-float", f"x = {digits}.5\n"
        yield f"int-{size}-imaginary", f"x = {digits}j\n"
        yield f"int-{size}-line-3", f"a = 1\n\nb = {digits}\n"


_CHAINS = {
    # name: (prefix, unit, core, suffix unit); the measured CPython maximum is the comment.
    "not": ("x = ", "not ", "a", ""),  # 5 967
    "neg": ("x = ", "-", "a", ""),  # 5 967
    "else": ("x = a", " if b else a", "", ""),  # 5 967
    "lambda": ("x = ", "lambda: ", "0", ""),  # 2 983
    "lambda-params": ("x = ", "lambda a, b=1: ", "0", ""),
    "lambda-default": ("x = ", "lambda a=", "0", ": 0"),
    "lambda-else": ("", "lambda: a if b else ", "0", ""),  # 1 989
    "power": ("x = a", " ** a", "", ""),
    "neg-power": ("x = ", "-a**", "a", ""),  # 1 989
}
_BRACKETS = {
    "group": ("(", ")"),
    "compare": ("(a < ", ")"),
    "mixed": ("(a or b and c < ", ")"),
    "list": ("[", "]"),
    "call": ("f(", ")"),
    "keyword": ("f(k=", ")"),
    "dict": ("{a: ", "}"),
    "comprehension": ("[a for a in b if c < ", "]"),
    "lambda-default": ("(lambda a=b < ", ": 0)"),
}


def _stack() -> Iterator[tuple[str, str]]:
    for name, (prefix, unit, core, suffix) in _CHAINS.items():
        for count in (1000, 1989, 1990, 2983, 2984, 3000, 5967, 5968, 9000):
            yield f"stack-{name}-{count}", f"{prefix}{unit * count}{core}{suffix * count}\n"
    for name, (opening, closing) in _BRACKETS.items():
        for count in (100, 150, 170, 199):
            yield f"stack-{name}-{count}", f"x = {opening * count}a{closing * count}\n"
    for count in (5274, 5275, 5500):
        blocks = "".join(" " * level + "def f():\n" for level in range(99))
        yield f"stack-blocks-not-{count}", f"{blocks}{' ' * 99}x = {'not ' * count}a\n"
    nested_calls = "x = " + "f(g(a, [b, {c: (d,)}], k=" * 20 + "a" + "))" * 20 + "\n"
    yield "real-calls", nested_calls


def _characters() -> Iterator[tuple[str, str | bytes]]:
    yield "bom-two", "\ufeff\ufeffx = 1\n".encode()
    yield "bom-one", "\ufeffx = 1\n".encode()
    yield "bom-middle", "x = 1\n\ufeffy = 2\n"
    yield "bom-string", "x = '\ufeff'  # \ufeff\n"
    for code in (0x200C, 0x200D):
        char = chr(code)
        yield f"joiner-{code:x}-inside", f"a{char}b = 1\n"
        yield f"joiner-{code:x}-end", f"ab{char} = 1\n"
        yield f"joiner-{code:x}-start", f"{char}ab = 1\n"
        yield f"joiner-{code:x}-string", f"x = 'a{char}b'\n"
        yield f"joiner-{code:x}-fstring", f"x = f'{{a{char}b}}'\n"
        yield f"joiner-{code:x}-attribute", f"x = a.b{char}c\n"
        yield f"joiner-{code:x}-import", f"import a{char}b\n"
    for code in (0xA0, 0x3000, 0x0B, 0x0C, 0x1C, 0x85, 0x2028, 0x180E, 0xAD, 0x1C89, 0xA7CB):
        yield f"char-{code:x}-gap", f"x{chr(code)}= 1\n"
        yield f"char-{code:x}-name", f"a{chr(code)} = 1\n"
        yield f"char-{code:x}-first", f"{chr(code)}a = 1\n"


def _fstrings() -> Iterator[tuple[str, str]]:
    for levels in (2, 3, 4, 100, 149, 150, 151):
        yield f"fstring-nested-{levels}", "x = " + "f'{" * levels + "1" + "}'" * levels + "\n"
    yield "fstring-quotes-4", "x = f'''{f\"\"\"{f'{f\"{1}\"}'}\"\"\"}'''\n"
    for inner in (1, 150, 199, 200, 201):
        yield f"fstring311-brackets-{inner}", f"x = f'{{{'(' * inner}a{')' * inner}}}'\n"
    cases = {
        "spec-1": "f'{a:{b}}'",
        "spec-2": "f'{a:{b:{c}}}'",
        "spec-2-conversion": "f'{a!r:{b!s:{c}}}'",
        "spec-2-inner": "f'{f\"{a:{b:{c}}}\"}'",
        "spec-siblings": "f'{a:{b}{c}}'",
        "star": "f'{*a}'",
        "star-comma": "f'{*a,}'",
        "star-tuple": "f'{*a, b}'",
        "star-second": "f'{a, *b}'",
        "star-group": "f'{(*a,)}'",
        "star-conversion": "f'{*a!r}'",
        "star-spec": "f'{*a:>3}'",
        "debug": "f'{a=}'",
        "debug-spec": "f'{a=:>{w}}'",
        "backslash": "f'{\"\\n\".join(a)}'",
        "comment": "f'{a # c\n}'",
        "same-quote": "f'{f'{a}'}'",
        "lambda": "f'{(lambda: 1)()}'",
        "walrus": "f'{(a := 1)}'",
        "dict": "f'{ {a: b} }'",
        "set": "f'{ {a} | {b} }'",
        "slice": "f'{a[1:2]}'",
        "template": "t'{a}'",
        "template-nested": "t'{t\"{a}\"}'",
        "empty": "f'{}'",
        "bang": "f'{a!}'",
        "brace-escape": "f'{{a}}'",
        "lone-brace": "f'{a}}'",
    }
    for name, text in cases.items():
        yield f"fstring-{name}", f"x = {text}\n"


def _futures() -> Iterator[tuple[str, str]]:
    cases = {
        "braces": "from __future__ import braces\n",
        "unknown": "from __future__ import nope\n",
        "star": "from __future__ import *\n",
        "known-all": "from __future__ import nested_scopes, generators, division, "
        "absolute_import, with_statement, print_function, unicode_literals, barry_as_FLUFL, "
        "generator_stop, annotations\n",
        "second-unknown": "from __future__ import annotations, nope, braces\n",
        "group": "from __future__ import (braces)\n",
        "alias": "from __future__ import annotations as a, braces as b\n",
        "docstring": '"doc"\nfrom __future__ import braces\n',
        "docstring-joined": '"a" "b"\nfrom __future__ import braces\n',
        "docstring-group": '("d")\nfrom __future__ import braces\n',
        "docstring-two": '"d"\n"e"\nfrom __future__ import braces\n',
        "docstring-fstring": 'f"d"\nfrom __future__ import braces\n',
        "docstring-bytes": 'b"d"\nfrom __future__ import braces\n',
        "comment": "# c\n\nfrom __future__ import braces\n",
        "late": "x = 1\nfrom __future__ import braces\n",
        "after-import": "from os import path\nfrom __future__ import braces\n",
        "after-future": "from __future__ import annotations\nfrom __future__ import nope\n",
        "semicolon": "from __future__ import annotations; from __future__ import nope\n",
        "relative": "from .__future__ import braces\n",
        "function": "def f():\n    from __future__ import braces\n",
        "block": "if 1:\n    from __future__ import braces\n",
        "annotated": "x: int\nfrom __future__ import nope\n",
        "barry-not-equal": "from __future__ import barry_as_FLUFL\nx = 1 != 2\n",
        "barry-diamond": "from __future__ import barry_as_FLUFL\nx = 1 <> 2\n",
        "barry-before": "x = 1 != 2\nfrom __future__ import barry_as_FLUFL\n",
        "barry-relative": "from .__future__ import barry_as_FLUFL\nx = 1 != 2\n",
        "barry-group": "from __future__ import (barry_as_FLUFL)\nx = 1 != 2\n",
        "barry-fstring": "from __future__ import barry_as_FLUFL\nx = f'{1 != 2}'\n",
        "barry-alias": "from __future__ import barry_as_FLUFL as b\nx = 1 != 2\n",
        "barry-renamed": "from __future__ import annotations as barry_as_FLUFL\nx = 1 != 2\n",
        "barry-dead": "if 0:\n    from __future__ import barry_as_FLUFL\nx = 1 != 2\n",
        "barry-function": "def f():\n    from __future__ import barry_as_FLUFL\n    return 1\n",
        "diamond": "x = 1 <> 2\n",
    }
    for name, text in cases.items():
        yield f"future-{name}", text


def _tokenizer() -> Iterator[tuple[str, str]]:
    for count in (199, 200, 201):
        yield f"brackets-{count}", "x = " + "(" * count + "1" + ")" * count + "\n"
        yield (
            f"brackets-{count}-fstring",
            "x = " + "(" * (count - 1) + "f'{a}'" + ")" * (count - 1) + "\n",
        )
    for levels in (99, 100, 101):
        lines = "".join(" " * level + "if 1:\n" for level in range(levels))
        yield f"indent-{levels}", lines + " " * levels + "x\n"
    yield "tab-deeper-fewer", "if 1:\n       if 1:\n\tpass\n"
    yield "tab-same-column", "if 1:\n        x = 1\n\ty = 2\n"
    yield "tab-deeper-more", "if 1:\n\tif 1:\n\t\tpass\n"
    yield "tab-after-tab", "if 1:\n\tif 1:\n        pass\n"
    yield "tab-dedent", "if 1:\n\tif 1:\n\t\tpass\n    x = 1\n"
    yield "unindent", "def f():\n    x\n  y\n"
    yield "null", "x = 1\0\n"
    yield "never-closed", "x = 1\nf(a,\n  [b,\n"
    yield "mismatch", "x = (1,\n  2]\n"
    yield "unmatched", "x = 1)\n"
    for count in (4990, 5000):
        yield f"ast-depth-{count}", "x = " + "+".join(["a"] * count) + "\n"
    yield "elif-6000", "if a:\n    pass\n" + "elif b:\n    pass\n" * 6000


def cases() -> dict[str, str | bytes]:
    found: dict[str, str | bytes] = {}
    for name, text in (
        *_ints(),
        *_stack(),
        *_characters(),
        *_fstrings(),
        *_futures(),
        *_tokenizer(),
    ):
        assert name not in found, name
        found[f"{name}.py"] = text
    return found


def _python(root: Path, rels: list[str]) -> dict[str, str | None]:
    """The class of the first failure of `parse_sources`, or `None` for a tree.

    CPython 3.11 raises `SystemError` for a long integer in an f-string; the collector does not
    catch it, so the file has no tree either (AD-334 point 6 (d)).
    """
    found: dict[str, str | None] = {}

    def work() -> None:
        for rel in rels:
            try:
                parsed = parse_sources([root / rel], root=root, namespace="zz_absent")
            except SystemError:
                found[rel] = "SystemError"
                continue
            failures = [
                item["kind"]
                for item in parsed.failures
                if not (item["kind"] == "ValueError" and item["data"]["message"] == "ValueError")
            ]
            found[rel] = failures[0] if failures else None

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


def _compare(binary: Path, root: Path, sources: dict[str, str | bytes]) -> list[str]:
    from python_refusal_probes import compiler_refuses, validation_depth_gap

    rels = _write(root, sources)
    python, native = _python(root, rels), _native(binary, root, rels)
    problems = []
    for rel in rels:
        refused_by_python = python[rel] is not None
        refused_by_native = native[rel] is not None
        if refused_by_python and not refused_by_native:
            problems.append(f"{rel}: CPython refuses ({python[rel]}), native gives a tree")
        elif refused_by_native and not refused_by_python:
            if any(rel.startswith(prefix) for prefix in STRICTER):
                continue
            if validation_depth_gap(sources[rel], native[rel]["message"]) or compiler_refuses(
                sources[rel]
            ):
                continue
            problems.append(f"{rel}: native refuses ({native[rel]}), not in STRICTER")
    return problems


def test_the_generator_has_at_least_300_cases() -> None:
    assert len(cases()) >= 300


def test_each_hostile_source_has_the_outcome_of_cpython_or_a_listed_stricter_one(
    tmp_path: Path, python_dump_binary: Path
) -> None:
    assert _compare(python_dump_binary, tmp_path, cases()) == []


def _table(minor: int) -> list[tuple[str, int, int]]:
    text = (Path(__file__).parents[1] / "native/python/src/identifier.txt").read_text()
    rows = [line.split(" ") for line in text.splitlines() if line and not line.startswith("#")]
    return [
        (kind, int(low, 16), int(high, 16))
        for version, kind, low, high in rows
        if version == f"3.{minor}"
    ]


def test_the_identifier_table_of_this_python_is_the_table_of_its_unicode_version(
    tmp_path: Path, python_dump_binary: Path
) -> None:
    # CPython of this version refuses both ends of each range, and so does native.
    minor = _minor()
    sources: dict[str, str | bytes] = {}
    for kind, low, high in _table(minor):
        for code in {low, high}:
            text = f"{chr(code)}=1\n" if kind == "start" else f"a{chr(code)}=1\n"
            sources[f"ident-{kind}-{code:x}.py"] = text
    rels = _write(tmp_path, sources)
    python, native = _python(tmp_path, rels), _native(python_dump_binary, tmp_path, rels)
    accepted = [rel for rel in rels if python[rel] is None or native[rel] is None]
    assert accepted == []

# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""CPython post-parse edges, based on Lib/test/test_{syntax,grammar,fstring,unicode}."""

from __future__ import annotations

import ast

import pytest
from oracle_support import ORACLE_UNAVAILABLE


def compiler_refuses(source: str | bytes) -> bool:
    try:
        compile(source, "probe.py", "exec", dont_inherit=True)
    except (SyntaxError, UnicodeError, ValueError, RecursionError):
        return True
    return False


def compiler_checked_collect(request):
    pytest.skip(ORACLE_UNAVAILABLE)


def validation_depth_gap(source: str | bytes, message: str) -> bool:
    if message != "CPython validation depth limit exceeded":
        return False
    try:
        pending = [(ast.parse(source), 0)]
        while pending:
            node, depth = pending.pop()
            if depth >= 1000:
                return True
            pending.extend((child, depth + 1) for child in ast.iter_child_nodes(node))
    except (SyntaxError, RecursionError):
        return True
    return False


def issue_probes() -> dict[str, str]:
    return {
        "unicode15": r"x = '\N{KAWI LETTER A}'",
        "unicode16": r"x = '\N{TODHRI LETTER A}'",
        "hangul-lower": r"x = '\N{hangul syllable ga}'",
        "spec-depth": "x = f'{a:{b:{c:{d}}}}'",
        "star-yield": "def f():\n    x = [1, *(yield) or b]",
        "raw-spec-name": r"x = rf'{ab:\N{BULLET}}'",
        "attribute-depth": "x = a" + ".b" * 3000,
        "call-depth": "x = a" + "()" * 3000,
    }


def edge_probes() -> dict[str, str]:
    """Vary scope, target grammar, pattern checks, escapes, and replacement field depth."""
    probes = issue_probes()
    statements = [
        "return",
        "return 1",
        "yield",
        "yield from x",
        "await x",
        "break",
        "continue",
        "nonlocal x",
        "global x",
        "x = 1; global x",
        "x; global x",
        "del x; global x",
        "x: int; global x",
        "global x; nonlocal x",
        "assert True",
        "raise",
        "pass",
        "from __future__ import braces",
        "from __future__ import unknown",
        "from __future__ import annotations",
        "from x import *",
    ]
    contexts = {
        "module": "{}\n",
        "function": "def f():\n{}\n",
        "async": "async def f():\n{}\n",
        "loop": "while True:\n{}\n",
        "class": "class Container:\n{}\n",
        "nested": "def outer():\n    x = 1\n    def inner():\n{}\n",
    }
    for context, template in contexts.items():
        indent = "" if context == "module" else "        " if context == "nested" else "    "
        for index, statement in enumerate(statements):
            probes[f"scope-{context}-{index}"] = template.format(indent + statement)
    for index, target in enumerate(
        ["1", "a()", "a + b", "a", "a.b", "a[b]", "*a", "a, *b", "a, *b, *c"]
    ):
        for kind, template in {
            "assign": "{} = x",
            "delete": "del {}",
            "augment": "{} += x",
            "annotate": "{}: int = x",
            "for": "for {} in xs:\n    pass",
        }.items():
            probes[f"target-{kind}-{index}"] = template.format(target)
    for index, parameters in enumerate(
        ["a, a", "a, /, a", "a, *a", "a, **a", "*, a, a", "a=1, b", "a", "a, /, *, b"]
    ):
        probes[f"parameters-{index}"] = f"def f({parameters}): pass"
    for index, pattern in enumerate(
        [
            "[a, a]",
            "[a, *b, *c]",
            "a | b",
            "1 | 2",
            "[a] | (a,)",
            "{'a': x, 'a': y}",
            "{1: x, True: y}",
            "C(a=x, a=y)",
            "_ | 1",
            "[a] | [b]",
            "[a, *b]",
            "{'a': a, **rest}",
        ]
    ):
        probes[f"pattern-{index}"] = f"match x:\n    case {pattern}: pass"
    for depth in range(1, 7):
        field = "a"
        for _ in range(depth):
            field = "a:{" + field + "}"
        for prefix in ["f", "rf", "t"]:
            probes[f"spec-{prefix}-{depth}"] = prefix + "'{" + field + "}'"
    for index, name in enumerate(
        [
            "BULLET",
            "hangul syllable ga",
            "HANGUL SYLLABLE GA",
            "KAWI LETTER A",
            "TODHRI LETTER A",
            "CJK UNIFIED IDEOGRAPH-2EBF0",
            "NOT A NAME",
        ]
    ):
        for prefix in ["", "r", "f", "rf", "t"]:
            probes[f"name-{prefix}-{index}"] = prefix + "'\\N{" + name + "}'"
    probes.update(
        {
            "lambda-duplicate": "f = lambda a, a: a",
            "lambda-default-yield": "x = lambda a=(yield): a",
            "scope-yield-depth": (
                "async def f():\n    x = (yield 1)" + ".a" * 250 + "\n    return 1"
            ),
            "debug-store": "__debug__ = 1",
            "debug-delete": "del __debug__",
            "debug-function": "def __debug__(): pass",
            "debug-class": "class __debug__: pass",
            "debug-parameter": "def f(__debug__): pass",
            "debug-import": "import x as __debug__",
            "debug-pattern": "match x:\n    case __debug__: pass",
            "debug-attribute": "obj.__debug__ = 1",
            "debug-keyword": "f(__debug__=1)",
            "debug-class-keyword": "class C(__debug__=1): pass",
            "debug-pattern-keyword": "match x:\n    case C(__debug__=1): pass",
            "debug-except": "try: pass\nexcept Exception as __debug__: pass",
            "debug-pattern-rest": "match x:\n    case {**__debug__}: pass",
            "call-star-boolean": "f(*a or b)",
            "call-star-yield": "def f():\n    g(*(yield) or b)",
            "global-import": "def f():\n    import x\n    global x",
            "global-pattern": "def f():\n    match value:\n        case x: pass\n    global x",
            "global-except": (
                "def f():\n    try: pass\n    except Exception as x: pass\n    global x"
            ),
            "global-annotation": "def f():\n    global x\n    x: int",
            "nonlocal-annotation": (
                "def f():\n    x=1\n    def g():\n        nonlocal x\n        x: int"
            ),
            "async-generator-return": "async def f():\n    yield 1\n    return 1",
            "async-for-outside": "for x in y: pass\nasync for x in y: pass",
            "async-with-outside": "async with x: pass",
            "comprehension-yield": "def f():\n    x = [(yield a) for a in b]",
            "comprehension-outer-yield": "def f():\n    x = [a for a in [(yield b)]]",
            "raw-spec-hex": r"x = rf'{ab:\xZZ}'",
            "raw-spec-unicode": r"x = rf'{ab:\uZZZZ}'",
            "comprehension-walrus-iter": "def f():\n    x = [a for a in (b := c)]",
            "comprehension-walrus-target": "def f():\n    x = [(a := 1) for a in b]",
            "except-star-return": "def f():\n    try: pass\n    except* Exception: return",
            "pattern-negative-key": "match x:\n    case {-1: a, -1: b}: pass",
            "pattern-bytes-key": "match x:\n    case {b'a': a, b'a': b}: pass",
            "pattern-complex-key": "match x:\n    case {1: a, 1+0j: b}: pass",
            "pattern-or-unreachable": "match x:\n    case 1 | _: pass\n    case 2: pass",
            "nonlocal-class": "class C:\n    x=1\n    def f():\n        nonlocal x",
            "nonlocal-global-barrier": (
                "def f():\n    x=1\n    def g():\n        global x\n"
                "        def h():\n            nonlocal x"
            ),
            "replacement-raw": "x = f'\ufffd{a}'",
            "replacement-escape": r"x = f'\ufffd{a}'",
            "debug-comment": "x = f'''{ a # comment\n = }'''",
            "template-space": "x = t'{ a   }'",
            "template-comment": "x = t'''{ a # comment\n }'''",
            "float-tie": "x = 2.98023223876953125e-8",
        }
    )
    return probes

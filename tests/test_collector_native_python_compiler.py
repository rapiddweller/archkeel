# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Source-audit cases in addition to the independent review corpus."""

from __future__ import annotations

from pathlib import Path

import pytest
from native_python import _native, _write
from python_refusal_probes import compiler_refuses

SOURCES = {
    "unpack-before-star": "(" + "x," * 256 + "*rest) = values",
    "pattern-before-star": "match value:\n case [" + "_," * 256 + "*rest]: pass",
    "nonlocal-before-global": "def f():\n x=0\n def g():\n  nonlocal x\n  global x",
    "mangled-parameters": "class C:\n def f(__x, _C__x): pass",
    "comp-inner-rebind": "[x for x in values if (y := 1) for y in values]",
    "async-await-list": "[await x for x in values]",
    "generic-default-walrus": "def f[T](x=(y := 1)): pass",
    "generic-default-yield": "def f():\n def g[T](x=(yield)): pass",
    "docstring-surrogate": "'\\ud800'",
    "assigned-surrogate": "x = '\\ud800'",
    "non-doc-surrogate": "pass\n'\\ud800'",
    "fstring-surrogate": "f'\\ud800'",
    "named-surrogate": "'\\N{CJK UNIFIED IDEOGRAPH-04E00}'",
    "unicode15-name": "'\\N{KAWI LETTER A}'",
    "lambda-yield-alias": "type X = lambda: (yield)",
    "lambda-walrus-alias": "type X = lambda: (x := 1)",
    "unpacked-vararg-annotation": "def f(*args: *Ts): pass",
    "starred-regular-annotation": "def f(arg: *Ts): pass",
}


@pytest.mark.parametrize("name", SOURCES)
def test_a_source_audit_case_matches_the_compiler(
    name: str, tmp_path: Path, python_dump_binary: Path
) -> None:
    source = SOURCES[name]
    rels = _write(tmp_path, {"p.py": source})
    found = _native(python_dump_binary, tmp_path, rels)["p.py"]
    assert (found is not None) == compiler_refuses(source), (name, found)

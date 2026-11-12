# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The native definition table equals the symbols of the Python collector (AD-377, slice 2a).

The oracle is the unmodified `collect.collect` in the phase `collect`, encoded as the facts of
protocol 9. The test keeps the records of the kinds `class`, `function` and `method` and the
fields in `DECIDED`: the fields that the module itself decides. The other fields need the binding
proofs, the class kinds or another module; AD-377 lists them. The evidence that a record cites is
compared too. The reply does not carry these records yet (AD-334 point 8).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from first_difference import same
from test_collector_native_python_scope import _FIXTURES

from archkeel.analyzer.interpreter import interpreter, python_request
from archkeel.analyzer.python.collect import collect
from archkeel.cli.config import load_config
from archkeel.ir import facts_codec
from archkeel.ir.facts import EXTENDED_CALL_BINDINGS_FEATURE
from archkeel.ir.protocol import (
    CollectionError,
    CollectionRequest,
    ProtocolVersion,
    PythonCollectionPhase,
    PythonSettings,
    SnapshotInput,
    SourceScope,
)

ROOT = Path(__file__).parents[1]
KINDS = {"class", "function", "method"}
DECIDED = (
    "qualified_name",
    "module",
    "package",
    "name",
    "visibility",
    "visibility_detail",
    "declared_in_all",
    "parent",
    "decorators",
    "namespace_bound",
    "lexical_parent_id",
    "definition_contexts",
    "symbol_category",
    "parameters",
    "receiver_parameter",
    "returns",
    "async",
    "parameters_contained",
    "stored_field_writes",
    "shape",
    "shape_nodes",
    "bases",
    "fields",
    "attribute_declarations",
    "class_members",
    "instance_member_writes",
    "instance_member_scope_evidence_id",
    "generic_bases",
    "guard_boolean_members",
)
_HEADER = ("id", "evidence_class", "area", "kind", "title", "subjects", "evidence_ids")
_CITES = {"evidence_id", "annotation_evidence_id", "instance_member_scope_evidence_id"}


def _request(
    root: Path, roots: tuple[str, ...], namespace: str, exclude: bool, witnesses: bool
) -> CollectionRequest:
    features = (EXTENDED_CALL_BINDINGS_FEATURE,) if witnesses else ()
    return CollectionRequest(
        SnapshotInput(str(root.resolve()), "a" * 40, False),
        SourceScope(roots, namespace, exclude),
        PythonSettings(phase=PythonCollectionPhase.COLLECT, features=features),
        ProtocolVersion.V9,
    )


def _cited(value: Any, found: set[str]) -> set[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "evidence_ids":
                found.update(item)
            elif key in _CITES and isinstance(item, str):
                found.add(item)
            else:
                _cited(item, found)
    elif isinstance(value, list):
        for item in value:
            _cited(item, found)
    return found


def _python(request: CollectionRequest) -> dict[str, Any]:
    facts = collect(request)
    version = ProtocolVersion.V9
    payload = facts_codec._facts_payload(
        facts, version, facts_codec._runtime_payload(facts.runtime, version)
    )
    records = next(item["records"] for item in payload["sections"] if item["name"] == "symbols")
    symbols = [
        {
            **{key: record[key] for key in _HEADER},
            "data": {key: record["data"][key] for key in DECIDED if key in record["data"]},
        }
        for record in records
        if record["kind"] in KINDS
    ]
    cited = _cited(symbols, set())
    evidence = [item for item in payload["evidence"] if item["id"] in cited]
    return {"symbols": symbols, "evidence": evidence}


def _native(binary: Path, request: CollectionRequest, witnesses: bool) -> dict[str, Any]:
    block = interpreter()
    assert not isinstance(block, CollectionError), block
    survey = CollectionRequest(
        request.snapshot,
        request.scope,
        PythonSettings(phase=PythonCollectionPhase.IMPORTS),
        request.protocol_version,
    )
    completed = subprocess.run(
        [str(binary), "--dump-symbols", "1" if witnesses else "0"],
        input=python_request(survey, block),
        capture_output=True,
        check=True,
    )
    found: dict[str, Any] = json.loads(completed.stdout)
    cited = _cited(found["symbols"], set())
    found["evidence"] = [item for item in found["evidence"] if item["id"] in cited]
    return found


def _text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _equal(
    binary: Path, root: Path, roots: tuple[str, ...], namespace: str, *, both: bool = True
) -> int:
    count = 0
    for exclude in (False, True) if both else (False,):
        for witnesses in (False, True):
            request = _request(root, roots, namespace, exclude, witnesses)
            expected, found = _python(request), _native(binary, request, witnesses)
            assert found["gaps"] == [], found["gaps"]
            for section in ("symbols", "evidence"):
                label = (root.name, exclude, witnesses, section)
                same(_text(found[section]), _text(expected[section]), label)
            count += len(found["symbols"])
    return count


def _tree(root: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")
    return root


@pytest.mark.parametrize("fixture", _FIXTURES)
def test_each_fixture_has_the_python_definition_table(
    fixture: str, python_dump_binary: Path
) -> None:
    root = ROOT / fixture
    config = load_config(root)
    _equal(python_dump_binary, root, config.roots, config.namespace)


def test_the_archkeel_source_has_the_python_definition_table(python_dump_binary: Path) -> None:
    assert _equal(python_dump_binary, ROOT, ("src",), "archkeel", both=False) > 4000


@pytest.mark.skipif(
    not os.environ.get("ARCHKEEL_PYTHON_SCOPE_CORPORA"), reason="no corpus is named"
)
def test_each_named_corpus_has_the_python_definition_table(python_dump_binary: Path) -> None:
    for entry in os.environ["ARCHKEEL_PYTHON_SCOPE_CORPORA"].split(";"):
        root, namespace, roots = entry.split("=")
        _equal(python_dump_binary, Path(root), tuple(roots.split(",")), namespace)


# Each probe is the module `app/probe.py`. The Python collector decides; a probe has no expected
# value of its own.
PROBES: dict[str, str] = {
    "shadowing": "def f(): pass\ndef f(): pass\nclass C: pass\nclass C: pass\nf = 1\n",
    "conditional": (
        "import sys\nif sys.version_info >= (3, 12):\n    def f(): pass\n"
        "elif sys.platform == 'x':\n    def f(): pass\nelse:\n    class f: pass\n"
    ),
    "loops": (
        "for a in b:\n    def f(): pass\nelse:\n    def g(): pass\n"
        "while c:\n    class W: pass\nelse:\n    def h(): pass\n"
        "async def k():\n    async for a in b:\n        def i(): pass\n"
        "    async with c as d:\n        def j(): pass\n"
    ),
    "try": (
        "try:\n    def f(): pass\nexcept (A, B) as e:\n    def g(): pass\n"
        "except C:\n    class H: pass\nelse:\n    def i(): pass\nfinally:\n    def j(): pass\n"
    ),
    "try-star": "try:\n    pass\nexcept* A:\n    def f(): pass\n",
    "match": (
        "match x:\n    case [a, *rest] if a:\n        def f(): pass\n"
        "    case {'k': v, **kw}:\n        class C: pass\n    case P(a, b=c) | None:\n"
        "        def g(): pass\n    case _:\n        def h(): pass\n"
    ),
    "with": "with a as b, c:\n    def f(): pass\n    with d:\n        class C: pass\n",
    "delete": "class C:\n    a = 1\n    b: int = 2\n    del a\n    def m(self): pass\n    del m\n",
    "star-import-all": (
        "from os.path import *\n__all__ = ['f', 'C']\n__all__ += ['g']\n"
        "def f(): pass\ndef g(): pass\nclass C: pass\n"
    ),
    "all-tuple": "__all__ = ('f',)\ndef f(): pass\ndef _p(): pass\ndef __dunder__(): pass\n",
    "all-edits": "__all__ = ['a']\n__all__.append('f')\n__all__.extend(['g'])\ndef f(): pass\n",
    "decorators": (
        "import functools\n@functools.lru_cache(maxsize=None)\n@staticmethod\n@a.b.c\n"
        "@(lambda f: f)\n@x[0]\ndef f(): pass\n@dataclass(frozen=True)\nclass D: pass\n"
    ),
    "decorator-comment": "@a\n# comment\n\n@b  # c\n\\\ndef f(): pass\n@c\n\n\nclass C: pass\n",
    "class-body": (
        "class C(B, metaclass=M):\n    '''doc'''\n    x: int = 1\n    y = z = 2\n"
        "    (p, q), r = s\n    _priv: str\n    __dunder__ = 3\n    t: 'C'\n"
        "    import os, os.path as op\n    from a import b as c, d\n"
        "    lit = 'text'\n    blit: str = 'b'\n    class Inner: pass\n"
    ),
    "nested-functions": (
        "def outer(a, b=1):\n    def inner(c):\n        def deepest(): pass\n"
        "        class Local: pass\n    return inner\n"
    ),
    "methods": (
        "class C:\n    def m(self, a, /, b, *args, c=1, **kw) -> 'C': ...\n"
        "    @staticmethod\n    def s(): ...\n    @classmethod\n    def k(cls): ...\n"
        "    @property\n    def p(self) -> int: return 1\n    async def a(self): ...\n"
        "    class N:\n        def n(self): ...\n"
    ),
    "init-writes": (
        "class C:\n    def __init__(self, a: int, b, /, c: 'T', *d, e, **f):\n"
        "        self.a = a\n        self.b: int = b\n        other.c = c\n        self.d = d\n"
        "        self.e = e\n        x = self.y = a\n        if a:\n            self.z = a\n"
        "def __init__(self, a):\n    self.a = a\n"
    ),
    "member-writes": (
        "class C:\n    def a(self):\n        self.x = 1\n        del self.y\n"
        "        setattr(self, 'z', 1)\n        delattr(self, name)\n    def b(this):\n"
        "        other = this\n        other.w = 1\n        f(this)\n    def c(self):\n"
        "        self[0] = 1\n        return self\n    def d(self):\n        def g(): self\n"
        "    def e(self):\n        yield self\n        x = [self]\n        y: object = self\n"
        "    def f(self):\n        lam = lambda: self\n    def g():\n        pass\n"
    ),
    "guard-booleans": (
        "class C:\n    ok: bool\n    flag: bool = False\n    flag: bool = True\n"
        "    other: 'bool'\n    def __init__(self):\n        self.ready: bool = False\n"
        "        if x:\n            self.done: bool = True\n        self.ok: bool = True\n"
        "    def m(this):\n        this.seen: bool = False\n        that.no: bool = False\n"
    ),
    "generic-bases": (
        "from typing import Generic, TypeVar\nT = TypeVar('T')\n"
        "class A(Generic[T]): pass\nclass B(dict[str, int], A[T]): pass\n"
        "class C(x.y[(1, 2)], z[lambda: 1]): pass\n"
    ),
    "global-nonlocal": (
        "def f():\n    global g\n    def g(): pass\n    x = 1\n    def h():\n"
        "        nonlocal x\n        def i(): pass\n"
    ),
    "walrus": "if (f := 1):\n    def f(): pass\nclass C:\n    [y := 1]\n    def m(self): pass\n",
    "parameters-contained": (
        "def a(x, y):\n    return x == y\ndef b(x):\n    return d[x]\ndef c(x):\n    d[x] = 1\n"
        "def e(x):\n    return x\ndef g(x):\n    if x in y: pass\ndef h(*a, **k):\n    a < k\n"
        "def i(x):\n    lambda: x == 1\ndef j(x):\n    del d[x]\ndef k(x):\n    f'{x}'\n"
    ),
    "shape": (
        "def a():\n    '''doc'''\n    return 1 + 2\ndef b():\n    return x * y\n"
        "def c():\n    1\n    return f'{a!r:>{b}}'\ndef d():\n    b'doc'\n"
        "def e():\n    ...\ndef g():\n    match x:\n        case [1, *r] | {'a': 1}: pass\n"
    ),
    "unicode-nfkc": (
        "def ﬁle(): pass\nclass Ｃ: pass\ndef \u00e9t\u00e9(): pass\nclass _Ünder: pass\n"
    ),
    "unicode-strings": (
        "class C:\n    a = '\\u0cf3'\n    b = 'é'\n    c = '\\x00\\t'\n"
        "def f(x='\\U0001e4d0', y=b'\\xff'): pass\n"
    ),
    "type-annotations": (
        "def f(a: 'int | None', b: list[int] = [], *, c: dict[str, 'C'] = {}) -> 'tuple[int, ...]':"
        " ...\nclass C:\n    x: Literal['a', 'b']\n    y: Annotated[int, 'meta'] = 0\n"
    ),
    "defaults": (
        "def f(a=1, b=-1, c=1e16, d=0x10, e=..., f=None, g=(1,), h=lambda: 0, i=a.b(c)): pass\n"
    ),
    "async-generator": (
        "async def f():\n    async def g(): yield\n    await h()\n    def i(): return (yield)\n"
    ),
    "class-in-function-in-class": (
        "class A:\n    def m(self):\n        class B:\n            def n(self): pass\n"
        "        return B\n    class C:\n        class D:\n            def o(self): pass\n"
    ),
    "if-type-checking": (
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    class P: pass\n"
        "    def f(): pass\n"
    ),
    "empty-and-docstring": "'''module doc'''\nclass C:\n    '''only doc'''\ndef f():\n    pass\n",
    "long-class": "class Big:\n" + "".join(f"    a{i} = {i}\n" for i in range(3000)),
    "semicolons-and-continuations": (
        "def f(): pass; x = 1\nclass C: a = 1; b = 2\ndef \\\n  g(): pass\n"
    ),
    "crlf": "class Cr:\r\n    def m(self):\r\n        self.x = 1\r\n",
}


def _probe(binary: Path, root: Path, source: str) -> None:
    _tree(root, {"src/app/__init__.py": "", "src/app/probe.py": source})
    _equal(binary, root, ("src",), "app", both=False)


@pytest.mark.parametrize(("name", "source"), sorted(PROBES.items()))
def test_each_probe_has_the_python_definition_table(
    name: str, source: str, tmp_path: Path, python_dump_binary: Path
) -> None:
    _probe(python_dump_binary, tmp_path / name, source)


def test_a_newer_construct_has_the_python_definition_table(
    tmp_path: Path, python_dump_binary: Path
) -> None:
    """Generics of 3.12 and type defaults of 3.13. On an older version CPython refuses the file,
    and both producers leave it out with a syntax failure."""
    probes = {
        "generic-def": (
            "def f[T: int, *Ts, **P](a: T, *b: *Ts) -> T: ...\n"
            "class C[T](Base[T]):\n    def m[S](self, s: S) -> T: ...\n"
            "type Alias[T] = list[T]\n"
        ),
        "type-default": "def f[T = int](): pass\nclass D[T = str]: pass\n",
        "tstring-default": "def f(a=t'{x}'): pass\n",
        "except-without-parens": "try:\n    pass\nexcept A, B:\n    def f(): pass\n",
    }
    for name, source in probes.items():
        _probe(python_dump_binary, tmp_path / name, source)


def _gaps(binary: Path, root: Path) -> list[dict[str, str]]:
    request = _request(root, ("src",), "app", False, True)
    found = _native(binary, request, True)
    assert all(record["data"]["module"] != "app.probe" for record in found["symbols"])
    gaps: list[dict[str, str]] = found["gaps"]
    return gaps


def test_a_deep_default_is_a_named_gap_of_the_module(
    tmp_path: Path, python_dump_binary: Path
) -> None:
    """AD-377: over `unparse::MAX_DEPTH` levels native writes a gap; Python can stop with
    `RecursionError` there, so no verdict of either producer is a PASS."""
    deep = " + ".join(["a"] * 150)
    root = _tree(
        tmp_path, {"src/app/__init__.py": "", "src/app/probe.py": f"def f(x={deep}): pass\n"}
    )
    gaps = _gaps(python_dump_binary, root)
    assert [gap["file"] for gap in gaps] == ["src/app/probe.py"]
    assert "RecursionError" in gaps[0]["reason"]


def test_a_surrogate_escape_is_a_named_gap_of_the_module(
    tmp_path: Path, python_dump_binary: Path
) -> None:
    """AD-377: ruff replaces a lone surrogate escape, so native cannot write the text of
    CPython. The module gets a gap instead of a record with another value (stricter)."""
    source = "class C:\n    x = '\\ud800'\n"
    root = _tree(tmp_path, {"src/app/__init__.py": "", "src/app/probe.py": source})
    gaps = _gaps(python_dump_binary, root)
    assert [gap["file"] for gap in gaps] == ["src/app/probe.py"]
    assert "surrogate" in gaps[0]["reason"]
    # The other modules keep their records: the gap is for the module only.
    python = _python(_request(root, ("src",), "app", False, True))
    assert any(record["title"] == "C" for record in python["symbols"])

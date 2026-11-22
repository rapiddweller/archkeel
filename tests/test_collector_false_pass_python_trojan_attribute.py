# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1967: a computed attribute name on an unproved receiver is a trojan horse, never PASS.

A trojan horse is a place that can load code the scan does not see; it is not a claim of malice.
Consumer: `archkeel validate`. `app.consumer` may not depend on `app.lib`. Each plant reads the
`__code__` of a function through `getattr`, `setattr` or `__getattribute__` with a name that the
scan cannot read, and Python 3.12 then imports `app.lib`. The rule must be UNKNOWN or FAIL. A
control with a project class, a literal name, a module receiver or a declared site clears.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from core_support import run
from python_interface_plants import Plant, build
from rust_repository import rule

from archkeel.cli import core_only

pytestmark = pytest.mark.skipif(shutil.which("python3.12") is None, reason="Python is the oracle")

EDIT = "tuple('app.lib' if n == 'json' else n for n in code.co_names)"
HEAD = "def f():\n    import json\n    return json\n\nname = {name}\n"
TAIL = "code = {read}\nsetattr(f, name, code.replace(co_names=" + EDIT + "))\nf()\n"
PLANTS = {
    "joined-getattr": ("'__co' + 'de__'", "getattr(f, name)"),
    "getattribute": ("''.join(['__c', 'ode__'])", "f.__getattribute__(name)"),
    "variable-name": ("''.join(['__c', 'ode__'])", "getattr(f, name)"),
    "reversed-name": ("'__edoc__'[::-1]", "getattr(f, name)"),
    "dir-filter": ("[n for n in dir(f) if n.startswith('__co')][0]", "getattr(f, name)"),
}
# AD-1058: plants of the independent review of #1968. CPython 3.12 imports `app.lib` in each one.
F = "def f():\n    import json\n    return json\n\n"
NAME = "name = '__co' + 'de__'\n"
PUT = "code.replace(co_names=" + EDIT + ")"
BUILTINS_IMPORT = "b = d['__bui' + 'ltins__']\nb['__imp' + 'ort__']('app.lib')\n"
W = "(f, name, " + PUT + ")\nf()\n"
FULL = {
    # AD-1058: no class is a proven receiver. A decorator returns another object; a store through
    # an alias of the module replaces the class.
    "class-decorator": (
        "def d(c):\n    return globals()['f']\n\n\n" + F + "@d\nclass C: ...\n\n\n"
        "def r(n):\n    return getattr(C, n)\n\n\n"
        + NAME
        + "code = r(name)\nsetattr(C, name, "
        + PUT
        + ")\nf()\n"
    ),
    "class-replaced-through-alias": (
        "import app.consumer as me\n\n\nclass C: ...\n\n\n"
        + F
        + NAME
        + "me.C = f\ncode = getattr(C, name)\nsetattr(C, name, "
        + PUT
        + ")\nf()\n"
    ),
    # AD-1058: a reference to an access form that is no direct call is a site.
    "alias": "g = getattr\ns = setattr\n" + F + NAME + "code = g(f, name)\ns" + W,
    "bound-method": (
        F
        + NAME
        + "ga = f.__getattribute__\nsa = f.__setattr__\ncode = ga(name)\nsa(name, "
        + PUT
        + ")\nf()\n"
    ),
    "attrgetter": (
        "import operator\nsa = f = None\n"
        + F
        + NAME
        + "code = operator.attrgetter('__co' + 'de__')(f)\nobject.__setattr__"
        + W
    ),
    "attrgetter-literal": (
        "import operator\ns = setattr\n"
        + F
        + "code = operator.attrgetter('__code__')(f)\ns(f, '__code__', "
        + PUT
        + ")\nf()\n"
    ),
    "map": F
    + NAME
    + "code = list(map(getattr, [f], [name]))[0]\nlist(map(setattr, [f], [name], ["
    + PUT
    + "]))\nf()\n",
    "partial": (
        "import functools\n" + F + NAME + "code = functools.partial(getattr, f)(name)\n"
        "functools.partial(setattr, f, name)(" + PUT + ")\nf()\n"
    ),
    # `vars(x)` and `x.__dict__` hand out every attribute; the key is computed later.
    "vars-bound": "import json\nd = vars(json)\n" + BUILTINS_IMPORT,
    "dict-bound": "import json\nd = json.__dict__\n" + BUILTINS_IMPORT,
    "vars-subscript": (
        "import json\nn = '__bui' + 'ltins__'\nb = vars(json)[n]\nb['__imp' + 'ort__']('app.lib')\n"
    ),
    # The members of a function hold its code object without its name.
    "getmembers": (
        "import inspect\n" + F + "members = inspect.getmembers(f)\n"
        "code = [v for n, v in members if n.endswith('code__')][0]\n"
        "g = type(f)(" + PUT + ", {})\ng()\n"
    ),
    "referents": (
        "import gc\n" + F + "code = [c for c in gc.get_referents(f) if hasattr(c, 'co_names')][0]\n"
        "g = type(f)(" + PUT + ", {})\ng()\n"
    ),
    # AD-1058: each module has `__builtins__`, so a module is no proven receiver.
    "module-builtins": (
        "import json\n\n\ndef read(n):\n    return getattr(json, n)\n\n\n"
        "b = read('__bui' + 'ltins__')\nb['__imp' + 'ort__']('app.lib')\n"
    ),
    "module-builtins-alias": (
        "import os.path as m\n\n\ndef read(n):\n    return getattr(m, n)\n\n\n"
        "b = read('__bui' + 'ltins__')\nb['__imp' + 'ort__']('app.lib')\n"
    ),
    "loaded-module-builtins": (
        "def read(n):\n    m = __import__('json')\n    return getattr(m, n)\n\n\n"
        "b = read('__bui' + 'ltins__')\nb['__imp' + 'ort__']('app.lib')\n"
    ),
    # `C.get(f, name)` calls the method through the class with any first argument.
    "unbound-self": (
        "class C:\n    def get(self, n):\n        return getattr(self, n)\n\n"
        "    def put(self, n, v):\n        setattr(self, n, v)\n\n\n"
        + F
        + NAME
        + "code = C.get(f, name)\nC.put(f, name, "
        + PUT
        + ")\nf()\n"
    ),
    "unbound-cls": (
        "class C:\n    @classmethod\n    def get(cls, n):\n        return getattr(cls, n)\n\n\n"
        + F
        + NAME
        + "code = C.get.__func__(f, name)\nsetattr(f, name, "
        + PUT
        + ")\nf()\n"
    ),
    # A parameter of a lambda or of a nested function rebinds the loaded name.
    "lambda-loaded": (
        "def r(obj, n):\n    m = __import__('json')\n"
        "    return (lambda m: getattr(m, n))(obj)\n\n\n"
        + F
        + NAME
        + "code = r(f, name)\nsetattr(f, name, "
        + PUT
        + ")\nf()\n"
    ),
    "nested-self": (
        "class C:\n    def put(self, obj, n, v):\n        def inner(self):\n"
        "            setattr(self, n, v)\n        inner(obj)\n\n\n"
        + F
        + NAME
        + "code = getattr(f, name)\nC().put(f, name, "
        + PUT
        + ")\nf()\n"
    ),
    # The unbound form `C.__getattribute__(x, n)` has the receiver `x`.
    "class-getattribute": (
        "class C:\n    pass\n\n\n"
        + F
        + NAME
        + "code = C.__getattribute__(f, name)\nobject.__setattr__(f, name, "
        + PUT
        + ")\nf()\n"
    ),
    "class-setattr": (
        "class C:\n    pass\n\n\n"
        + F
        + NAME
        + "code = f.__getattribute__(name)\nC.__setattr__(f, name, "
        + PUT
        + ")\nf()\n"
    ),
    # A name that one literal binds and a loop rebinds is no literal name.
    "literal-rebound-by-loop": (
        "def r(obj, names):\n    n = 'a'\n    for n in names:\n        pass\n"
        "    return getattr(obj, n)\n\n\n"
        "def w(obj, names, v):\n    n = 'a'\n    for n in names:\n        pass\n"
        "    setattr(obj, n, v)\n\n\n"
        + F
        + NAME
        + "code = r(f, [name])\nw(f, [name], "
        + PUT
        + ")\nf()\n"
    ),
    "literal-rebound-by-with": (
        "import contextlib\n\n\ndef r(obj, other):\n    n = 'a'\n    with other as n:\n"
        "        pass\n    return getattr(obj, n)\n\n\n"
        "def w(obj, other, v):\n    n = 'a'\n    with other as n:\n        pass\n"
        "    setattr(obj, n, v)\n\n\n" + F + NAME + "code = r(f, contextlib.nullcontext(name))\n"
        "w(f, contextlib.nullcontext(name), " + PUT + ")\nf()\n"
    ),
    "match-capture": (
        "def r(obj, n):\n    m = __import__('json')\n    match obj:\n        case m:\n"
        "            return getattr(m, n)\n\n\n"
        + F
        + NAME
        + "code = r(f, name)\nsetattr(f, name, "
        + PUT
        + ")\nf()\n"
    ),
    "for-target": (
        "def r(obj, n):\n    m = __import__('json')\n    for m in (obj,):\n        pass\n"
        "    return getattr(m, n)\n\n\n"
        + F
        + NAME
        + "code = r(f, name)\nsetattr(f, name, "
        + PUT
        + ")\nf()\n"
    ),
}
# AD-1058: a stored annotation hands the class back, so code reads it and calls it.
BYTES = "bytes([151, 0, 100, 0, 100, 1, 108, 0, 1, 0, 121, 1])"
BUILD = f"(0, 0, 0, 0, 2, 0, {BYTES}, (0, None), ('app.lib',), (), 'x', 'x', 'x', 1, b'', b'')"
ANNOTATED = {
    "class-annotation": (
        "import types\n\n\nclass H:\n    code: types.CodeType\n"
        "    function: types.FunctionType\n\n\n"
        f"hints = H.__annotations__\nc = hints['code']{BUILD}\nhints['function'](c, " + "{})()\n"
    ),
    "parameter-annotation": (
        "import types\n\n\ndef h(code: types.CodeType, function: types.FunctionType): ...\n\n\n"
        f"hints = h.__annotations__\nc = hints['code']{BUILD}\nhints['function'](c, " + "{})()\n"
    ),
    "module-annotation": (
        "import types\n\ncode: types.CodeType\nfunction: types.FunctionType\n\n"
        f"hints = __annotations__\nc = hints['code']{BUILD}\nhints['function'](c, " + "{})()\n"
    ),
}
FULL |= ANNOTATED
CONTROLS = {
    "literal-name": "def f():\n    return 1\n\nNAME = getattr(f, '__name__')\n",
    "local-literal": "def f():\n    n = '__name__'\n    return getattr(f, n)\n",
    "local-annotation": (
        "import types\n\ndef f(x):\n    code: types.CodeType = x\n"
        "    return isinstance(x, types.CodeType)\n"
    ),
}
SITES = {"builtins": "import builtins\n\ndef read(n):\n    return getattr(builtins, n)\n"}


def _root(tmp: Path, source: str, version: str = "2.2.0", declared: list | None = None) -> Path:
    root = tmp / "repo"
    root.mkdir(parents=True)
    build(root, Plant("trojan", source, ("app.lib",), {"src/app/lib/__init__.py": "value = 1\n"}))
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    forbidden = rule("NO-LIB", "forbidden_dependency", source="app.consumer", target="app.lib")
    forbidden["include_type_checking"] = True
    forbidden["provenance"] = ["docs/target.md"]
    contract["rules"] = [forbidden]
    if declared is not None:
        contract["schema_version"] = version
        contract["declarations"] = {"trojan_horse_reach": declared}
    path.write_text(json.dumps(contract))
    return root


def _loads_lib(root: Path) -> bool:
    code = (
        "import sys; sys.path.insert(0, 'src'); import app.consumer; "
        "print('app.lib' in sys.modules)"
    )
    done = subprocess.run(
        ["python3.12", "-I", "-c", code], cwd=root, capture_output=True, text=True
    )
    return done.stdout.strip() == "True"


def _verdict(root: Path, core: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    monkeypatch.setattr(core_only, "locate_core", lambda: core)
    return run("validate", "--root", str(root))[1]


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_a_computed_name_that_reaches_a_code_object_is_never_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    value, read = PLANTS[name]
    root = _root(tmp_path, HEAD.format(name=value) + TAIL.format(read=read))
    assert _loads_lib(root), "CPython must import app.lib: the plant is real"
    frame = _verdict(root, release_core, monkeypatch)["frame"]

    assert frame["rules"]["NO-LIB"][1] in {"FAIL", "UNKNOWN"}, frame


@pytest.mark.parametrize("name", sorted(FULL))
def test_a_review_plant_that_imports_the_module_is_never_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    root = _root(tmp_path, FULL[name])
    assert _loads_lib(root), "CPython must import app.lib: the plant is real"
    frame = _verdict(root, release_core, monkeypatch)["frame"]

    assert frame["rules"]["NO-LIB"][1] in {"FAIL", "UNKNOWN"}, frame


@pytest.mark.parametrize("name", sorted(CONTROLS))
def test_a_receiver_or_name_that_the_scan_proves_clears(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    root = _root(tmp_path, CONTROLS[name])
    assert not _loads_lib(root), "CPython must leave app.lib unloaded: the control is clean"
    frame = _verdict(root, release_core, monkeypatch)["frame"]

    assert frame["rules"]["NO-LIB"][1] == "PASS", frame


def test_a_declared_trojan_horse_site_passes_under_its_declaration(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = "def read(n):\n    return getattr(read, n)\n"
    root = _root(tmp_path / "a", source)
    assert not _loads_lib(root)
    frame = _verdict(root, release_core, monkeypatch)["frame"]
    assert frame["rules"]["NO-LIB"][1] == "UNKNOWN", frame

    declared = [
        {
            "id": "T-1",
            "module": "app.consumer",
            "name": "getattr",
            "line": 2,
            "loads": [],
            "changes": [],
            "rationale": "The name comes from a fixed table of the product.",
            "provenance": ["docs/target.md"],
        }
    ]
    root = _root(tmp_path / "b", source, "3.20.0", declared)
    frame = _verdict(root, release_core, monkeypatch)["frame"]
    assert frame["rules"]["NO-LIB"][1] == "PASS", frame
    assert frame["trojan_horse_reach"][0]["id"] == "T-1", frame

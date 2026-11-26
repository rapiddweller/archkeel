# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#2090: a write of an exception-chain name stays a loader site, never a silent PASS.

The scan reads no type. A write of `__cause__`, `__context__`, `__traceback__`,
`__suppress_context__` or `__notes__` can run project code with no hook name in sight: a hook bound
by assignment in a class body, a metaclass, a computed name in `type()`, a `__str__` or a finalizer
of the written value. Two exemptions (#2092, #2102) were unsound for this reason. CPython 3.12 runs
each plant (a counter file), so the scan must not say PASS.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from test_collector_false_pass_python_trojan_attribute import _root, _verdict

pytestmark = pytest.mark.skipif(shutil.which("python3.12") is None, reason="Python is the oracle")

RUN = "open('counter.txt', 'a').write('hooked')"
PAD = "def _pad():\n    pass\n\n"
VENDOR = "class Base(Exception):\n    def __setattr__(self, n, v):\n        " + RUN + "\n"


def _code(*lines: str) -> str:
    return "\n".join(lines).replace("RUN", RUN) + "\n"


PLANTS = {
    "A-body-assign-setattr": _code(
        "def h(self, n, v):",
        "    RUN",
        "class K:",
        "    __setattr__ = h",
        "K().__cause__ = 1",
    ),
    "A2-lambda-setattr": _code(
        "class K:",
        "    __setattr__ = lambda self, n, v: RUN",
        "K().__cause__ = 1",
    ),
    "A3-annassign": _code(
        "def h(self, n, v):",
        "    RUN",
        "class K:",
        "    __setattr__: object = h",
        "K().__cause__ = 1",
    ),
    "B-body-assign-delattr": _code(
        "def h(self, n):",
        "    RUN",
        "class K:",
        "    __delattr__ = h",
        "k = K()",
        "del k.__cause__",
    ),
    "B2-descriptor-set-assigned": _code(
        "def h(self, o, v):",
        "    RUN",
        "class D:",
        "    __set__ = h",
        "class K:",
        "    __cause__ = D()",
        "K().__cause__ = 1",
    ),
    "D-cause-str-traceback": _code(
        "class Evil(Exception):",
        "    def __str__(self):",
        "        RUN",
        "        return 'x'",
        "e = ValueError('a')",
        "e.__cause__ = Evil()",
        "raise e",
    ),
    "E-notes-str": _code(
        "class N:",
        "    def __str__(self):",
        "        RUN",
        "        return 'n'",
        "import traceback",
        "e = ValueError('a')",
        "e.__notes__ = [N()]",
        "traceback.format_exception(e)",
    ),
    "F-notes-iadd-nonlist": _code(
        "class N:",
        "    def __iadd__(self, o):",
        "        RUN",
        "        return self",
        "e = ValueError('a')",
        "e.__notes__ = N()",
        "e.__notes__ += ['x']",
    ),
    "G-userlist-attr-base": _code(
        "import collections",
        "class L(collections.UserList):",
        "    def __iadd__(self, o):",
        "        RUN",
        "        return self",
        "e = ValueError('a')",
        "e.__notes__ = L()",
        "e.__notes__ += ['x']",
    ),
    "H-list-alias-base": _code(
        "Base = list",
        "class L(Base):",
        "    def __iadd__(self, o):",
        "        RUN",
        "        return self",
        "e = ValueError('a')",
        "e.__notes__ = L()",
        "e.__notes__ += ['x']",
    ),
    "H2-builtins-list-attr": _code(
        "import builtins",
        "class L(builtins.list):",
        "    def __iadd__(self, o):",
        "        RUN",
        "        return self",
        "e = ValueError('a')",
        "e.__notes__ = L()",
        "e.__notes__ += ['x']",
    ),
    "I-weakref-finalize": _code(
        "import weakref",
        "class T:",
        "    pass",
        "def cb():",
        "    RUN",
        "t = T()",
        "weakref.finalize(t, cb)",
        "e = ValueError('a')",
        "e.__notes__ = t",
        "del t",
        "e.__notes__ = None",
    ),
    "J-generator-finally": _code(
        "def g():",
        "    try:",
        "        yield 1",
        "    finally:",
        "        RUN",
        "x = g()",
        "next(x)",
        "e = ValueError('a')",
        "e.__notes__ = x",
        "del x",
        "e.__notes__ = None",
    ),
    "K-type-concat": _code(
        "def h(self, n, v):",
        "    RUN",
        "E = type('E', (Exception,), {'__set' + 'attr__': h})",
        "E().__cause__ = None",
    ),
    "K2-type-lower": _code(
        "def h(self, n, v):",
        "    RUN",
        "E = type('E', (Exception,), {'__SETATTR__'.lower(): h})",
        "E().__cause__ = None",
    ),
    "K3-types-new_class": _code(
        "import types",
        "def h(self, n, v):",
        "    RUN",
        "E = types.new_class('E', (Exception,), {}, lambda ns: ns.update({'__set' + 'attr__': h}))",
        "E().__cause__ = None",
    ),
    "K4-init_subclass-computed": _code(
        "def h(self, n, v):",
        "    RUN",
        "class B(Exception):",
        "    def __init_subclass__(cls):",
        "        setattr(cls, '__set' + 'attr__', h)",
        "class E(B):",
        "    pass",
        "E().__cause__ = None",
    ),
    "L-vendor-base": _code(
        "import sys",
        "sys.path.insert(0, 'vendor')",
        "import thirdparty",
        "class E(thirdparty.Base):",
        "    pass",
        "E().__cause__ = None",
    ),
    "M-metaclass-assign": _code(
        "def h(cls, n, v):",
        "    RUN",
        "class M(type):",
        "    __setattr__ = h",
        "class K(metaclass=M):",
        "    pass",
        "K.__cause__ = 1",
    ),
    "N-nested-property": _code(
        "class K:",
        "    if True:",
        "        @property",
        "        def __cause__(self):",
        "            return 1",
        "        @__cause__.setter",
        "        def __cause__(self, v):",
        "            RUN",
        "K().__cause__ = 2",
    ),
    "N2-tuple-target-property": _code(
        "def g(self):",
        "    return 1",
        "def s(self, v):",
        "    RUN",
        "class K:",
        "    __cause__, other = property(g, s), 1",
        "K().__cause__ = 2",
    ),
    "N3-try-nested-property": _code(
        "def g(self):",
        "    return 1",
        "def s(self, v):",
        "    RUN",
        "class K:",
        "    try:",
        "        __cause__ = property(g, s)",
        "    except Exception:",
        "        pass",
        "K().__cause__ = 2",
    ),
}


def _runs_hook(root: Path) -> bool:
    code = "import sys; sys.path.insert(0, 'src'); import app.consumer"
    # A plant may raise after its hook ran: the run need not end well.
    subprocess.run(["python3.12", "-I", "-c", code], cwd=root, capture_output=True, check=False)
    return (root / "counter.txt").is_file()


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_a_chain_write_that_runs_project_code_is_never_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    root = _root(tmp_path, PAD + PLANTS[name])
    (root / "vendor").mkdir()
    (root / "vendor/thirdparty.py").write_text(VENDOR)
    assert _runs_hook(root), "CPython must run the hook"
    frame = _verdict(root, release_core, monkeypatch)["frame"]

    assert frame["rules"]["NO-LIB"][1] in {"FAIL", "UNKNOWN"}, frame

# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Fixed inputs pin the work of every binding traversal family (AD-396)."""

COSTS = {
    "namespace": (
        "list(globals().keys().keys())\n"
        "for name in globals(): pass\n"
        "'x' not in globals()\n"
        "[name for name in globals()]\n"
        "locals()\nvars(x)\n__import__('x')\n"
        "__annotations__\nf.f_globals\ntyping.get_type_hints(x)\n",
        4800,
    ),
    "globals": (
        "class C:\n"
        "    def f():\n"
        "        global x, alias\n"
        "        x = 1\n"
        "def outer(p, /, q=1, *args, r=2, **kw):\n"
        "    local = p\n"
        "    def inner():\n"
        "        nonlocal local\n"
        "        return local\n"
        "    del q\n"
        "    return inner\n",
        2137,
    ),
    "class-closure": (
        "import dataclasses\n"
        "x = alias\nalias = y.attr\nlocal = alias\nx = local\n"
        "@dataclasses.dataclass(frozen=True)\n"
        "class C(Base, metaclass=M):\n"
        "    A = 1\n    B: int = 2\n    del A\n"
        "    s = 'text'\n    _lambda = lambda x: x\n"
        "    model_config = pydantic.ConfigDict(frozen=True)\n"
        "    @overload\n    def m(self, value: int = 1) -> str:\n"
        "        unused = 2\n        return 'value'\n"
        "    class D:\n        _ignore_ = 'A'\n        A = 1\n",
        6238,
    ),
    "plain-class": (
        "class Plain:\n"
        "    def m(self, p):\n        spare = 1\n        return p\n"
        "class Imports:\n    import a.b\n    from a import b as c\n",
        1290,
    ),
    "binding-forms": (
        "import a.b as renamed\nfrom .a import b as imported\n"
        "a, (b, *rest) = seq\na += 1\nx: int = 2\nonly_annotation: str\n"
        "for x in seq:\n    alias = x\n"
        "with resource() as (x, alias): pass\n"
        "try:\n    x = 1\nexcept Error as alias:\n    del x\n"
        "match value:\n    case {'x': x, **mapping}: pass\n"
        "    case [*rest] as captured: pass\n"
        "x = [(alias := i) for i in seq if i]\n"
        "x = {k: v for k, v in seq}\n"
        "f = lambda x=1: x\n"
        "if value:\n    def conditional(): return 1\n",
        7893,
    ),
}

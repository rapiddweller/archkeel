# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Shapes of global scripts that stress each producer of the script facts (AD-340, PR 4.3a-4).

Python walks the subtree of a scope for each alias, each published member and each wrapper, so a
script with n of them costs n squared. Each shape here has n of one construct in one file (or in
one scope), and the facts of each must cost one lookup. `.js` files are global scripts.
"""

from __future__ import annotations

from scaling_shapes import Shape


def _each(template: str, n: int) -> str:
    return "".join(template.replace("{i}", str(i)) for i in range(n))


def _member_object(n: int) -> str:
    """One object that publishes n local functions: n lookups of a local definition."""
    names = ", ".join(f"f{i}" for i in range(n))
    return _each("function f{i}() {}\n", n) + f"window.Lib = {{ {names} }};\n"


def _factory_object(n: int) -> str:
    names = ", ".join(f"m{i}" for i in range(n))
    return "function make() { return { " + names + " }; " + _each("function m{i}() {}", n) + " }\n"


def _one_wrapper(n: int) -> str:
    return "(function (g) {\n" + _each("g.P{i} = { v: {i} };\n", n) + "})(window);\n"


SCRIPT_SHAPES: dict[str, Shape] = {
    "script-aliases": Shape(
        lambda n: _each("const a{i} = window.f{i};\na{i}();\n", n).encode(), 1500, ".js"
    ),
    "script-alias-factories": Shape(
        lambda n: _each("const m{i} = window.make{i}();\nm{i}.a();\nm{i}.b;\n", n).encode(),
        800,
        ".js",
    ),
    "script-destructures": Shape(
        lambda n: _each("const { a{i}, b{i} } = window.lib{i};\n", n).encode(), 2000, ".js"
    ),
    "script-namespaces": Shape(
        lambda n: _each(
            "var N{i};\n(function (N{i}) { N{i}.x = 1; })(N{i} || (N{i} = {}));\n", n
        ).encode(),
        1000,
        ".js",
    ),
    "script-wrappers": Shape(
        lambda n: _each(
            "(function (g) { g.P{i} = { f{i} }; function f{i}() {} })(window);\n", n
        ).encode(),
        1200,
        ".js",
    ),
    "script-one-wrapper": Shape(lambda n: _one_wrapper(n).encode(), 1500, ".js"),
    "script-source-members": Shape(lambda n: _member_object(n).encode(), 1500, ".js"),
    "script-factory-members": Shape(lambda n: _factory_object(n).encode(), 1500, ".js"),
    "script-write-paths": Shape(
        lambda n: _each(
            "const w{i} = window;\nw{i}.a.b = {i};\nvar v{i} = w{i};\nv{i}.c.d = 1;\n", n
        ).encode(),
        1200,
        ".js",
    ),
    "script-opaque-writes": Shape(
        lambda n: _each(
            "this.x{i} = 1;\neval('{i}');\nwindow['k' + {i}] = 2;\nf(window.o{i});\n", n
        ).encode(),
        1500,
        ".js",
    ),
    "script-top-level": Shape(
        lambda n: _each("var c{i} = {};\nc{i}.a = 1;\nc{i}.b.c = 2;\n", n).encode(), 2000, ".js"
    ),
}

# Each script fact of `Syntax` and the shapes that hold it.
SCRIPT_FIELD_COVERAGE: dict[str, tuple[str, ...]] = {
    "script_globals": ("script-one-wrapper", "script-wrappers", "script-source-members"),
    "script_writes": ("script-opaque-writes", "script-top-level"),
    "script_aliases": ("script-aliases", "script-alias-factories"),
    "script_factories": ("script-factory-members",),
    "script_source_writes": ("script-top-level", "script-write-paths"),
    "script_write_paths": ("script-write-paths",),
    "script_top_level_write_paths": ("script-top-level",),
    "script_destructures": ("script-destructures",),
    "script_namespaces": ("script-namespaces",),
}

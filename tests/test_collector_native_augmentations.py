# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Issue #976: the native collector reads module augmentations and script roots as Python does.

Consumer: `concerns.rs` and the script analysis. A relative augmentation name is a concern; a bare
one is a concern in a module file of a project that sets `paths` or `baseUrl`; a wildcard name is
none; `frames` and `self` are roots of the global object.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from test_collector_native_imports import COMMONJS, _differences, _request, _write

ALIASED = '{"compilerOptions":{"allowJs":true,"baseUrl":".","paths":{"@b/*":["src/b/*"]}}}'
AUGMENTATIONS = {
    "src/b/t.ts": "export type T = number;\n",
    # A module file: a bare name and a relative name are concerns; a wildcard name is not.
    "src/a/module.ts": 'export {};\ndeclare module "@b/t" {}\ndeclare module "./x" {}\n',
    "src/a/wildcard.ts": 'export {};\ndeclare module "*.css" {}\ndeclare module "@b/*" {}\n',
    # A script declares an ambient module: a bare name is no concern there.
    "src/a/script.d.ts": 'declare module "@b/t" {}\n',
    "src/a/module.d.ts": 'import type { T } from "../b/t";\ndeclare module "pkg" {}\n',
    "src/a/frames.js": "frames.x();\nself.y();\n",
    "src/b/b.js": "window.x = 1;\nwindow.y = 2;\n",
}


@pytest.mark.parametrize("config", [ALIASED, COMMONJS], ids=["aliased", "plain"])
def test_augmentation_names_equal_the_python_collector(
    tmp_path: Path, native_binary: Path, config: str
) -> None:
    _write(tmp_path, {**AUGMENTATIONS, "tsconfig.json": config})
    assert _differences(native_binary, _request(tmp_path, "app", "tsconfig.json")) == []


TYPE_ROOT = '{"compilerOptions":{"allowJs":true,"typeRoots":["./src"]},"include":["src"]}'
NODE_ROOT = (
    '{"compilerOptions":{"allowJs":true,"typeRoots":["./node_modules/@types"]},"include":["src"]}'
)
DIRECTIVES = {
    "src/b/index.d.ts": "declare var fromB: number;\n",
    "src/a/types.ts": '/// <reference types="b" />\nexport const a = fromB;\n',
    "src/a/path.ts": '/// <reference types="../b/index" />\nexport const p = 1;\n',
    "src/a/amd.ts": (
        '/// <amd-dependency path="../b/t" />\n/// <amd-dependency path="x" />\nexport {};\n'
    ),
    "src/a/amd-name.ts": (
        '/// <amd-dependency name="x" />\n/// <reference types="node" />\nexport {};\n'
    ),
    "src/a/late.ts": 'export {};\n/// <amd-dependency path="../b/t" />\n',
    # The attributes in any order and the names in any case, as tsc reads them (#988).
    "src/a/order.ts": (
        '/// <amd-dependency name="n" path="../b/t" />\n'
        '/// <reference preserve="true" path="../b/t.ts" />\n'
        '/// <AMD-DEPENDENCY PATH="../b/t" />\n'
        '/// <Reference LIB="dom" />\n'
        '/// <reference types="x" preserve="true" path="p" />\n'
        "/// <reference  path = 'q'  />\n"
        '/// <referencepath="z" />\n'
        "/// <amd-dependency path='unclosed />\n"
        "export {};\n"
    ),
    "src/a/roots.js": "top.x();\nparent.y();\nvar own = top;\n",
    "src/b/b.js": "window.x = 1;\nwindow.y = 2;\n",
}


@pytest.mark.parametrize(
    "config", [TYPE_ROOT, NODE_ROOT, COMMONJS], ids=["project", "node", "none"]
)
def test_directives_and_type_roots_equal_the_python_collector(
    tmp_path: Path, native_binary: Path, config: str
) -> None:
    _write(tmp_path, {**DIRECTIVES, "tsconfig.json": config})
    assert _differences(native_binary, _request(tmp_path, "app", "tsconfig.json")) == []


CHAIN_FILES = {
    "src/b/b.js": "window.x = 1;\nwindow.y = 2;\n",
    # A use through a chain of aliases of the global object, as a call, a read, a value and a path
    # with a name that no file publishes (#1007).
    "src/a/chains.js": (
        "window.window.x();\nself.window.y;\nglobalThis.window.x();\nwindow.self.y();\n"
        "window.globalThis.x();\ntop.window.x();\nparent.top.y;\nframes.self.window.nobody();\n"
        "var w = window.window;\nfoo(window.self);\nvar o = { v: top.parent };\n"
        "window.window.x.z;\nwindow.window;\nwindow.window[name]();\n"
    ),
    # A local variable named like a root is no root: no gap, as before.
    "src/a/locals.js": "function f(parent, top) { parent.appendChild(top); }\n",
}


def test_chains_of_global_object_aliases_equal_the_python_collector(
    tmp_path: Path, native_binary: Path
) -> None:
    _write(tmp_path, {**CHAIN_FILES, "tsconfig.json": COMMONJS})
    assert _differences(native_binary, _request(tmp_path, "app", "tsconfig.json")) == []

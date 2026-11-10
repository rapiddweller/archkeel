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

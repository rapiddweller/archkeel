# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The standard-global catalog follows the compiler's own lib files for each `lib` and target."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from test_typescript_standard_globals import _environment

from archkeel.analyzer.typescript.config import standard_globals
from archkeel.analyzer.typescript.standard_libs import (
    LIB_GLOBALS,
    TYPESCRIPT_VERSION,
    StandardLibrary,
)

ROOT = Path(__file__).resolve().parents[1]
TYPESCRIPT_LIB = ROOT / "tools/browser-runtime/node_modules/typescript/lib"


@pytest.mark.parametrize(
    ("compiler", "present", "missing"),
    [
        (
            {"lib": ["ES2020", "DOM", "DOM.Iterable"]},
            {"Math", "Date", "Map", "BigInt", "document", "console"},
            {"WeakRef"},
        ),
        ({"lib": ["es5"]}, {"Math", "Date"}, {"document", "Map"}),
        ({"lib": ["es2015"]}, {"Map", "Promise", "Math"}, {"document", "WeakRef"}),
        ({"lib": ["es6"]}, {"Map", "Promise"}, {"document"}),
        ({"lib": ["es2020"]}, {"BigInt", "Map"}, {"WeakRef", "document"}),
        ({"target": "es2022"}, {"Map", "document", "WeakMap"}, set()),
        ({"target": "es2015"}, {"Map", "Promise", "document"}, {"WeakRef"}),
        ({"target": "esnext"}, {"WeakRef", "document", "Iterator"}, set()),
        ({"module": "node16"}, {"Map", "document"}, set()),
        ({"module": "commonjs"}, {"String", "document"}, {"Map"}),
        ({}, {"String", "Math", "document"}, {"Map", "Promise"}),
    ],
)
def test_lib_and_default_target_prove_exactly_the_compiler_globals(
    tmp_path, compiler, present, missing
):
    config, snapshot = _environment(tmp_path, compiler)
    assert not config.partial and not snapshot.problems and not config.options.ambient_custom
    names = standard_globals(config.options)
    assert present <= names
    assert not missing & names


def test_generated_catalog_is_the_one_the_pinned_compiler_produces():
    if not TYPESCRIPT_LIB.is_dir():
        pytest.skip("browser runtime dependencies are not installed")
    result = subprocess.run(
        [sys.executable, "-m", "tools.typescript_libs", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_catalog_records_the_pinned_compiler_version():
    if not TYPESCRIPT_LIB.is_dir():
        pytest.skip("browser runtime dependencies are not installed")
    version = json.loads((TYPESCRIPT_LIB.parent / "package.json").read_text())["version"]
    assert TYPESCRIPT_VERSION == version


def test_catalog_entries_hold_the_declared_globals_of_their_library():
    assert LIB_GLOBALS[StandardLibrary.ES5] and "Math" in LIB_GLOBALS[StandardLibrary.ES5]
    assert "console" in LIB_GLOBALS[StandardLibrary.DOM]
    assert "WeakRef" in LIB_GLOBALS[StandardLibrary.ES2021_WEAKREF]

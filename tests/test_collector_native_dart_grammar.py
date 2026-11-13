# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
# ruff: noqa: E402
"""AD-342: the vendored Rust Dart grammar gives the same tree as the Python grammar.

Consumer: the native Dart collector, which must read the same syntax as the Python collector.
The gate compares the full trees of each Dart fixture and each Dart demo variant.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import re
import shutil
import sys
from pathlib import Path

import pytest
from oracle_support import ORACLE_UNAVAILABLE

pytest.skip(ORACLE_UNAVAILABLE, allow_module_level=True)
from conftest import install_rust_toolchain

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location(
    "dart_grammar_parity", ROOT / "tools/dart_grammar_parity.py"
)
assert spec and spec.loader
parity = importlib.util.module_from_spec(spec)
sys.modules["dart_grammar_parity"] = parity
spec.loader.exec_module(parity)


VENDOR = ROOT / "native/dart-grammar/vendor"


def test_the_vendored_files_are_the_bytes_of_the_release() -> None:
    """The vendored copy stays unchanged: each file has the SHA-256 of the sdist file."""
    table = (VENDOR / "README.md").read_text(encoding="utf-8")
    pinned = dict(re.findall(r"^\| `([^`]+)` \| `([0-9a-f]{64})` \|$", table, re.MULTILINE))
    on_disk = {
        path.relative_to(VENDOR).as_posix()
        for path in VENDOR.rglob("*")
        if path.is_file() and path.name != "README.md"
    }
    assert sorted(pinned) == sorted(on_disk)
    for relative, digest in pinned.items():
        assert hashlib.sha256((VENDOR / relative).read_bytes()).hexdigest() == digest, relative


def test_the_tree_text_holds_each_node_with_its_field_range_and_flags() -> None:
    parser = parity.Parser(parity.Language(parity.tree_sitter_dart.language()))
    lines = parity.tree_text(parser.parse(b"class A {\n  int f() => 1\n}")).splitlines()
    assert lines[:4] == [
        "0 program 1 - 0 26 0 0",
        "1 class_definition 1 - 0 26 0 0",
        # An anonymous node has named 0, and a field name is part of the line.
        "2 class 0 - 0 5 0 0",
        "2 identifier 1 name 6 7 0 0",
    ]
    # The parser adds the missing `;` as an empty node with the missing flag.
    assert "4 ; 0 - 24 24 1 0" in lines
    # A comment is an extra node.
    extra = parity.tree_text(parser.parse(b"// c\nvar a = 1;")).splitlines()
    assert "1 comment 1 - 0 4 0 1" in extra


def test_the_demo_corpora_cover_every_dart_fixture_and_variant(tmp_path: Path) -> None:
    named = dict(parity.corpora(True, [], tmp_path))
    assert sorted(named) == sorted([*parity.FIXTURES, "demo variants"])
    assert all(named.values())


def test_the_rust_grammar_gives_the_python_tree_on_every_demo_file(tmp_path: Path) -> None:
    cargo = shutil.which("cargo")
    if cargo is None:
        if os.environ.get("CI"):
            pytest.fail("CI must provide cargo for the native collector tests.")
        pytest.skip("cargo is not installed; install Rust to test changes in native/.")
    install_rust_toolchain(cargo)
    binary = parity.build_rust(release=False)
    for name, paths in parity.corpora(True, [], tmp_path):
        result = parity.compare(name, binary, paths)
        assert result.different == (), name
        assert result.equal == result.total > 0, name

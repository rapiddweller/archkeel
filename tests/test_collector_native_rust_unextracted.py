# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-352 (#1003): a use, path or macro call that the Rust collector loses is a gap, never a PASS.

Consumer: `edges_extracted.rs` (`check_extracted`). A second count of the tree must equal what the
scan and the edges ended. A bug that drops a record would otherwise leave no trace, and the scan
would read as complete (FP-13). The test plants that bug (`plant.rs`, only in the test binary) and
checks that the reply of the collector names an `unextracted` gap and is not a full scope.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from collector_wire import collect, request_bytes
from conftest import build_native_copy
from rust_repository import repository

# `app` has one `use` leaf, one qualified path, one macro call and one method call.
APP = (
    "use base_crate::make;\n"
    'pub fn run() { base_crate::make(); println!("x"); make(); "a".len(); }\n'
)
LOST = (
    "unextracted: 1 use, path or macro call node(s) of crates/app/src/lib.rs "
    "have no record and no gap"
)


@pytest.fixture(scope="session")
def dump_rust_binary(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The Rust collector built with the test-only `dump` feature, for its plants."""
    return build_native_copy(
        tmp_path_factory, "native-rust-dump", ("dump",), binary="archkeel-rust-collector"
    )


def _facts(root: Path, binary: Path, lib: str) -> dict[str, Any]:
    repository(root, binary, {"crates/app/src/lib.rs": lib})
    request = request_bytes(root, "native", roots=("crates",), language="rust", version="9.0.0")
    return collect(binary, request)


def _unextracted(facts: dict[str, Any]) -> list[str]:
    return [gap["title"] for gap in facts["coverage"]["gaps"] if "unextracted" in gap["title"]]


def test_a_doc_attribute_that_calls_a_macro_is_no_false_failure(
    tmp_path: Path, dump_rust_binary: Path
) -> None:
    # The macro call of `doc = include_str!(..)` is code that the scan reads: the count sees it.
    lib = '#![doc = include_str!("../README.md")]\n#[doc = concat!("a", "b")]\n' + APP
    facts = _facts(tmp_path, dump_rust_binary, lib)
    assert _unextracted(facts) == []


def test_an_extraction_that_loses_nothing_has_no_unextracted_gap(
    tmp_path: Path, dump_rust_binary: Path
) -> None:
    facts = _facts(tmp_path, dump_rust_binary, APP)
    assert facts["coverage"]["gaps"] == []
    assert facts["coverage"]["full_scope"]


@pytest.mark.parametrize(
    ("plant", "value"),
    [
        ("ARCHKEEL_PLANT_SKIP", "crates/app/src/lib.rs:0"),
        ("ARCHKEEL_PLANT_SKIP", "crates/app/src/lib.rs:1"),
        ("ARCHKEEL_PLANT_ARM", "crates/app/src/lib.rs:0"),
        ("ARCHKEEL_PLANT_ARM", "crates/app/src/lib.rs:1"),
        ("ARCHKEEL_PLANT_SCAN", "reference"),
        ("ARCHKEEL_PLANT_SCAN", "call"),
        ("ARCHKEEL_PLANT_SCAN", "method"),
        ("ARCHKEEL_PLANT_METHOD", "crates/app/src/lib.rs:0"),
    ],
)
def test_a_node_that_the_collector_loses_is_a_gap_and_not_a_full_scope(
    tmp_path: Path,
    dump_rust_binary: Path,
    monkeypatch: pytest.MonkeyPatch,
    plant: str,
    value: str,
) -> None:
    monkeypatch.setenv(plant, value)
    facts = _facts(tmp_path, dump_rust_binary, APP)
    assert _unextracted(facts) == [LOST]
    assert not facts["coverage"]["full_scope"]

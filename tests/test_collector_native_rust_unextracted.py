# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-352 (#1003): a use, path or macro call that the Rust collector loses is a gap, never a PASS.

Consumer: `edges_extracted.rs` (`check_extracted`). A second count of the tree must equal what the
scan and the edges ended. A bug that drops a record would otherwise leave no trace, and the scan
would read as complete (FP-13). The test plants that bug (`plant.rs`, only in the test binary) and
checks that the host reports a run failure named `unextracted`, and that no rule passes.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import build_native_copy
from rust_repository import repository, statuses, validate

Capsys = pytest.CaptureFixture[str]
# `app` has one `use` leaf, one qualified path, one macro call and one method call.
APP = (
    "use base_crate::make;\n"
    'pub fn run() { base_crate::make(); println!("x"); make(); "a".len(); }\n'
)


@pytest.fixture(scope="session")
def dump_rust_binary(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The Rust collector built with the test-only `dump` feature, for its plants."""
    return build_native_copy(
        tmp_path_factory, "native-rust-dump", ("dump",), binary="archkeel-rust-collector"
    )


def _unextracted(result: dict[str, object]) -> list[str]:
    return [
        str(item["unknown_claim"])
        for item in result["diagnostics"]  # type: ignore[attr-defined]
        if "unextracted" in str(item["unknown_claim"])
    ]


def test_a_doc_attribute_that_calls_a_macro_is_no_false_failure(
    tmp_path: Path, dump_rust_binary: Path, capsys: Capsys
) -> None:
    # The macro call of `doc = include_str!(..)` is code that the scan reads: the count sees it.
    lib = '#![doc = include_str!("../README.md")]\n#[doc = concat!("a", "b")]\n' + APP
    root = repository(tmp_path, dump_rust_binary, {"crates/app/src/lib.rs": lib})
    result = validate(root, capsys)
    assert _unextracted(result) == []
    assert result["exit_code"] == 0


def test_an_extraction_that_loses_nothing_has_no_unextracted_gap(
    tmp_path: Path, dump_rust_binary: Path, capsys: Capsys
) -> None:
    root = repository(tmp_path, dump_rust_binary, {"crates/app/src/lib.rs": APP})
    result = validate(root, capsys)
    assert _unextracted(result) == []
    assert statuses(result)["REQUIRES"] == "PASS"
    assert result["exit_code"] == 0


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
def test_a_node_that_the_collector_loses_is_a_run_failure_not_a_pass(
    tmp_path: Path,
    dump_rust_binary: Path,
    capsys: Capsys,
    monkeypatch: pytest.MonkeyPatch,
    plant: str,
    value: str,
) -> None:
    root = repository(tmp_path, dump_rust_binary, {"crates/app/src/lib.rs": APP})
    monkeypatch.setenv(plant, value)
    result = validate(root, capsys)
    assert len(_unextracted(result)) == 1
    assert result["exit_code"] != 0

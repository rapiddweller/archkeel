# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1047: a scan that asks for compiler type-reach facts and gets none says why.

A `PATH` with `git` and no `rustup` simulates a missing toolchain; none is removed.
The verdict is UNKNOWN for the whole scope, with the exact cause in the gaps.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from rust_repository import CRATE_RULES, repository, rule, validate
from rustc_dev_support import needs_rustc_dev

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="the scan needs git")


def _without_rustup(tmp_path: Path) -> str:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    git = shutil.which("git")
    assert git is not None
    (bin_dir / "git").symlink_to(git)
    return str(bin_dir)


def test_a_missing_toolchain_gives_unknown_with_the_exact_cause(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repository(tmp_path / "repo", release_core, rules=CRATE_RULES, type_reach=True)
    monkeypatch.setenv("PATH", _without_rustup(tmp_path))
    monkeypatch.setenv("ARCHKEEL_FACTS_CACHE", str(tmp_path / "cache"))
    result = validate(root)
    reasons = [gap["reason"] for gap in result["frame"]["collection_gaps"]]
    cause = (
        "The compiler type-reach facts are unavailable: the pinned Rust toolchain is not installed"
    )
    assert any(reason.startswith(cause) for reason in reasons), reasons
    assert result["frame"]["status"] == "UNKNOWN"
    assert "PASS" not in {row[1] for row in result["frame"]["rules"].values()}


def test_a_scan_without_the_key_reads_no_facts_and_adds_no_gap(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repository(tmp_path / "repo", release_core, rules=CRATE_RULES)
    monkeypatch.setenv("PATH", _without_rustup(tmp_path) + os.pathsep + os.environ.get("PATH", ""))
    reasons = [gap["reason"] for gap in validate(root)["frame"]["collection_gaps"]]
    assert not any("type-reach facts" in reason for reason in reasons)


def _facts_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCHKEEL_FACTS_CACHE", str(tmp_path / "cache"))


def test_a_scan_that_asks_for_facts_without_the_premise_does_not_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _facts_run(tmp_path, monkeypatch)
    root = repository(
        tmp_path / "repo", release_core, rules=CRATE_RULES, type_reach=True, premise=False
    )
    result = validate(root)
    reasons = [gap["reason"] for gap in result["frame"]["collection_gaps"]]
    cause = (
        "The compiler type-reach facts are unavailable: the contract does not declare the premise"
    )
    assert any(reason.startswith(cause) for reason in reasons), reasons
    assert "PASS" not in {row[1] for row in result["frame"]["rules"].values()}


def test_a_declared_premise_without_facts_is_not_named_in_the_receipt(
    tmp_path: Path, release_core: Path
) -> None:
    """AD-1116: a declaration alone is a wish. No facts exist, so no PASS names the premise."""
    root = repository(
        tmp_path / "repo", release_core, rules=CRATE_RULES, type_reach=False, declared=True
    )
    frame = validate(root)["frame"]
    assert frame["rules"]["REQUIRES"][1] == "PASS", frame["collection_gaps"]
    kinds = {use["kind"] for uses in frame.get("premises", {}).values() for use in uses}
    assert "rust_type_reach" not in kinds
    assert "rust_type_reach" not in (frame.get("assuming") or "")


@needs_rustc_dev
def test_a_pass_on_the_facts_names_the_premise_in_its_receipt(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _facts_run(tmp_path, monkeypatch)
    root = repository(tmp_path / "repo", release_core, rules=CRATE_RULES, type_reach=True)
    result = validate(root)
    frame = result["frame"]
    assert frame["rules"]["REQUIRES"][1] == "PASS", frame["collection_gaps"]
    used = {
        name
        for name, uses in frame["premises"].items()
        for use in uses
        if use["kind"] == "rust_type_reach"
    }
    assert {"ASSIGNED", "REQUIRES", "NO-CYCLES"} >= used >= {"REQUIRES", "NO-CYCLES"}
    assert "rust_type_reach: the compiler type reach of the pinned rustc holds" in frame["assuming"]
    assert "whole program" in frame["assuming"]
    assert "this target" in frame["assuming"]


_MARKER_BUILD = """fn main() {
    std::fs::write("MARKER", "the build script ran").unwrap();
}
"""


def _marked(tmp_path: Path, release_core: Path) -> tuple[Path, Path]:
    marker = tmp_path / "build-script-ran"
    root = repository(
        tmp_path / "repo",
        release_core,
        rules=CRATE_RULES,
        type_reach=True,
        files={"crates/base/build.rs": _MARKER_BUILD.replace("MARKER", str(marker))},
    )
    return root, marker


def test_the_setting_of_the_repository_alone_runs_no_cargo(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AD-1130: the repository cannot grant operator trust. No permission, no build script."""
    _facts_run(tmp_path, monkeypatch)
    root, marker = _marked(tmp_path, release_core)
    result = validate(root, allow_build=False)
    frame = result["frame"]
    cause = "The compiler type-reach facts are unavailable: type reach not allowed by the operator"
    reasons = [gap["reason"] for gap in frame["collection_gaps"]]
    assert any(reason.startswith(cause) for reason in reasons), reasons
    assert not marker.exists()
    assert frame["status"] == "UNKNOWN"
    assert "PASS" not in {row[1] for row in frame["rules"].values()}
    kinds = {use["kind"] for uses in frame.get("premises", {}).values() for use in uses}
    assert "rust_type_reach" not in kinds


@needs_rustc_dev
def test_with_the_permission_the_facts_are_produced_as_before(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _facts_run(tmp_path, monkeypatch)
    root, marker = _marked(tmp_path, release_core)
    frame = validate(root, allow_build=True)["frame"]
    assert frame["rules"]["REQUIRES"][1] == "PASS", frame["collection_gaps"]
    assert marker.exists()


@needs_rustc_dev
def test_a_sibling_cycle_in_a_bin_target_is_still_a_module_cycle(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AD-1160: the facts of `main.rs` modules are read per module; a real cycle fails."""
    _facts_run(tmp_path, monkeypatch)
    cycle = {
        "crates/app/src/main.rs": "mod a;\nmod b;\nfn main() { a::f(); }\n",
        "crates/app/src/a.rs": "pub fn f() { crate::b::g(); }\n",
        "crates/app/src/b.rs": "pub fn g() { crate::a::f(); }\n",
    }
    rules = (*CRATE_RULES, rule("MODS", "no_component_cycles", level="module"))
    root = repository(tmp_path / "repo", release_core, files=cycle, rules=rules, type_reach=True)
    frame = validate(root)["frame"]
    assert frame["rules"]["MODS"][1] == "FAIL", frame["collection_gaps"]

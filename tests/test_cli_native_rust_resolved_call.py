# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1185: a method call that rustc resolves is an edge and closes the other receiver candidates.

`c::make()` gives a `d::U`. `a` calls it through a local, so the scan cannot type it.
The scan reads no types, so `a -> b` was a held pair. The compiler resolves the call to the `m`
of `d`: the counter that `cargo run` prints shows that only `d` runs. A call that the compiler
cannot resolve (a trait object) keeps the gap. So does a call that a configuration changes.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from rust_resolved_support import (
    A_B,
    A_D,
    A_DYN,
    A_FEATURE,
    MANIFEST,
    _cargo_run,
    _scan,
)
from rustc_dev_support import needs_rustc_dev

pytestmark = [
    pytest.mark.skipif(shutil.which("cargo") is None, reason="cargo is the oracle"),
    needs_rustc_dev,
]


def test_a_resolved_call_closes_the_other_candidate_and_is_a_proven_use(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, found = _scan(tmp_path, release_core, monkeypatch, A_D)
    assert _cargo_run(root) == "0 1", "only the `m` of `d` runs"
    assert found["NO-A-TO-B"] == "PASS", "the compiler excludes `b`"
    assert found["NO-A-TO-D"] == "FAIL", "the resolved call is a use of `d`"


def test_a_call_that_runs_the_candidate_is_a_proven_use_of_it(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, found = _scan(tmp_path, release_core, monkeypatch, A_B)
    assert _cargo_run(root) == "1 0", "the `m` of `b` runs"
    assert found["NO-A-TO-B"] == "FAIL"
    assert found["NO-A-TO-D"] == "PASS", "the compiler excludes `d`"


def test_a_call_through_a_trait_object_is_not_resolved_and_keeps_both_gaps(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, found = _scan(tmp_path, release_core, monkeypatch, A_DYN)
    assert _cargo_run(root) == "0 1", "the impl of `d` runs through the vtable"
    assert found["NO-A-TO-B"] == "UNKNOWN"
    assert found["NO-A-TO-D"] != "PASS"


def test_a_call_that_a_feature_changes_keeps_the_gap(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without the feature `d` runs, with it `b` runs: no callee holds in every configuration."""
    _, found = _scan(tmp_path, release_core, monkeypatch, A_FEATURE, MANIFEST)
    assert found["NO-A-TO-B"] != "PASS"
    assert found["NO-A-TO-D"] != "PASS"

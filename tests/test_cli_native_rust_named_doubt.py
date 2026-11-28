# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1550: the named doubt and the execution doubt of a method call are two holds.

The compiler resolves `.next()` to a function of another file. That settles the doubt that the
call names the method `next` of `b`. An argument that can run code of `b` is a second doubt, and it
stays as a hold of its own (a `collection_gap`, not a named `source_resolution_gap`).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
from rust_repository import CRATE_RULES, repository, rule, validate
from rust_resolved_support import (
    A_CLOSURE_A,
    A_CLOSURE_B,
    _cargo_run,
    _forbid,
    _parts,
    _sources,
)
from rustc_dev_support import needs_rustc_dev

pytestmark = [
    pytest.mark.skipif(shutil.which("cargo") is None, reason="cargo is the oracle"),
    needs_rustc_dev,
]

SAME_LINE = (
    "pub fn run() {\n    let _held = crate::c::other();\n"
    "    std::iter::once(()).next(); crate::c::other().m();\n}\n"
)
MACRO = (
    "macro_rules! go {\n    () => {\n        crate::c::other().m()\n    };\n}\n\n"
    "pub fn run() {\n    let _held = crate::c::other();\n"
    "    std::iter::once(()).next(); go!();\n}\n"
)
ELSEWHERE = (
    "pub fn run() {\n    let _held = crate::c::other();\n    crate::c::counter().next();\n}\n"
)
COUNTER_IN_C = (
    "\n\npub struct Counter;\n\nimpl Counter {\n"
    "    pub fn next(&self) -> usize {\n        1\n    }\n}\n\n"
    "pub fn counter() -> Counter {\n    Counter\n}\n"
)


def _scan(
    tmp_path: Path, core: Path, monkeypatch: pytest.MonkeyPatch, a: str, extra_c: str = ""
) -> tuple[Path, dict[str, Any]]:
    monkeypatch.setenv("ARCHKEEL_FACTS_CACHE", str(tmp_path / "cache"))
    files = _sources(a)
    files["crates/app/src/c.rs"] += extra_c
    root = repository(
        tmp_path / "repo",
        core,
        files,
        components=_parts(),
        rules=(*CRATE_RULES[1:], _forbid("b"), _forbid("d")),
        type_reach=True,
    )
    return root, validate(root)["frame"]


def _interface_scan(
    tmp_path: Path, core: Path, monkeypatch: pytest.MonkeyPatch, a: str
) -> tuple[Path, dict[str, Any]]:
    """`b` publishes `S` and `mk`; the interface rule reads the named doubts of `a` to `b`."""
    monkeypatch.setenv("ARCHKEEL_FACTS_CACHE", str(tmp_path / "cache"))
    parts = tuple(
        {**part, "public": ["native.app.b:S", "native.app.b:mk"]} if part["label"] == "b" else part
        for part in _parts()
    )
    root = repository(
        tmp_path / "repo",
        core,
        _sources(a),
        components=parts,
        rules=(*CRATE_RULES[1:], rule("BOUNDARY", "interface_boundary")),
        type_reach=True,
    )
    return root, validate(root)["frame"]


def test_an_argument_that_runs_b_leaves_no_named_doubt_of_the_call(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`use b::S` is an edge. `.next()` is `Iterator::next`, so it names no private method of `b`.

    The closure of `b` that the argument runs is a second doubt. It comes from `c::pass`, which
    `c` judges on its own import of `b::mk`; it is no use of an unpublished name by `a`.
    """
    a = (
        "use crate::b::S;\n\npub fn run() {\n    let _held: Option<S> = None;\n"
        "    std::iter::once(()).map(crate::c::pass()).next();\n}\n"
    )
    root, frame = _interface_scan(tmp_path, release_core, monkeypatch, a)
    assert _cargo_run(root) == "1 0", "the closure of `b` runs"
    assert frame["rules"]["BOUNDARY"][1] == "PASS", frame["explain"]["holds"]


def test_an_argument_that_runs_b_keeps_its_execution_hold_when_a_does_not_import_b(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No edge: the interface rule has no named doubt left, `REQUIRES` keeps the execution doubt."""
    root, frame = _interface_scan(tmp_path, release_core, monkeypatch, A_CLOSURE_B)
    assert _cargo_run(root) == "1 0", "the closure of `b` runs"
    assert frame["rules"]["BOUNDARY"][1] == "PASS", frame["explain"]["holds"]
    assert frame["rules"]["REQUIRES"][1] == "UNKNOWN", "code of `b` can still run"
    held = frame["explain"]["holds"]["rules"]["REQUIRES"]["pairs"]
    assert [(p["source"], p["target"]) for p in held] == [("native.app.a", "native.app.b")]


def test_an_argument_that_runs_nothing_of_b_closes_the_pair(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, frame = _scan(tmp_path, release_core, monkeypatch, A_CLOSURE_A)
    assert _cargo_run(root) == "0 0"
    assert frame["rules"]["NO-A-TO-B"][1] == "PASS"


def test_two_calls_on_one_line_each_keep_their_own_decision(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`.next()` goes to `core`; `.m()` on the same line is a method of `b`: a violation."""
    root, frame = _scan(tmp_path, release_core, monkeypatch, SAME_LINE)
    assert _cargo_run(root) == "1 0", "`m` of `b` runs"
    assert frame["rules"]["NO-A-TO-B"][1] == "FAIL"


def test_a_call_that_a_macro_writes_does_not_settle_a_named_doubt(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, frame = _scan(tmp_path, release_core, monkeypatch, MACRO)
    assert _cargo_run(root) == "1 0", "`m` of `b` runs through the macro"
    assert frame["rules"]["NO-A-TO-B"][1] in {"FAIL", "UNKNOWN"}


def test_the_same_spelling_in_another_file_settles_only_its_own_call(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`c::Counter::next` and `b::S::next` have one spelling. The compiler picks the file of `c`."""
    root, frame = _scan(tmp_path, release_core, monkeypatch, ELSEWHERE, COUNTER_IN_C)
    assert _cargo_run(root) == "0 0"
    assert frame["rules"]["NO-A-TO-B"][1] == "PASS"

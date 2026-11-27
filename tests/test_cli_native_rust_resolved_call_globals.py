# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1185: a resolved call stays open when a global can hold a callback of `b`.

The callback sits in a static, a constant or an associated constant of a file that the call touches.
The counter that `cargo run` prints is `1 0` (`b` runs), so the candidate must stay.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from rust_resolved_support import (
    COUNTER,
    _cargo_run,
    _hit0_scan,
)
from rustc_dev_support import needs_rustc_dev

pytestmark = [
    pytest.mark.skipif(shutil.which("cargo") is None, reason="cargo is the oracle"),
    needs_rustc_dev,
]


def test_a_static_callback_of_the_callee_file_keeps_the_gap(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d::U::m` calls `CALLBACK`, a static of `d` that holds `b::hit0`: no signature names it."""
    holds = COUNTER.format(
        body="pub struct U;\n\nstatic CALLBACK: fn() = crate::b::hit0;\n\n"
        "impl U {\n    pub fn m(&self) -> usize {\n        CALLBACK();\n        0\n    }\n}"
    )
    files = {
        "crates/app/src/d.rs": holds,
        "crates/app/src/c.rs": "pub fn other() -> crate::b::S {\n    crate::b::S\n}\n\n"
        "pub fn make() -> crate::d::U {\n    crate::d::U\n}\n",
        "crates/app/src/a.rs": "pub fn run() {\n    let _held = crate::c::other();\n"
        "    let make = crate::c::make;\n    make().m();\n}\n",
    }
    root, found = _hit0_scan(tmp_path, release_core, monkeypatch, files)
    assert _cargo_run(root) == "1 0", "the static function of `b` runs"
    assert found["NO-A-TO-B"] != "PASS"


def test_a_constant_callback_of_the_callee_file_keeps_the_gap(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d::U::m` calls `CALLBACK`, a constant of `d` that holds `b::hit0`: no signature names it."""
    holds = COUNTER.format(
        body="pub struct U;\n\nconst CALLBACK: fn() = crate::b::hit0;\n\n"
        "impl U {\n    pub fn m(&self) -> usize {\n        CALLBACK();\n        0\n    }\n}"
    )
    files = {
        "crates/app/src/d.rs": holds,
        "crates/app/src/c.rs": "pub fn other() -> crate::b::S {\n    crate::b::S\n}\n\n"
        "pub fn make() -> crate::d::U {\n    crate::d::U\n}\n",
        "crates/app/src/a.rs": "pub fn run() {\n    let _held = crate::c::other();\n"
        "    let make = crate::c::make;\n    make().m();\n}\n",
    }
    root, found = _hit0_scan(tmp_path, release_core, monkeypatch, files)
    assert _cargo_run(root) == "1 0", "the constant function of `b` runs"
    assert found["NO-A-TO-B"] != "PASS"


def test_an_associated_constant_callback_of_the_callee_keeps_the_gap(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d::U::m` calls `CALLBACK`, an associated constant that holds `b::hit0`."""
    holds = COUNTER.format(
        body="pub struct U;\n\n"
        "impl U {\n    const CALLBACK: fn() = crate::b::hit0;\n\n"
        "    pub fn m(&self) -> usize {\n        (Self::CALLBACK)();\n        0\n    }\n}"
    )
    files = {
        "crates/app/src/d.rs": holds,
        "crates/app/src/c.rs": "pub fn other() -> crate::b::S {\n    crate::b::S\n}\n\n"
        "pub fn make() -> crate::d::U {\n    crate::d::U\n}\n",
        "crates/app/src/a.rs": "pub fn run() {\n    let _held = crate::c::other();\n"
        "    let make = crate::c::make;\n    make().m();\n}\n",
    }
    root, found = _hit0_scan(tmp_path, release_core, monkeypatch, files)
    assert _cargo_run(root) == "1 0", "the associated constant function of `b` runs"
    assert found["NO-A-TO-B"] != "PASS"


def test_a_static_callback_that_a_second_file_holds_keeps_the_gap(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d` holds a static of type `c::State`, and `c` holds the static callback into `b`."""
    state = COUNTER.format(
        body="pub struct State;\n\npub static CALLBACK: fn() = crate::b::hit0;\n\n"
        "impl State {\n    pub fn run(&self) {\n        CALLBACK();\n    }\n}"
    )
    holds = COUNTER.format(
        body="pub struct U;\n\nstatic STATE: crate::c::State = crate::c::State;\n\n"
        "impl U {\n    pub fn m(&self) -> usize {\n        STATE.run();\n        0\n    }\n}"
    )
    files = {
        "crates/app/src/d.rs": holds,
        "crates/app/src/c.rs": state + "\npub fn other() -> crate::b::S {\n    crate::b::S\n}\n\n"
        "pub fn make() -> crate::d::U {\n    crate::d::U\n}\n",
        "crates/app/src/a.rs": "pub fn run() {\n    let _held = crate::c::other();\n"
        "    let make = crate::c::make;\n    make().m();\n}\n",
    }
    root, found = _hit0_scan(tmp_path, release_core, monkeypatch, files)
    assert _cargo_run(root) == "1 0", "the static function of `b` runs"
    assert found["NO-A-TO-B"] != "PASS"


def test_a_static_callback_that_the_receiver_call_reads_keeps_the_gap(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`c::make` reads a static of `c` that holds `b::hit0` before it returns the `d::U`."""
    files = {
        "crates/app/src/c.rs": "static CALLBACK: fn() = crate::b::hit0;\n\n"
        "pub fn other() -> crate::b::S {\n    crate::b::S\n}\n\n"
        "pub fn make() -> crate::d::U {\n    CALLBACK();\n    crate::d::U\n}\n",
        "crates/app/src/d.rs": COUNTER.format(
            body="pub struct U;\n\nimpl U {\n    pub fn m(&self) -> usize {\n        0\n    }\n}"
        ),
        "crates/app/src/a.rs": "pub fn run() {\n    let _held = crate::c::other();\n"
        "    let make = crate::c::make;\n    make().m();\n}\n",
    }
    root, found = _hit0_scan(tmp_path, release_core, monkeypatch, files)
    assert _cargo_run(root) == "1 0", "the static function of `b` runs"
    assert found["NO-A-TO-B"] != "PASS"

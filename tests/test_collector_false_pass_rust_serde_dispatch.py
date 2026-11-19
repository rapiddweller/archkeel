# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Constructing a record does not run its Serde callback."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from rust_repository import APP, BASE, component, repository, rule, statuses, validate

pytestmark = pytest.mark.skipif(shutil.which("cargo") is None, reason="Rust runs the fixtures")

PRODUCER = "native.app.producer"
RECORD = "native.base_crate.record"
SKIP = "native.base_crate.skip"
RECORD_FILE = "crates/base/src/record.rs"
RECORD_SOURCE = """\
#[derive(serde::Serialize)]
pub struct Record {
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub field: Option<u8>,
}
"""
SKIP_SOURCE = """\
use std::sync::atomic::{AtomicBool, Ordering};
pub(crate) static HIT: AtomicBool = AtomicBool::new(false);
pub(crate) trait Present { fn present(&self) -> bool; }
impl<T> Present for Option<T> {
    fn present(&self) -> bool {
        HIT.store(true, Ordering::Relaxed);
        self.is_some()
    }
}
pub(crate) fn omitted<T: Present>(value: &T) -> bool { !value.present() }
"""
PRIVATE_BOUND = """\
#[allow(private_bounds)]
pub fn encode_field<T: crate::skip::Present>(field: &T) -> bool {
    crate::skip::omitted(field)
}
"""


def _exact(label: str, needs: tuple[str, ...], *modules: str) -> dict[str, Any]:
    return {**component(label, label, needs), "packages": [], "exact_modules": list(modules)}


def _check(result: dict[str, Any], executes: bool, allow_callback: bool) -> None:
    verdict = statuses(result)["REQUIRES"]
    frame = result["frame"]
    if not allow_callback:
        assert verdict == "FAIL", frame["rules"]
        locations = frame["locations"]
        assert any(
            row["source"] == RECORD
            and row["target"] == SKIP
            and any(
                (locations[key]["path"], locations[key]["line"]) == (RECORD_FILE, 3)
                for key in row["evidence"]
            )
            for row in frame["details"]["REQUIRES"]
        ), frame["details"]
    elif executes:
        assert verdict in {"UNKNOWN", "FAIL"}, frame["rules"]
        if verdict == "UNKNOWN":
            holds = frame["explain"]["holds"]["rules"]["REQUIRES"]
            assert {"source": PRODUCER, "target": SKIP} in holds["pairs"], holds
        else:
            rows = frame["details"]["REQUIRES"]
            assert any(row["source"] == PRODUCER and row["target"] == SKIP for row in rows), rows
    else:
        assert verdict in {"PASS", "UNKNOWN"}, frame["rules"]


def test_requires_keeps_evidence_for_a_serialization_hook(
    tmp_path: Path, release_core: Path
) -> None:
    cases = (
        ("construct", "", "", False, True),
        ("write", 'assert_eq!(serde_json::to_string(&value).unwrap(), "{}");', "", True, True),
        (
            "private-bound",
            "assert!(record::encode_field(&value.field));",
            PRIVATE_BOUND,
            True,
            True,
        ),
        ("named-callback", "", "", False, False),
    )
    lock = None
    for name, call, extra, executes, allow_callback in cases:
        files = {
            "crates/base/Cargo.toml": BASE
            + '[dependencies]\nserde = { version = "1", features = ["derive"] }\n',
            "crates/base/src/lib.rs": (
                "pub mod record; mod skip;\n"
                "pub fn take_hit() -> bool {\n"
                "    skip::HIT.swap(false, std::sync::atomic::Ordering::Relaxed)\n"
                "}\n"
            ),
            RECORD_FILE: RECORD_SOURCE + extra,
            "crates/base/src/skip.rs": SKIP_SOURCE,
            "crates/app/Cargo.toml": APP + 'serde_json = "1"\n',
            "crates/app/src/lib.rs": "pub mod producer;",
            "crates/app/src/producer.rs": (
                "use base_crate::record;\n"
                "pub fn make() -> record::Record {\n"
                f"    let value = record::Record {{ field: None }};\n    {call}\n    value\n"
                "}\n"
            ),
            "crates/app/src/main.rs": (
                "fn main() {\n"
                "    let record = app::producer::make();\n"
                f"    assert_eq!(base_crate::take_hit(), {str(executes).lower()});\n"
                '    assert_eq!(serde_json::to_string(&record).unwrap(), "{}");\n'
                "    assert!(base_crate::take_hit());\n"
                "}\n"
            ),
        }
        parts = (
            _exact("base", ("record", "skip"), "native.base_crate", "native.base_crate.cargo_toml"),
            _exact("record", ("skip",) if allow_callback else (), RECORD),
            _exact("skip", (), SKIP),
            _exact(
                "app",
                ("base", "producer", "record", "skip"),
                "native.app",
                "native.app.cargo_toml",
                "native.app.bin_app",
            ),
            _exact("producer", ("record",), PRODUCER),
        )
        root = repository(
            tmp_path / name, release_core, files, parts, (rule("REQUIRES", "complete_requires"),)
        )
        _check(validate(root), executes, allow_callback)

        # The manifests are identical, so only the first witness needs to resolve dependencies.
        lock_path = root / "crates/Cargo.lock"
        if lock is not None:
            lock_path.write_bytes(lock)
        command = ["cargo", "run", "--quiet", "--manifest-path", str(root / "crates/Cargo.toml")]
        if lock is not None:
            command += ["--locked", "--offline"]
        witness = subprocess.run(
            command,
            cwd=Path(__file__).resolve().parents[1] / "native",
            env={**os.environ, "CARGO_TARGET_DIR": str(tmp_path / "target")},
            capture_output=True,
            text=True,
            check=False,
        )
        assert witness.returncode == 0, (name, witness.stderr)
        if lock is None:
            lock = lock_path.read_bytes()

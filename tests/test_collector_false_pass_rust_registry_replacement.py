# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A source replacement outside the repository changes a modeled registry derive (#1518).

The lock names `serde` and `serde_derive` 1.0.229 from crates.io with their checksums, so the model
of AD-424 reads `#[derive(Serialize)]` in `a` as the written helper paths of Serde. A
`[source.crates-io] replace-with` in `$CARGO_HOME/config.toml` takes both crates from a directory
outside the repository. Its `.cargo-checksum.json` states the checksums of the lock, so `cargo check
--locked --offline` builds it, and its derive expands to `crate::b::secret()` in `a`. The rule that
forbids `a -> b` may not PASS.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from rust_repository import CRATE_RULES, component, repository, rule, statuses, validate

pytestmark = pytest.mark.skipif(shutil.which("cargo") is None, reason="rustc is the oracle")

FIXTURE = json.loads(Path(__file__).with_name("rust_registry_replacement.json").read_text())
NO_A_TO_B = rule(
    "NO-A-TO-B",
    "forbidden_dependency",
    source="native.app.a",
    target="native.app.b",
    include_type_checking=True,
)


def _write(root: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def test_an_outside_source_replacement_cannot_certify_a_derive(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repository(
        tmp_path / "repo",
        release_core,
        {
            "crates/app/Cargo.toml": FIXTURE["manifest"],
            "crates/Cargo.lock": FIXTURE["lock"],
            "crates/app/src/lib.rs": "pub mod a; pub mod b;\n",
            "crates/app/src/a.rs": "use serde::Serialize;\n#[derive(Serialize)]\npub struct S;\n",
            "crates/app/src/b.rs": "pub const fn secret() {}\n",
        },
        components=(component("base", "base_crate"), component("app", "app")),
        rules=(*CRATE_RULES, NO_A_TO_B),
    )
    home, replacement = tmp_path / "home", tmp_path / "replacement"
    _write(replacement, FIXTURE["vendor"])
    _write(
        home,
        {
            "config.toml": '[source.crates-io]\nreplace-with = "outside"\n'
            f'[source.outside]\ndirectory = "{replacement}"\n'
        },
    )
    monkeypatch.setenv("CARGO_HOME", str(home))
    verdict = statuses(validate(root))["NO-A-TO-B"]
    env = {**os.environ, "CARGO_TARGET_DIR": str(tmp_path / "target")}
    manifest = root / "crates/Cargo.toml"
    command = [
        "cargo",
        "check",
        "--quiet",
        "--locked",
        "--offline",
        "--manifest-path",
        str(manifest),
    ]
    done = subprocess.run(command, capture_output=True, text=True, env=env, check=False)
    assert done.returncode == 0, done.stderr
    assert verdict in {"FAIL", "UNKNOWN"}

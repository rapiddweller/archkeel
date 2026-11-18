# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A source replacement can change a modeled registry derive (#1518, AD-774).

The lock names `serde` and `serde_derive` 1.0.229 from crates.io with their checksums, so the model
of AD-424 reads `#[derive(Serialize)]` in `a` as the written helper paths of Serde. A
`[source.crates-io] replace-with` takes both crates from a directory whose `.cargo-checksum.json`
states the checksums of the lock: `cargo check --locked --offline` builds it, and its derive
expands to `crate::b::secret()` in `a`.

- A replacement in a `.cargo/config.toml` of the repository withholds the proof: the rule that
  forbids `a -> b` is UNKNOWN, and a gap names the file and line.
- A replacement in `$CARGO_HOME` is not read (the result does not depend on the machine): the rule
  passes under the printed premise, which says that no outside source replacement applies.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from rust_repository import CRATE_RULES, component, repository, rule, validate

pytestmark = pytest.mark.skipif(shutil.which("cargo") is None, reason="rustc is the oracle")

FIXTURE = json.loads(Path(__file__).with_name("rust_registry_replacement.json").read_text())
# AD-608, #1779: each Rust run states that the code compiles; the lock premise follows it.
COMPILES = "the Rust code compiles (rustc accepts it)"
PREMISE = (
    f"{COMPILES}; registry crates are built from the identity that Cargo.lock records; "
    "no outside source replacement"
)
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


def _config(replacement: Path) -> str:
    return (
        '[source.crates-io]\nreplace-with = "outside"\n'
        f'[source.outside]\ndirectory = "{replacement}"\n'
    )


def _plant(tmp_path: Path, core: Path, extra: dict[str, str] | None = None) -> Path:
    files = {
        "crates/app/Cargo.toml": FIXTURE["manifest"],
        "crates/Cargo.lock": FIXTURE["lock"],
        "crates/app/src/lib.rs": "pub mod a; pub mod b;\n",
        "crates/app/src/a.rs": "use serde::Serialize;\n#[derive(Serialize)]\npub struct S;\n",
        "crates/app/src/b.rs": "pub const fn secret() {}\n",
        **(extra or {}),
    }
    parts = (component("base", "base_crate"), component("app", "app"))
    root = repository(
        tmp_path / "repo", core, files, components=parts, rules=(*CRATE_RULES, NO_A_TO_B)
    )
    _write(tmp_path / "replacement", FIXTURE["vendor"])
    return root


def _cargo_builds(root: Path, home: Path) -> None:
    home.mkdir(exist_ok=True)
    env = {**os.environ, "CARGO_HOME": str(home), "CARGO_TARGET_DIR": str(root.parent / "target")}
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
    # Cargo reads the configuration of the directory where it runs and of each directory above.
    done = subprocess.run(
        command, capture_output=True, text=True, env=env, check=False, cwd=root / "crates"
    )
    assert done.returncode == 0, done.stderr


def _row(document: dict[str, Any]) -> str:
    return str(document["frame"]["rules"]["NO-A-TO-B"][1])


def test_a_replacement_inside_the_repository_withholds_the_derive_proof(
    tmp_path: Path, release_core: Path
) -> None:
    config = _config(tmp_path / "replacement")
    root = _plant(tmp_path, release_core, {"crates/.cargo/config.toml": config})
    document = validate(root)
    _cargo_builds(root, tmp_path / "home")
    assert _row(document) == "UNKNOWN"
    reasons = [gap["reason"] for gap in document["frame"]["collection_gaps"]]
    named = [r for r in reasons if "crates/.cargo/config.toml:2" in r and "serde" in r]
    assert named, reasons
    assert document["frame"]["premise"] == COMPILES


def test_a_replacement_outside_the_repository_passes_under_the_printed_premise(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _plant(tmp_path, release_core)
    home = tmp_path / "home"
    _write(home, {"config.toml": _config(tmp_path / "replacement")})
    monkeypatch.setenv("CARGO_HOME", str(home))
    document = validate(root)
    _cargo_builds(root, home)
    assert _row(document) == "PASS"
    assert document["frame"]["premise"] == PREMISE


def test_a_configuration_without_a_source_setting_keeps_the_proof(
    tmp_path: Path, release_core: Path
) -> None:
    root = _plant(tmp_path, release_core, {".cargo/config.toml": "[build]\njobs = 1\n"})
    document = validate(root)
    assert _row(document) == "PASS"
    assert document["frame"]["premise"] == PREMISE


def test_a_cache_tag_does_not_hide_a_nested_paths_override(
    tmp_path: Path, release_core: Path
) -> None:
    path = "docs/cache/nested/.cargo/config.toml"
    root = _plant(
        tmp_path,
        release_core,
        {
            "docs/cache/CACHEDIR.TAG": "Signature: 8a477f597d28d172789f06886806bc55\n",
            path: 'paths = ["local-input"]\n',
        },
    )
    document = validate(root)
    assert _row(document) == "UNKNOWN"
    assert document["frame"]["premise"] == COMPILES
    assert any(
        f"A paths override in {path}:1" in gap["reason"]
        for gap in document["frame"]["collection_gaps"]
    )

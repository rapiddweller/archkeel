# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Layout shapes of real projects that `init` must draft without a fault.

Each plant is the smallest form of a shape that a public project has (the project is named).
"""

from pathlib import Path

from archkeel.cli.init_draft import draft

CRATE = '[package]\nname = "{}"\nversion = "0.1.0"\nedition = "2021"\n'


def _write(root: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    return root


def test_a_member_workspace_of_its_own_folder_is_no_fault(tmp_path: Path) -> None:
    """tokio 1.48.0: `tokio/fuzz/Cargo.toml` is a workspace with `members = ["."]`."""
    root = _write(
        tmp_path,
        {
            "Cargo.toml": '[workspace]\nmembers = [\n  "core",\n\n  # Internal\n  "util",\n]\n',
            "core/Cargo.toml": CRATE.format("core-a"),
            "core/src/lib.rs": "pub fn one() -> i32 { 1 }\n",
            "core/fuzz/Cargo.toml": CRATE.format("core-fuzz") + '\n[workspace]\nmembers = ["."]\n',
            "core/fuzz/src/main.rs": "fn main() {}\n",
            "util/Cargo.toml": CRATE.format("util"),
            "util/src/lib.rs": "pub fn two() -> i32 { 2 }\n",
        },
    )
    result = draft(root)
    assert result.language == "rust"
    assert result.components == ("core_a", "util")


def test_a_workspace_draft_leaves_test_sources_out_as_a_crate_draft_does(tmp_path: Path) -> None:
    """tokio 1.48.0, serde 1.0.228: a proc-macro crate tests itself through the main crate (a
    `[dev-dependencies]` edge back). A draft that scans test sources fails its first run with a
    cycle that only tests close (#1680)."""
    root = _write(
        tmp_path,
        {
            "Cargo.toml": '[workspace]\nmembers = ["main", "derive"]\n',
            "main/Cargo.toml": CRATE.format("main")
            + '[dependencies]\nderive = { path = "../derive" }\n',
            "main/src/lib.rs": "pub use derive::*;\n",
            "derive/Cargo.toml": CRATE.format("derive")
            + '[dev-dependencies]\nmain = { path = "../main" }\n',
            "derive/src/lib.rs": "pub fn one() -> i32 { 1 }\n",
        },
    )
    config = next(file for file in draft(root).files if file.path == "archkeel.toml")
    assert "exclude_test_sources = true" in config.text

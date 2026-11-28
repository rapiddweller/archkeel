# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1952: a single binary crate whose `[[bin]]` has another name than the package is owned.

`fd-find` names its binary `fd` and its root file `src/main.rs`. The draft names the modules
`<ns>.fd_find.<mod>`; the collector named them `<ns>.fd_find.bin_fd.<mod>`, so no component owned
a module and the first verdict was FAIL (ownership), not UNKNOWN.
"""

import json
from pathlib import Path

import pytest

from archkeel.cli import core_only
from tests.test_cli_auto_init import commit, write

CARGO = """[package]
name = "my-tool"
version = "0.1.0"
edition = "2021"

[[bin]]
name = "tool"
path = "src/main.rs"
"""
FILES = {
    "Cargo.toml": CARGO,
    "src/main.rs": "mod parse;\nmod render;\nfn main() { parse::run(); render::run(); }\n",
    "src/parse.rs": "pub fn run() {}\n",
    "src/render/mod.rs": "pub fn run() {}\n",
}


def test_the_first_verdict_of_a_named_bin_is_not_an_ownership_fail(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    release_core: Path,
) -> None:
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    root = commit(write(tmp_path, FILES))
    core_only.run(["validate", "--root", str(root), "--json"])
    capsys.readouterr()
    code = core_only.run(["validate", "--root", str(root), "--json"])
    document = json.loads(capsys.readouterr().out)
    frame = document["frame"]
    assert frame["violations"] == {}, frame["details"]
    assert (document["status"], code) == ("UNKNOWN", 2), document["gaps"]
    assert frame["rules"]["ASSIGNMENT-COMPLETE"][1] != "FAIL"

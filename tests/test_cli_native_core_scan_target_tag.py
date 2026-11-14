# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A build directory that a test helper makes before cargo must not be counted as source."""

from __future__ import annotations

import json
from pathlib import Path

from core_support import SUFFIX, ensure_target_dir
from corpus_support import commit_tree

from archkeel.cli import native_scan

OVER_BUDGET = 1024**3 + 1


def _scan(core: Path, root: Path) -> dict[str, object]:
    request = {"protocol": native_scan.SCAN_PROTOCOL, "root": str(root), "config": "archkeel.toml"}
    stdout, _ = native_scan.exchange(str(core), "scan", json.dumps(request).encode())
    collect: dict[str, object] = json.loads(stdout)["self_test"]["collect"]
    return collect


def _project(root: Path) -> None:
    (root / "src").mkdir(parents=True)
    (root / "src" / "lib.rs").write_text("")
    (root / "Cargo.toml").write_text('[package]\nname = "p"\nversion = "0.0.0"\nedition = "2021"\n')
    config = '[scan]\nlanguage = "rust"\nroots = ["src"]\nnamespace = "p"\ncontract = "c.json"\n'
    (root / "archkeel.toml").write_text(config)
    (root / "c.json").write_text(json.dumps({"components": []}))


def _fill(directory: Path) -> None:
    with (directory / "build-output.rs").open("wb") as handle:
        handle.truncate(OVER_BUDGET)


def test_the_target_directory_of_a_helper_is_tagged_and_not_counted(
    built: Path, tmp_path: Path
) -> None:
    _project(tmp_path)
    commit_tree(tmp_path)
    ensure_target_dir(tmp_path)
    _fill(tmp_path / "target")
    collect = _scan(built / f"archkeel-core{SUFFIX}", tmp_path)
    assert "request" in collect, collect


def test_an_untagged_target_directory_is_refused_with_the_remedy(
    built: Path, tmp_path: Path
) -> None:
    _project(tmp_path)
    commit_tree(tmp_path)
    (tmp_path / "target").mkdir()
    _fill(tmp_path / "target")
    collect = _scan(built / f"archkeel-core{SUFFIX}", tmp_path)
    assert "CACHEDIR.TAG" in str(collect.get("refused")), collect

# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""K11: an imported module without a file is a gap that names its likely cause and the fix."""

from pathlib import Path

from test_cli_core_only_scan import command
from test_cli_python_target import target_project


def test_a_git_ignored_generated_module_names_the_ignore_rule_and_the_fix(
    release_core: Path, tmp_path: Path
) -> None:
    root = target_project(tmp_path)
    (root / "src/app/client.py").write_text("from app.gen import Thing\n")
    (root / ".gitignore").write_text("# generated\nsrc/app/gen.py\n")
    done = command(release_core, root, "--text")
    assert done.returncode == 2, done.stdout
    assert "1 x an imported module that has no file in the scan" in done.stdout
    assert "src/app/client.py:1: app.gen (no file; the ignore rule .gitignore:2 covers it" in (
        done.stdout
    )
    assert "Fix: generate or build the module before the scan" in done.stdout
    assert "project_module_not_found" not in done.stdout
    # The gap stays a gap: the verdict is not PASS, and the JSON keeps the machine reason.
    assert "project_module_not_found: app.gen" in command(release_core, root, "--json").stdout


def test_a_missing_module_without_an_ignore_rule_does_not_claim_one(
    release_core: Path, tmp_path: Path
) -> None:
    root = target_project(tmp_path)
    (root / "src/app/client.py").write_text("from app.gen import Thing\n")
    done = command(release_core, root, "--text")
    assert done.returncode == 2, done.stdout
    assert "app.gen (no file; it may be generated, or the import is wrong)" in done.stdout
    assert "ignore rule" not in done.stdout
    first = done.stdout.splitlines()[0]
    assert "all 1 rules pass; the run stays UNKNOWN because 1 gaps are open" in first

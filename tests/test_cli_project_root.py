# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""One project root for `init`, auto-init, the configuration reason, the baseline and the request.

The root is an explicit `--root`, else the top of the Git work tree (AD-735). A baseline that a
run writes is the file that the same run reads back, and `init` drafts where `validate` reads.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from core_support import HONEST, SUFFIX, case_root
from test_cli_core_only_scan import command

from archkeel.cli import core_only
from archkeel.cli.core_binding import ProjectRoot, RootMode
from tests.test_cli_init import plant

GIT = ["git", "-c", "user.email=a@b", "-c", "user.name=a"]


def _commit(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run([*GIT, "add", "-A"], cwd=root, check=True)
    subprocess.run([*GIT, "commit", "-qm", "plant"], cwd=root, check=True)


def _nested(outer: Path) -> Path:
    """A repository whose project is the folder `sub`, below the top of the work tree."""
    with case_root(HONEST) as root:
        shutil.copytree(root, outer / "sub", ignore=shutil.ignore_patterns(".git"))
    _commit(outer)
    return outer / "sub"


def _core(built: Path, root: Path, *flags: str) -> tuple[int, dict[str, object]]:
    done = command(built / f"archkeel-core{SUFFIX}", root, "--json", *flags)
    assert "Traceback" not in done.stderr, done.stderr
    return done.returncode, json.loads(done.stdout)


def test_a_baseline_written_with_an_explicit_root_is_read_back(built: Path, tmp_path: Path) -> None:
    sub = _nested(tmp_path)
    code, result = _core(built, sub, "--write-baseline", "b.json")
    assert code == 0, result
    assert (sub / "b.json").is_file() and not (tmp_path / "b.json").exists()
    code, result = _core(built, sub, "--baseline", "b.json")
    assert code == 0, result
    assert result["baseline"]["state"] == "current"  # type: ignore[index]


def test_init_in_a_folder_of_a_work_tree_drafts_at_the_top(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    plant(tmp_path)  # a committed Git work tree
    (tmp_path / "docs").mkdir()
    monkeypatch.chdir(tmp_path / "docs")
    code = core_only.run(["init", "--json"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert (tmp_path / "archkeel.toml").is_file()
    assert not (tmp_path / "docs" / "archkeel.toml").exists()


def test_the_configuration_reason_looks_where_the_core_looked(
    built: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sub = _nested(tmp_path)
    (sub / "other.toml").write_text("[scan]\n", encoding="utf-8")
    monkeypatch.chdir(sub)
    # AD-776: with --root, a relative --config is below the root, where the core reads it.
    flags = ("--json", "--config", "other.toml")
    done = command(built / f"archkeel-core{SUFFIX}", tmp_path, *flags)
    message = json.loads(done.stdout)["refusal"]["message"]
    assert done.returncode == 2
    assert "the file does not exist" in message, message
    assert "exists but cannot be read" not in message


def test_text_header_uses_absolute_paths_outside_the_current_directory(tmp_path: Path) -> None:
    project = ProjectRoot(tmp_path / "project", RootMode.EXPLICIT)
    assert project.named(tmp_path / "other") == (
        str(project.path),
        str(project.path / "archkeel.toml"),
    )
    assert project.named(tmp_path) == ("project", str(Path("project", "archkeel.toml")))


@pytest.mark.skipif(sys.platform == "win32", reason="requires symbolic link privileges")
def test_absolute_text_header_keeps_the_spelling_of_an_explicit_root(tmp_path: Path) -> None:
    target = tmp_path / "project"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    project = ProjectRoot.of(alias, "custom.toml")
    assert project.path == target.resolve()
    assert project.named(tmp_path / "other") == (str(alias), str(alias / "custom.toml"))

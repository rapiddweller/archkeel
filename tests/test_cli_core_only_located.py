# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Without `--root`, a configuration of another repository names its own root (AD-606)."""

from pathlib import Path

import pytest

from archkeel.cli.core_arguments import parse
from archkeel.cli.core_only import _located


def repository(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    (project / ".git").mkdir(parents=True)
    (project / "archkeel.toml").write_text("[scan]\n", encoding="utf-8")
    return project


def test_a_configuration_of_another_repository_names_its_git_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = repository(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    for config in (str(project / "archkeel.toml"), "../project/archkeel.toml"):
        options = _located(parse(["report", "--config", config]))
        assert (options.root, options.config) == (project.resolve(), "archkeel.toml")


def test_a_configuration_inside_the_working_repository_and_an_explicit_root_stay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = repository(tmp_path)
    monkeypatch.chdir(project)
    options = _located(parse(["report", "--config", "archkeel.toml"]))
    assert (options.root, options.config) == (None, "archkeel.toml")
    other = tmp_path / "other"
    explicit = _located(parse(["report", "--root", str(other), "--config", "x.toml"]))
    assert (explicit.root, explicit.config) == (other, "x.toml")

# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Without `--root`, a configuration names its own root (AD-606, AD-776).

The folder of the file is the root, also for a file of another repository; an explicit root keeps
the configuration below it.
"""

from pathlib import Path

import pytest

from archkeel.cli.core_binding import ProjectRoot, RootMode


def repository(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    (project / ".git").mkdir(parents=True)
    (project / "archkeel.toml").write_text("[scan]\n", encoding="utf-8")
    return project


def test_a_configuration_of_another_repository_names_its_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = repository(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    for config in (str(project / "archkeel.toml"), "../project/archkeel.toml"):
        found = ProjectRoot.of(None, config)
        assert (found.path, found.config, found.mode) == (
            project.resolve(),
            "archkeel.toml",
            RootMode.CONFIG,
        )


def test_a_configuration_inside_the_working_repository_and_an_explicit_root_stay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = repository(tmp_path)
    monkeypatch.chdir(project)
    found = ProjectRoot.of(None, "archkeel.toml")
    assert (found.path, found.config) == (project.resolve(), "archkeel.toml")
    other = tmp_path / "other"
    explicit = ProjectRoot.of(other, "x.toml")
    assert (explicit.path, explicit.config, explicit.mode) == (
        other.resolve(),
        "x.toml",
        RootMode.EXPLICIT,
    )

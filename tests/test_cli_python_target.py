# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Python target selection reaches the collector, the verdict and the text summary."""

import json
from pathlib import Path

import pytest
from test_cli_core_only_scan import command
from test_cli_native_python_imports import BASE, RULE, component, project


def target_project(root: Path) -> Path:
    """A project with no unresolved component-dependency decisions."""
    project(root, BASE)
    contract = {
        "schema_version": "2.2.0",
        "components": [component("root", ["app"])],
        "rules": [{**RULE, "id": "ASSIGN", "kind": "complete_assignment", "source": "app"}],
    }
    (root / "architecture-contract.json").write_text(json.dumps(contract))
    return root


def test_python_target_is_selected_from_the_project_requirement(
    release_core: Path, tmp_path: Path
) -> None:
    """A Python 3.13 project must not be checked against the collector's 3.14 default."""
    root = target_project(tmp_path)
    (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.13,<3.14"\n')
    done = command(release_core, root, "--text")
    assert done.returncode == 0, done.stdout
    assert "Python 3.13" in done.stdout
    assert ">=3.13,<3.14" in done.stdout


def test_python_target_can_be_selected_and_an_unsupported_target_is_named(
    release_core: Path, tmp_path: Path
) -> None:
    """The configuration selects a supported target and names the supported range otherwise."""
    root = target_project(tmp_path)
    config = root / "archkeel.toml"
    config.write_text(config.read_text() + 'python = "3.13"\n')
    done = command(release_core, root, "--text")
    assert done.returncode == 0, done.stdout
    assert "Python 3.13" in done.stdout
    config.write_text(config.read_text().replace('python = "3.13"', 'python = "3.10"'))
    done = command(release_core, root, "--text")
    assert done.returncode == 2, done.stdout
    assert "3.10" in done.stdout and "3.11" in done.stdout and "3.14" in done.stdout
    assert "python =" in done.stdout


def test_python_target_selects_the_parser_grammar(release_core: Path, tmp_path: Path) -> None:
    """A type statement is valid from Python 3.12, but not on Python 3.11."""
    root = target_project(tmp_path)
    (root / "src/app/client.py").write_text("type Item = int\n")
    config = root / "archkeel.toml"
    original = config.read_text()
    config.write_text(original + 'python = "3.11"\n')
    before = command(release_core, root, "--json")
    assert json.loads(before.stdout)["status"] == "UNKNOWN", before.stdout
    config.write_text(original + 'python = "3.12"\n')
    after = command(release_core, root, "--json")
    assert json.loads(after.stdout)["status"] == "PASS", after.stdout


def test_python_target_mismatch_keeps_the_gap_and_names_both_versions(
    release_core: Path, tmp_path: Path
) -> None:
    """An explicitly selected target that the project excludes cannot produce PASS."""
    root = target_project(tmp_path)
    (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.13,<3.14"\n')
    config = root / "archkeel.toml"
    config.write_text(config.read_text() + 'python = "3.12"\n')
    done = command(release_core, root, "--text")
    assert done.returncode == 2, done.stdout
    assert "Python 3.12" in done.stdout and ">=3.13,<3.14" in done.stdout


@pytest.mark.parametrize("metadata", [None, "[project]\n"])
def test_python_target_defaults_when_no_requirement_exists(
    release_core: Path, tmp_path: Path, metadata: str | None
) -> None:
    """An absent requirement uses the named default, not a fictional interpreter."""
    root = target_project(tmp_path / "project")
    if metadata is None:
        (root / "pyproject.toml").rename(tmp_path / "saved-pyproject.toml")
    else:
        (root / "pyproject.toml").write_text(metadata)
    done = command(release_core, root, "--text")
    assert done.returncode == 0, done.stdout
    assert "Python 3.14" in done.stdout and "collector default" in done.stdout


@pytest.mark.parametrize("requirement", ["''", '"invalid"'])
def test_a_configured_python_target_does_not_forgive_an_invalid_requirement(
    release_core: Path, tmp_path: Path, requirement: str
) -> None:
    root = target_project(tmp_path)
    config = root / "archkeel.toml"
    config.write_text(config.read_text() + 'python = "3.13"\n')
    (root / "pyproject.toml").write_text(f"[project]\nrequires-python = {requirement}\n")
    done = command(release_core, root, "--json")
    assert done.returncode == 2, done.stdout
    assert json.loads(done.stdout)["status"] == "UNKNOWN", done.stdout


def test_a_range_below_3_11_that_reaches_it_is_read_as_3_11_and_says_so(
    release_core: Path, tmp_path: Path
) -> None:
    """K14: `>=3.10` (pydantic) is not a refusal; 3.11 is the lowest supported version inside."""
    root = target_project(tmp_path)
    for requires, unsupported in (
        (">=3.10", "Python 3.10 is"),
        (">=3.9", "Python 3.9 and 3.10 are"),
    ):
        (root / "pyproject.toml").write_text(f'[project]\nrequires-python = "{requires}"\n')
        done = command(release_core, root, "--text")
        assert done.returncode == 0, done.stdout
        assert "reads this project as Python 3.11" in done.stdout, done.stdout
        assert f'requires-python "{requires}"' in done.stdout
        assert f"{unsupported} not supported" in done.stdout, done.stdout


def test_a_range_entirely_below_3_11_keeps_the_refusal(release_core: Path, tmp_path: Path) -> None:
    root = target_project(tmp_path)
    (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.9,<3.11"\n')
    done = command(release_core, root, "--text")
    assert done.returncode == 2, done.stdout
    assert "unsupported" in done.stdout and "3.11" in done.stdout and "python =" in done.stdout

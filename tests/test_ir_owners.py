# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-432: the Python core has no owner, because its packages do not exist.

AD-315 gave the Python IR four owners. This file checked their direction. The Rust core owns the
model, the facts and the verdicts now, so the check that stays is that the packages are gone and
that the Python shell is the closed set of modules below.
"""

import importlib
import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "src/archkeel"
DELETED = ("ir", "check", "analyzer")
# Each module of the shell. A new module is a decision: add it here with its task in AD-432.
SHELL = frozenset(
    (
        "__init__.py",
        "cli/__init__.py",
        "cli/__main__.py",
        "cli/core_binary.py",
        "cli/core_binding.py",
        "cli/core_evidence.py",
        "cli/core_trojan_horses.py",
        "cli/core_baseline.py",
        "cli/core_explain.py",
        "cli/core_explorer.py",
        "cli/core_explorer_http.py",
        "cli/core_explorer_identity.py",
        "cli/core_explorer_scip.py",
        "cli/core_exit.py",
        "cli/core_frame.py",
        "cli/core_help.py",
        "cli/core_gaps.py",
        "cli/core_text.py",
        "cli/core_words.py",
        "cli/core_arguments.py",
        "cli/core_json.py",
        "cli/init_draft.py",
        "cli/init_areas.py",
        "cli/init_binding.py",
        "cli/init_typescript.py",
        "cli/init_preset.py",
        "cli/core_init.py",
        "cli/core_schema.py",
        "cli/core_only.py",
        "cli/core_delivery.py",
        "cli/core_guide.py",
        "cli/core_topology.py",
        "cli/core_output.py",
        "cli/native_scan.py",
        "cli/skill.py",
        "cli/story_model.py",
        "explorer_agent.py",
        "explorer_boundaries.py",
        "explorer_hierarchy.py",
        "explorer_map.py",
        "explorer_mcp.py",
        "explorer_queries.py",
        "explorer_source.py",
        "explorer_store.py",
        "explorer_stories.py",
        "explorer_story_external.py",
        "explorer_story_spec.py",
        "explorer_story_sql.py",
        "explorer_symbols.py",
        "explorer_verdict.py",
    )
)


def _tracked_python() -> frozenset[str]:
    names = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", "*.py"],
        cwd=SOURCE,
        text=True,
    ).split("\0")
    return frozenset(name for name in names if name and (SOURCE / name).is_file())


@pytest.mark.parametrize("package", DELETED)
def test_the_python_core_package_does_not_exist(package: str) -> None:
    assert not (SOURCE / package).exists(), f"src/archkeel/{package} is back"
    assert importlib.util.find_spec(f"archkeel.{package}") is None
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(f"archkeel.{package}")


def test_the_python_shell_is_a_closed_set_of_modules() -> None:
    tracked = _tracked_python()
    assert sorted(tracked - SHELL) == [], "a Python module that AD-432 does not name"
    assert sorted(SHELL - tracked) == []


def test_no_shell_module_names_a_deleted_package() -> None:
    hits = [
        f"{name}: archkeel.{package}"
        for name in sorted(SHELL)
        for package in DELETED
        if f"archkeel.{package}" in (SOURCE / name).read_text(encoding="utf-8")
    ]
    assert hits == []

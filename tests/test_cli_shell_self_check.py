# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-478: the core decides each rule of the contract of the Python shell (#880).

The tests copy `src/archkeel` and the shell contract into a Git repository, run the default
`archkeel validate` with the core of this build, and require a usable result without FAIL or
violation, as `make self-validate-shell` does (AD-1260). No status or gap count is pinned.
Planted imports show that a rule can fail, and one mounted contract of `native/` shows what a
mixed tree gives today.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from core_support import ROOT, SUFFIX, copy_cited, run
from corpus_support import commit_tree

from archkeel.cli import core_only

sys.path.insert(0, str(ROOT / "tools"))
import self_check_summary  # noqa: E402
from self_check_gate import problems  # noqa: E402

CONFIG = "docs/architecture/shell.toml"
CONTRACT = "docs/architecture/target/shell-contract.json"
DECIDED_KINDS = {
    "complete_assignment",
    "complete_requires",
    "complete_external_scope",
    "external_dependency_scope",
    "forbidden_dependency",
    "interface_boundary",
    "layer_order",
    "no_component_cycles",
    "unused_public",
}


@pytest.fixture
def shell_tree(tmp_path: Path) -> Iterator[Path]:
    """A Git repository with the shell source and its contract, as they are in this checkout."""
    root = tmp_path / "shell"
    shutil.copytree(
        ROOT / "src/archkeel",
        root / "src/archkeel",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    for name in (CONFIG, CONTRACT, "native/architecture-contract.json", "pyproject.toml"):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, root / name)
    copy_cited(root, ROOT, CONTRACT)
    yield root


def decide(root: Path, built: Path) -> tuple[int, dict[str, Any]]:
    commit_tree(root)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(core_only, "locate_core", lambda: built / f"archkeel-core{SUFFIX}")
        return run("validate", "--root", str(root), "--config", CONFIG)


def test_the_core_decides_each_rule_of_the_shell_contract(shell_tree: Path, built: Path) -> None:
    code, result = decide(shell_tree, built)
    frame = result["frame"]
    assert problems(result) == []
    core = {rule: row[1] for rule, row in frame["rules"].items()}
    assert core, "the shell contract has rules"
    assert code in (0, 2) and result["status"] == frame["status"]


def test_a_planted_import_fails_the_rule_that_names_it(shell_tree: Path, built: Path) -> None:
    plants = {
        "core_binary.py": "from .core_frame import Status\n",
        "core_json.py": "import subprocess\n",
        "core_output.py": "import requests\n",
        "core_frame.py": "from .core_only import run\n",
    }
    for name, line in plants.items():
        path = shell_tree / "src/archkeel/cli" / name
        path.write_text(path.read_text() + line)
    code, result = decide(shell_tree, built)
    failing = {rule for rule, row in result["frame"]["rules"].items() if row[1] == "FAIL"}
    assert {
        "SHELL-NO-LOCATE-TO-FRAME",
        "SHELL-ONLY-LAUNCH-STARTS-A-PROCESS",
        "SHELL-EXTERNAL-COMPLETE",
        "SHELL-NO-FRAME-TO-COMMANDS",
        "SHELL-REQUIRES-COMPLETE",
        "SHELL-NO-COMPONENT-CYCLES",
    } <= failing
    assert (code, result["status"]) == (1, "FAIL")


def test_a_contract_of_native_mounted_in_the_python_scan_decides_nothing(
    shell_tree: Path, built: Path
) -> None:
    """One scan has one profile and one namespace: the Rust packages of `native/` lie outside the
    Python namespace, so the mount makes the whole run UNKNOWN and no mounted row can PASS."""
    copy_cited(shell_tree, ROOT, "native/architecture-contract.json")
    path = shell_tree / CONTRACT
    document = json.loads(path.read_text())
    document["components"].append(
        {
            "id": "SHELL-NATIVE",
            "label": "native",
            "role": "component",
            "layer": "foundation",
            "packages": ["native"],
            "inside": "native/architecture-contract.json",
            "responsibilities": ["The Rust core."],
            "forbidden_responsibilities": ["Python source."],
            "provenance": ["docs/architecture/shell.md"],
            "requires": [],
            "decided_by": "architect",
        }
    )
    path.write_text(json.dumps(document))
    code, result = decide(shell_tree, built)
    rows = result["frame"]["rules"]
    assert any(rule.startswith("native:") for rule in rows)
    assert {row[1] for rule, row in rows.items() if rule.startswith("native:")} == {"UNKNOWN"}
    # A violation of the shell is a fact also in an incomplete scope; the shell has none.
    failing = {rule for rule, row in rows.items() if row[1] == "FAIL"}
    assert failing == set()
    assert "PASS" not in {row[1] for row in rows.values()}
    assert "outside the namespace" in result["frame"]["scope"]
    assert (code, result["status"]) == (2, "UNKNOWN")


def test_the_summary_lists_a_planted_import_with_its_place(
    shell_tree: Path, built: Path, tmp_path: Path
) -> None:
    """AD-1088: the text of `make self-check` names a new violation with its file and line."""
    (shell_tree / "tests").mkdir()

    def lines() -> list[str]:
        commit_tree(shell_tree)
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(core_only, "locate_core", lambda: built / f"archkeel-core{SUFFIX}")
            _code, result = run(
                "report", "--root", str(shell_tree), "--config", CONFIG, "--topology"
            )
        path = tmp_path / "validation-shell/result.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(result), encoding="utf-8")
        text = self_check_summary.summary(tmp_path, shell_tree, 0, "x.log")
        assert len(text) <= self_check_summary.MAX_LINES
        return text

    assert "violations: 0" in lines()
    core_json = shell_tree / "src/archkeel/cli/core_json.py"
    core_json.write_text(core_json.read_text() + "import subprocess\n")
    found = lines()
    count = next(line for line in found if line.startswith("violations: "))
    assert count != "violations: 0"
    assert any("src/archkeel/cli/core_json.py:" in line for line in found)


def test_the_contract_states_every_rule_with_a_decided_kind_and_real_provenance() -> None:
    document = json.loads((ROOT / CONTRACT).read_text())
    assert {rule["kind"] for rule in document["rules"]} <= DECIDED_KINDS
    for item in [*document["components"], *document["rules"]]:
        assert item.get("rationale", "x") and item["provenance"]
        assert [name for name in item["provenance"] if not (ROOT / name).is_file()] == []
    assert len({rule["id"] for rule in document["rules"]}) == len(document["rules"])


def test_each_module_of_the_shell_has_a_component_and_each_component_a_graph_node() -> None:
    document = json.loads((ROOT / CONTRACT).read_text())
    owned = {name for c in document["components"] for name in c["exact_modules"]}
    modules = {
        ".".join(path.relative_to(ROOT / "src").with_suffix("").parts).removesuffix(".__init__")
        for path in (ROOT / "src/archkeel").rglob("*.py")
    }
    assert modules == owned
    page = (ROOT / "docs/architecture/shell.md").read_text()
    block = page.split("<!-- archkeel-component-graph -->", 1)[1].split("```", 2)[1]
    nodes = dict(re.findall(r'n_(\d+)\["([^"]+)"\]', block))
    assert set(nodes.values()) == {c["label"] for c in document["components"]}
    drawn = {(nodes[a], nodes[b]) for a, b in re.findall(r"n_(\d+) --> n_(\d+)", block)}
    declared = {(c["label"], r["component"]) for c in document["components"] for r in c["requires"]}
    assert drawn == declared

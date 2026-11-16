# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1314 (AD-626): a new project reaches a first verdict by following the CLI output only.

The plant is a Python package with three subpackages and no `archkeel.toml`. The walk is the one of
docs/onboarding.md: refusal that names `init`, draft, open verdict, decisions, PASS, then FAIL.
"""

import json
import subprocess
from pathlib import Path

import pytest

from archkeel.cli import core_only
from archkeel.cli.init_draft import NothingToDraft, draft

GIT = ["git", "-c", "user.email=a@b", "-c", "user.name=a"]


def plant(root: Path, *, python_range: bool = True) -> Path:
    """A `src/shop` package: billing -> orders -> catalog, and one module beside them."""
    files = {
        "src/shop/__init__.py": "",
        "src/shop/cli.py": "",
        "src/shop/billing/__init__.py": "",
        "src/shop/billing/pay.py": "from shop.orders import service\n",
        "src/shop/orders/__init__.py": "",
        "src/shop/orders/service.py": "from shop.catalog import items\n",
        "src/shop/catalog/__init__.py": "",
        "src/shop/catalog/items.py": "def get(): return 1\n",
        "pyproject.toml": '[project]\nname = "shop"\nversion = "0"\n'
        + ('requires-python = ">=3.11"\n' if python_range else ""),
    }
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run([*GIT, "add", "-A"], cwd=root, check=True)
    subprocess.run([*GIT, "commit", "-qm", "plant"], cwd=root, check=True)
    return root


def run(
    capsys: pytest.CaptureFixture[str], root: Path, *argv: str
) -> tuple[int, dict[str, object]]:
    code = core_only.run([*argv, "--root", str(root), "--json"])
    return code, json.loads(capsys.readouterr().out)


def decided(document: dict[str, object]) -> str:
    frame = document["frame"]
    assert isinstance(frame, dict)
    return json.dumps([document["status"], document["gaps"], frame.get("rules")])


def test_a_project_without_configuration_gets_a_draft_not_a_dead_end(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """#1314, then AD-638: the project without `archkeel.toml` reaches a verdict by itself."""
    code, document = run(capsys, plant(tmp_path), "validate")
    assert code == 2 and document["status"] == "UNKNOWN" and "refusal" not in document
    assert "archkeel.toml" in document["init"]["written"]  # type: ignore[index]


def test_init_drafts_one_component_for_each_subpackage_and_the_walk_ends_in_pass_and_fail(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = plant(tmp_path)
    code, document = run(capsys, root, "init")
    assert code == 0 and document["components"] == ["billing", "catalog", "orders", "root"]
    assert (root / "archkeel.toml").read_text(encoding="utf-8").splitlines()[1:3] == [
        'language = "python"',
        'namespace = "shop"',
    ]
    # The draft decides nothing: the core names every open responsibility; the verdict is no PASS.
    code, first = run(capsys, root, "validate")
    gaps = first["gaps"]
    assert isinstance(gaps, list)
    subjects = [gap["subject"] for gap in gaps]
    assert code == 2 and first["status"] == "UNKNOWN"
    opened = [s for s in subjects if s.startswith("hygiene:responsibility.missing")]
    assert len(opened) == 4, subjects
    # K13: the text says why a run of passing rules stays UNKNOWN.
    assert core_only.run(["validate", "--root", str(root), "--text"]) == 2
    text = capsys.readouterr().out
    head = text.splitlines()[0]
    assert "the run stays UNKNOWN because the contract draft has" in head
    assert head.startswith("validate: UNKNOWN -> exit 2 (all ")
    # A second init replaces nothing.
    code, again = run(capsys, root, "init")
    refused = again["refusal"]
    assert isinstance(refused, dict) and code == 2 and refused["kind"] == "io_error"
    # The user decides: responsibilities, rationales, the dependencies and the drawn graph.
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text(encoding="utf-8"))
    needs = {"billing": ["orders"], "orders": ["catalog"]}
    for component in contract["components"]:
        component["responsibilities"] = [f"Owns {component['label']}."]
        listed = needs.get(component["label"], [])
        component["requires"] = [
            {"component": target, "rationale": f"{component['label']} calls {target}."}
            for target in listed
        ]
    for rule in contract["rules"]:
        rule["rationale"] = "The architecture stays acyclic and every module has one owner."
    contract["rules"].append(
        {
            "id": "REQUIRES-COMPLETE",
            "kind": "complete_requires",
            "rationale": "Only the listed dependencies are decided.",
            "provenance": ["docs/architecture/architecture.md"],
            "decided_by": "architect",
        }
    )
    path.write_text(json.dumps(contract), encoding="utf-8")
    graph = "graph TD\n    billing --> orders\n    orders --> catalog\n    root\n"
    (root / "docs/architecture/architecture.md").write_text(
        f"# A\n\n<!-- archkeel-component-graph -->\n```mermaid\n{graph}```\n", encoding="utf-8"
    )
    code, second = run(capsys, root, "validate")
    assert (code, second["status"]) == (0, "PASS"), decided(second)
    # An import against the decision is a FAIL with the edge.
    (root / "src/shop/catalog/items.py").write_text("from shop.billing import pay\n", "utf-8")
    code, third = run(capsys, root, "validate")
    assert (code, third["status"]) == (1, "FAIL"), decided(third)


def test_a_layout_without_a_package_is_refused_with_the_manual_way(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    with pytest.raises(NothingToDraft, match=r"no top-level Python package.*onboarding\.md"):
        draft(tmp_path)


def test_a_project_without_a_python_range_gets_the_note_that_names_the_cause(
    tmp_path: Path,
) -> None:
    assert "requires-python" in draft(plant(tmp_path, python_range=False)).note

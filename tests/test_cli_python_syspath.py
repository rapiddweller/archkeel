# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-538: a `sys.path.append` that adds no imported name is no gap; each other write is.

Consumer: a CI job that reads `archkeel validate` on a Python project with a Poetry/Alembic style
`sys.path.append(str(Path(__file__).resolve().parents[k]))`. The control gives each rule PASS (the
gap of the whole run is gone). Every plant of `python_syspath_plants.py` keeps the gap: the rules
are UNKNOWN and the reason is `import_system_change`. Release 4.0.1 reads no `sys.path` write, so
it gives PASS for all of them; the core is stricter, never weaker.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from python_syspath_plants import CONTROL, Plant, plants
from test_cli_native_python_imports import RULE, project, rows, rules, verdict

PLANTS = plants()
DECIDED = [*rules(), {**RULE, "id": "REQUIRES", "kind": "complete_requires"}]
NAMES = ["FORBID", "ASSIGN", "CYCLES", "EXTERNAL", "REQUIRES"]


def tree(root: Path, plant: Plant) -> Path:
    """The tree of a plant: the scan root `app` (as K-python-realworld), or `src/app`."""
    base = "src/app" if plant.roots != '["app"]' else "app"
    files: dict[str, str | None] = {
        f"{base}/__init__.py": "",
        f"{base}/client.py": plant.client,
        f"{base}/service.py": "VALUE = 1\n",
        "pyproject.toml": '[project]\nrequires-python = ">=3.11"\n',
    }
    files.update(plant.files)
    written = {name: text for name, text in files.items() if text is not None}
    made = project(root, written, roots=plant.roots, contract_rules=DECIDED)
    for name, target in plant.links:
        (made / name).symlink_to(target)
    return made


def test_the_form_of_k_is_no_gap_and_each_rule_passes(release_core: Path, tmp_path: Path) -> None:
    control = Plant("control", CONTROL)
    result = verdict(release_core, tree(tmp_path, control))
    assert rows(result) == dict.fromkeys(NAMES, "PASS"), result["frame"]["explained"]
    assert (result["status"], result["exit_code"]) == ("PASS", 0)


def test_comprehension_local_has_no_import_gap_but_site_module_does(
    release_core: Path, tmp_path: Path
) -> None:
    """The target of a comprehension is not the standard library module of the same name."""
    local = Plant("local", "result = {site.id: site for site in sites}\n" * 13)
    result = verdict(release_core, tree(tmp_path / "local", local))
    assert "import_system_change" not in json.dumps(result)
    assert rows(result) == dict.fromkeys(NAMES, "PASS")

    module = Plant("module", "import site\nsite.addsitedir('x')\n")
    result = verdict(release_core, tree(tmp_path / "module", module))
    assert "import_system_change" in json.dumps(result)
    assert result["status"] == "UNKNOWN"


@pytest.mark.parametrize("plant", PLANTS, ids=[plant.name for plant in PLANTS])
def test_each_other_write_keeps_the_gap_of_the_whole_run(
    release_core: Path, tmp_path: Path, plant: Plant
) -> None:
    result = verdict(release_core, tree(tmp_path, plant))
    found = rows(result)
    # A plant that imports an external name has the row EXTERNAL FAIL; the gap holds each other row.
    assert result["status"] != "PASS" and result["exit_code"] != 0, (plant.name, found)
    assert "import_system_change" in json.dumps(result), plant.name
    assert {found[name] for name in ("ASSIGN", "CYCLES", "FORBID")} == {"UNKNOWN"}, (
        plant.name,
        found,
    )


@pytest.mark.skipif(os.name == "nt", reason="needs a symbolic link")
def test_a_writer_below_a_linked_directory_keeps_the_gap(
    release_core: Path, tmp_path: Path
) -> None:
    root = tmp_path / "p"
    root.mkdir()
    (root / "shared").mkdir()
    (root / "shared" / "w.py").write_text(CONTROL.replace("parents[1]", "parents[2]"))
    (root / "app").mkdir()
    (root / "app" / "link").symlink_to("../shared")
    result = verdict(release_core, tree(root, Plant("link", CONTROL)))
    # The link is a gap of its own (a linked directory below a root); the control alone passes.
    assert result["status"] == "UNKNOWN" and result["exit_code"] == 2

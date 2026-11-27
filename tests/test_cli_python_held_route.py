# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#2198: a held facade route is no reason to remove a public entry.

Consumer: a team that reads `interface.usage_unknown` for an entry that a facade re-exports.
When the collector withholds the route through the facade (a script outside the scan roots), the
gap is `route_held`: it names the cause and gives no removal hint. A proven route passes. An entry
that no import names stays `no_import_found` and removable.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from test_cli_native_python_imports import BASE, RULE, component, project, verdict

HOLD = 'import importlib.resources\nimportlib.resources.files("app")\n'
SERVICE = "def run() -> None:\n    pass\n"
UNUSED = "app.other:unused"


def tree(root: Path, *, facade_in_service: bool, script: str | None, public: list[str]) -> Path:
    """`client` calls `run` through `app.facade`, which re-exports it from `app.service`."""
    files = {
        **BASE,
        "src/app/service.py": SERVICE,
        "src/app/other.py": "def unused() -> None:\n    pass\n",
        "src/app/facade/__init__.py": "from app.service import run\n",
        "src/app/client.py": "from app.facade import run\n\nrun()\n",
        **({"scripts/tool.py": script} if script else {}),
    }
    rules = [{**RULE, "id": "INTERFACE", "kind": "interface_boundary"}]
    project(root, files, contract_rules=rules)
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    uses = "service" if facade_in_service else "facade"
    if not facade_in_service:
        contract["components"].append(component("facade", ["app.facade"], ["service"]))
    for part in contract["components"]:
        if part["label"] == "service":
            part["public"] = public
            part["packages"] = ["app.service", "app.other"]
            if facade_in_service:
                part["packages"].append("app.facade")
        if part["label"] == "facade":
            part["public"] = ["app.facade:run"]
        if part["label"] == "client":
            part["requires"] = [{"component": uses, "rationale": "Use it."}]
    path.write_text(json.dumps(contract))
    who = ["-c", "user.name=t", "-c", "user.email=t@t"]
    for step in (["add", "-A"], [*who, "commit", "-qm", "facade"]):
        subprocess.run(["git", "-C", str(root), *step], check=True, capture_output=True)
    return root


def actions(result: dict[str, Any], entry: str) -> list[str | None]:
    """The action word of the `usage_unknown` gap of one public entry (the frame states it)."""
    gaps = result["frame"]["gaps"]
    return [
        g.get("action")
        for g in gaps
        if g["kind"] == "interface.usage_unknown" and g["subject"].endswith(entry)
    ]


def holds(result: dict[str, Any]) -> dict[str, str]:
    """The text of each `usage_unknown` gap, by public entry."""
    rows = result["frame"]["unsupported"]["rules"]
    return {
        name.rsplit(":", 2)[-2] + ":" + name.rsplit(":", 1)[-1]: text
        for name, text in rows.items()
        if name.startswith("hygiene:interface.usage_unknown:")
    }


@pytest.mark.parametrize("facade_in_service", [False, True], ids=["own-facade", "same-component"])
def test_a_held_route_is_unknown_names_its_cause_and_gives_no_removal_hint(
    release_core: Path, tmp_path: Path, facade_in_service: bool
) -> None:
    root = tree(
        tmp_path, facade_in_service=facade_in_service, script=HOLD, public=["app.service:run"]
    )
    result = verdict(release_core, root)
    assert result["frame"]["rules"]["INTERFACE"][1] == "UNKNOWN"
    text = holds(result)["app.service:run"]
    assert "held, not absent" in text and "does not recommend removing" in text, text
    assert "outside_write" in text, text
    assert "Remove the entry" not in text and "delete" not in text, text
    assert actions(result, "app.service:run") == ["route_held"]


@pytest.mark.parametrize("facade_in_service", [False, True], ids=["own-facade", "same-component"])
def test_a_proven_route_has_no_hold(
    release_core: Path, tmp_path: Path, facade_in_service: bool
) -> None:
    public = ["app.service:run", "app.facade:run"] if facade_in_service else ["app.service:run"]
    root = tree(tmp_path, facade_in_service=facade_in_service, script=None, public=public)
    result = verdict(release_core, root)
    assert holds(result) == {}, result["frame"]["unsupported"]["rules"]
    assert result["frame"]["rules"]["INTERFACE"][1] == "PASS", result["frame"]["details"]


def test_an_entry_that_no_import_names_is_still_removable(
    release_core: Path, tmp_path: Path
) -> None:
    root = tree(tmp_path, facade_in_service=False, script=None, public=["app.service:run", UNUSED])
    result = verdict(release_core, root)
    found = holds(result)
    assert list(found) == [UNUSED], found
    assert "Remove the entry from `public`" in found[UNUSED], found
    assert actions(result, UNUSED) == ["no_import_found"]


def test_a_held_route_to_another_name_does_not_hide_an_unused_entry(
    release_core: Path, tmp_path: Path
) -> None:
    """The hold names `run`; the entry `unused` is named by no import, held or proven."""
    root = tree(tmp_path, facade_in_service=False, script=HOLD, public=["app.service:run", UNUSED])
    found = holds(verdict(release_core, root))
    assert "held, not absent" in found["app.service:run"]
    assert "Remove the entry from `public`" in found[UNUSED], found

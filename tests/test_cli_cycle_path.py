# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1657 (AD-786): the text and JSON outputs of a component cycle give its closed path in import
order, with one import site for each step.

The plant has the shape of the `pydantic-core` cycle: `root` imports the other components and two
of them import back through it. The members sorted are `argument_markers, build_tools, root,
tools`, and no import `argument_markers -> build_tools` exists, so printing the sorted members
with arrows shows a false path.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from core_support import EMPTY_GRAPH
from test_cli_core_only_scan import command
from test_cli_native_python_imports import RULE, component, rows, verdict

FILES = {
    "src/app/__init__.py": "import app.argument_markers\nimport app.build_tools\n",
    "src/app/argument_markers.py": "import app.tools\n",
    "src/app/build_tools.py": "VALUE = 1\nimport app\n",
    "src/app/tools.py": "VALUE = 2\nimport app\n",
}
PATH = ["argument_markers", "tools", "root", "argument_markers"]
SITES = ["src/app/argument_markers.py:1", "src/app/tools.py:2", "src/app/__init__.py:1"]


def plant(root: Path) -> Path:
    for name, text in FILES.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    (root / "p").write_text(EMPTY_GRAPH)
    (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (root / "archkeel.toml").write_text(
        '[scan]\nlanguage = "python"\nroots = ["src"]\nnamespace = "app"\n'
        'contract = "architecture-contract.json"\n'
    )
    components = [component("root", ["app"], exact=True)] + [
        component(name, [f"app.{name}"]) for name in ("argument_markers", "build_tools", "tools")
    ]
    contract = {
        "schema_version": "2.2.0",
        "components": components,
        "rules": [{**RULE, "id": "CYCLES", "kind": "no_component_cycles"}],
    }
    (root / "architecture-contract.json").write_text(json.dumps(contract))
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t"}
    env |= {"GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    for step in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "init"]):
        subprocess.run(["git", "-C", str(root), *step], check=True, env=env)
    return root


def test_the_json_detail_of_a_cycle_gives_its_closed_path_and_its_sorted_members(
    release_core: Path, tmp_path: Path
) -> None:
    result = verdict(release_core, plant(tmp_path))
    assert rows(result) == {"CYCLES": "FAIL"}
    [detail] = result["frame"]["details"]["CYCLES"]
    assert detail["members"] == ["argument_markers", "build_tools", "root", "tools"]
    path = detail["path"]
    assert [step["from"] for step in path] + [path[-1]["to"]] == PATH
    locations = result["frame"]["locations"]
    sites = [locations[step["evidence"]] for step in path]
    assert [f"{site['path']}:{site['line']}" for site in sites] == SITES
    # The identity that the baseline reads stays the sorted set (AD-546).
    assert detail["source"] == "argument_markers -> build_tools -> root -> tools"


def test_the_text_of_a_cycle_shows_the_closed_path_with_one_site_for_each_step(
    release_core: Path, tmp_path: Path
) -> None:
    done = command(release_core, plant(tmp_path), "--text")
    expected = f"CYCLES: contract graph cycle: {' -> '.join(PATH)} ({', '.join(SITES)})"
    assert expected in done.stdout, done.stdout
    assert "argument_markers -> build_tools" not in done.stdout

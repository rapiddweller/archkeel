# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-466: the topology of a Python project types an import of the platform or of a library."""

import json
from pathlib import Path
from typing import Any

from corpus_support import commit_tree
from rust_repository import component
from test_cli_core_only_scan import command

FILES = {
    "src/pkg/__init__.py": "",
    "src/pkg/a.py": "import os\nimport json\nfrom pkg import b\nimport requests\n",
    "src/pkg/b.py": "from __future__ import annotations\nimport sys\n",
}


def python_project(root: Path) -> Path:
    for name, text in FILES.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    parts = (
        {**component("base", "b"), "packages": ["pkg.b"]},
        {**component("app", "a", ("base",)), "packages": ["pkg.a"]},
    )
    contract = {"schema_version": "2.1.0", "components": list(parts), "rules": []}
    (root / "architecture-contract.json").write_text(json.dumps(contract))
    (root / "archkeel.toml").write_text(
        '[scan]\nlanguage = "python"\nroots = ["src/pkg"]\nnamespace = "pkg"\n'
        'contract = "architecture-contract.json"\n'
    )
    commit_tree(root)
    return root


def topology_of(release_core: Path, tmp_path: Path) -> dict[str, Any]:
    root = python_project(tmp_path / "project")
    done = command(release_core, root, "--json", "--topology", verb="report")
    assert "no listed module" not in done.stdout + done.stderr, done.stdout
    assert done.returncode in (0, 1, 2), done.stderr
    frame = json.loads(done.stdout)["frame"]
    assert isinstance(frame["topology"], dict), done.stdout
    return frame["topology"]  # type: ignore[no-any-return]


def test_a_python_import_of_the_platform_or_a_library_is_an_external_edge(
    release_core: Path, tmp_path: Path
) -> None:
    topology = topology_of(release_core, tmp_path)
    modules = {m["name"] for m in topology["modules"]}
    rows = {(e["source"], e["target"]): e["resolution"] for e in topology["edges"]}
    assert rows[("pkg.a", "os")] == "external"
    assert rows[("pkg.a", "json")] == "external"
    assert rows[("pkg.a", "requests")] == "external"
    assert rows[("pkg.b", "sys")] == "external"
    assert rows[("pkg.a", "pkg.b")] == "resolved"
    # Nothing is dropped: each edge that is resolved ends at a listed module.
    assert all(e["target"] in modules for e in topology["edges"] if e["resolution"] == "resolved")
    assert topology["total"]["edges"] == len(topology["edges"])


def test_the_component_edges_count_the_external_imports_under_their_own_label(
    release_core: Path, tmp_path: Path
) -> None:
    topology = topology_of(release_core, tmp_path)
    outside = [e for e in topology["component_edges"] if e["resolution"] == "external"]
    assert sum(e["count"] for e in outside) == 5
    assert {e["target"] for e in outside} == {"external"}

# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-594: the topology carries the declared structure, and each requirement names its use."""

import json
from pathlib import Path
from typing import Any

import pytest
from corpus_support import commit_tree
from rust_repository import GRAPH_PAGE, component, rule
from test_cli_core_only_scan import command

from archkeel.cli.core_frame import NAMES_A_GAP_EXIT, CoreError, read_frame

FILES = {
    "src/pkg/__init__.py": "",
    "src/pkg/a.py": "from pkg import b\nfrom pkg.b import value\n",
    "src/pkg/b.py": "value = 1\n",
    "src/pkg/c.py": "other = 2\n",
}


def declared_frame(release_core: Path, root: Path) -> dict[str, Any]:
    """A project where `app` uses its requirement and `spare` does not use its requirement.

    The run is UNKNOWN: the marked graph draws the requirement that no import uses."""
    for name, text in FILES.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    parts = (
        {**component("base", "b"), "packages": ["pkg.b"], "layer": "core", "public": ["pkg.b"]},
        {**component("app", "a", ("base",)), "packages": ["pkg.a"], "layer": "edge"},
        {**component("spare", "c", ("base",)), "packages": ["pkg.c"], "layer": "edge"},
    )
    rules = [rule("LAYERS", "layer_order", layers=["core", "edge"])]
    contract = {"schema_version": "2.3.0", "components": list(parts), "rules": rules}
    (root / "architecture-contract.json").write_text(json.dumps(contract))
    (root / "archkeel.toml").write_text(
        '[scan]\nlanguage = "python"\nroots = ["src/pkg"]\nnamespace = "pkg"\n'
        'contract = "architecture-contract.json"\n'
    )
    (root / "docs").mkdir()
    (root / "docs/target.md").write_text(
        GRAPH_PAGE.format(edges="    app --> base\n    spare --> base")
    )
    commit_tree(root)
    done = command(release_core, root, "--json", "--topology", verb="report")
    result = json.loads(done.stdout)
    assert "refusal" not in result, result
    return result["frame"]  # type: ignore[no-any-return]


def test_the_topology_states_the_declared_structure(release_core: Path, tmp_path: Path) -> None:
    frame = declared_frame(release_core, tmp_path / "project")
    topology = frame["topology"]
    assert [(c["id"], c["layer"], c["public"]) for c in topology["components"]] == [
        ("COMP-APP", "edge", []),
        ("COMP-BASE", "core", ["pkg.b"]),
        ("COMP-SPARE", "edge", []),
    ]
    # The count is the count of the observed component edge. Zero is a permission without a use.
    used = {
        (e["source"], e["target"]): e["count"]
        for e in topology["component_edges"]
        if e["resolution"] == "resolved"
    }
    rows = [(r["source"], r["target"], r["imports"], r["through"]) for r in topology["requires"]]
    assert rows == [
        ("COMP-APP", "COMP-BASE", used["COMP-APP", "COMP-BASE"], []),
        ("COMP-SPARE", "COMP-BASE", 0, []),
    ]
    # AD-606: each row carries the rationale that the contract states.
    assert all(r["rationale"] for r in topology["requires"])
    assert used["COMP-APP", "COMP-BASE"] > 0
    assert topology["layers"] == [{"rule": "LAYERS", "layers": ["core", "edge"]}]
    assert topology["total"]["requires"] == 2 and topology["budgets"]["requires"] == 20_000
    decoded = read_frame(json.dumps(frame).encode(), NAMES_A_GAP_EXIT, scan=True).topology
    assert decoded is not None and [r.imports for r in decoded.requires] == [
        used["COMP-APP", "COMP-BASE"],
        0,
    ]
    assert decoded.layers[0].layers == ("core", "edge")


@pytest.mark.parametrize("fault", ["component", "repeat", "rule", "count"])
def test_a_forged_declared_row_is_refused(release_core: Path, tmp_path: Path, fault: str) -> None:
    frame = declared_frame(release_core, tmp_path / "project")
    topology = frame["topology"]
    if fault == "component":
        topology["requires"][0]["target"] = "NOT-LISTED"
    elif fault == "repeat":
        topology["requires"][1] = dict(topology["requires"][0])
    elif fault == "rule":
        topology["layers"].append(dict(topology["layers"][0]))
        topology["total"]["layers"] += 1
    else:
        topology["total"]["requires"] += 1
    with pytest.raises(CoreError, match="topology"):
        read_frame(json.dumps(frame).encode(), NAMES_A_GAP_EXIT, scan=True)

# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The opt-in topology is a bounded read of the same run, not a second verdict."""

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from core_support import HONEST, case_root
from rust_repository import repository
from test_cli_core_inside_trees import tree
from test_cli_core_only_scan import command

from archkeel.cli.core_frame import CoreError, read_frame


def test_small_rust_topology(release_core: Path, tmp_path: Path) -> None:
    root = repository(tmp_path / "project", release_core)
    done = command(release_core, root, "--json", "--topology", verb="report")
    assert done.returncode == 0, done.stdout + done.stderr
    topology = json.loads(done.stdout)["frame"]["topology"]
    assert topology["version"] == 1 and topology["complete"]
    assert [(c["id"], c["name"], c["parent"]) for c in topology["components"]] == [
        ("COMP-APP", "app", None),
        ("COMP-BASE", "base", None),
    ]
    assert [(m["path"], m["component"]) for m in topology["modules"]] == [
        ("crates/app/Cargo.toml", "COMP-APP"),
        ("crates/app/src/lib.rs", "COMP-APP"),
        ("crates/base/Cargo.toml", "COMP-BASE"),
        ("crates/base/src/lib.rs", "COMP-BASE"),
    ]
    assert [(e["source"], e["target"], e["resolution"], e["count"]) for e in topology["edges"]] == [
        ("native.app", "native.base_crate", "resolved", 1),
        ("native.app.cargo_toml", "native.base_crate", "resolved", 1),
    ]
    assert [(e["source"], e["target"], e["count"]) for e in topology["component_edges"]] == [
        ("COMP-APP", "COMP-BASE", 2)
    ]


def test_small_typescript_topology_links_the_existing_fail(release_core: Path) -> None:
    with case_root(HONEST) as root:
        (root / "src/a/a.ts").write_text(
            'import type { T } from "../b/t";\nexport const a: T = 1;\n'
        )
        plain = command(release_core, root, "--json", verb="report")
        done = command(release_core, root, "--json", "--topology", verb="report")
        assert done.returncode == plain.returncode == 1, done.stdout
        frame = json.loads(done.stdout)["frame"]
        original = json.loads(plain.stdout)["frame"]
        topology = frame.pop("topology")
        assert json.dumps(frame) == json.dumps(original)
        assert without_section(done.stdout) == plain.stdout
        assert [(m["path"], m["component"]) for m in topology["modules"]] == [
            ("src/a/a.ts", "COMP-A"),
            ("src/b/t.ts", "COMP-B"),
        ]
        assert [
            (e["source"], e["target"], e["resolution"], e["count"], e["rules"])
            for e in topology["edges"]
        ] == [("app.src.a.a_x2e_ts", "app.src.b.t_x2e_ts", "resolved", 1, ["REQUIRES"])]
        assert topology["edges"][0]["evidence"] == [{"path": "src/a/a.ts", "line": 1}]
        assert "topology" not in original


def without_section(stdout: str) -> str:
    """The raw text of a frame without its `topology` member and the comma that joins it."""
    key = '"topology":'
    start = stdout.index(key)
    value = start + len(key)
    while stdout[value] == " ":
        value += 1
    _, end = json.JSONDecoder().raw_decode(stdout, value)
    if stdout[end] == ",":
        end += 1
        while stdout[end] == " ":
            end += 1
    elif stdout[start - 1] == ",":
        start -= 1
    return stdout[:start] + stdout[end:]


def import_b(root: Path) -> None:
    """Let `a` import `b`; the marked graph draws the edge, so no hygiene row names it (AD-466)."""
    (root / "src/a/a.ts").write_text('import type { T } from "../b/t";\nexport const a: T = 1;\n')
    readme = root / "README.md"
    readme.write_text(readme.read_text().replace("flowchart LR\n", "flowchart LR\n    a --> b\n"))


def topology_frame(binary: Path, root: Path) -> dict:
    done = command(binary, root, "--json", "--topology", verb="report")
    result = json.loads(done.stdout)
    assert "refusal" not in result, result
    return result["frame"]


def test_incomplete_scope_and_unresolved_edges_are_explicit(release_core: Path) -> None:
    with case_root(HONEST) as root:
        (root / "src/a/a.ts").write_text(
            'import { missing } from "./absent";\nexport const a = missing;\n'
        )
        frame = topology_frame(release_core, root)
        topology = frame["topology"]
        assert not topology["complete"] and frame["scope"] in topology["gaps"]
        assert [(e["source"], e["resolution"]) for e in topology["edges"]] == [
            ("app.src.a.a_x2e_ts", "unresolved")
        ]


def test_inside_components_keep_their_mount_parent(release_core: Path) -> None:
    with case_root(HONEST) as root:
        tree(root)
        frame = topology_frame(release_core, root)
        assert [(c["id"], c["parent"]) for c in frame["topology"]["components"]] == [
            ("COMP-A", None),
            ("COMP-B", None),
            ("a:INNER", "COMP-A"),
            ("a:inner:LEAF", "a:INNER"),
        ]
        assert frame["topology"]["modules"][0]["component"] == "a:inner:LEAF"


@pytest.mark.parametrize("kind", ["modules", "edges", "evidence_per_edge"])
def test_hard_budgets_name_the_exact_total(release_core: Path, kind: str) -> None:
    with case_root(HONEST) as root:
        contract = root / "architecture-contract.json"
        document = json.loads(contract.read_text())
        document["rules"] = [document["rules"][1]]
        contract.write_text(json.dumps(document))
        if kind == "modules":
            for index in range(10_000):
                (root / f"src/a/m{index}.ts").write_text("export const value = 1;\n")
            expected = 10_002
        elif kind == "edges":
            for source in range(143):
                imports = "".join(
                    f'import {{ v as v{target} }} from "./m{target}";\n'
                    for target in range(143)
                    if source != target
                )
                (root / f"src/a/m{source}.ts").write_text(imports + "export const v = 1;\n")
            expected = 143 * 142
        else:
            (root / "src/a/a.ts").write_text(
                'import type { T } from "../b/t";\n' * 6 + "export const a: T = 1;\n"
            )
            expected = 6
        frame = topology_frame(release_core, root)
        topology = frame["topology"]
        assert topology["truncated"] and not topology["complete"]
        assert topology["total"][kind] == expected
        if kind == "evidence_per_edge":
            assert len(topology["edges"][0]["evidence"]) == 5
            assert topology["edges"][0]["evidence_total"] == 6
        else:
            assert len(topology[kind]) == topology["budgets"][kind]


def test_topology_is_byte_stable_and_text_names_its_limits(release_core: Path) -> None:
    with case_root(HONEST) as root:
        first = topology_frame(release_core, root)["topology"]
        assert first == topology_frame(release_core, root)["topology"]
        text = command(release_core, root, "--text", "--topology", verb="report")
        assert "Topology: 2/2 modules, 0/0 edges; complete: True; truncated: False" in text.stdout
        refused = command(release_core, root, "--json", "--topology")
        assert refused.returncode == 2


@pytest.mark.parametrize(
    "fault", ["absent", "version", "extra", "complete", "count", "budget", "resolution", "rule"]
)
def test_a_requested_old_or_forged_topology_is_refused(release_core: Path, fault: str) -> None:
    with case_root(HONEST) as root:
        import_b(root)
        frame = topology_frame(release_core, root)
        topology = frame["topology"]
        if fault == "absent":
            frame.pop("topology")
            assert read_frame(json.dumps(frame).encode(), 0, scan=True).topology is None
            return
        elif fault == "version":
            topology["version"] = True
        elif fault == "extra":
            topology["pass"] = True
        elif fault == "complete":
            topology["complete"] = False
        elif fault == "count":
            topology["total"]["modules"] += 1
        elif fault == "budget":
            topology["budgets"]["modules"] += 1
        elif fault == "resolution":
            topology["edges"][0]["resolution"] = "guessed"
        else:
            topology["edges"][0]["rules"] = ["NOT-A-ROW"]
        with pytest.raises(CoreError, match="topology"):
            read_frame(json.dumps(frame).encode(), 0, scan=True)


def test_a_requested_but_absent_section_is_refused(release_core: Path) -> None:
    with case_root(HONEST) as root:
        frame = topology_frame(release_core, root)
        frame.pop("topology")
        with pytest.raises(CoreError, match="requested topology"):
            read_frame(json.dumps(frame).encode(), 0, scan=True, request={"topology": True})


def planned_owner(root: Path, document: dict) -> None:
    document["schema_version"] = "2.4.0"
    document["components"].append(
        {
            "id": "COMP-P",
            "label": "p",
            "role": "component",
            "lifecycle": "planned",
            "packages": [],
            "planned": ["app.src.p"],
            "responsibilities": ["Plan p."],
            "forbidden_responsibilities": [],
            "provenance": ["README.md"],
            "requires": [],
            "decided_by": "architect",
        }
    )


def two_claimants(root: Path, document: dict) -> None:
    second = json.loads(json.dumps(document["components"][0]))
    second.update(id="COMP-A2", label="a2")
    document["components"].append(second)


def node_import(root: Path, document: dict) -> None:
    (root / "src/a/a.ts").write_text(
        'import { readFileSync } from "node:fs";\nexport const a = readFileSync;\n'
    )


def topology_after(binary: Path, change: Callable[[Path, dict], None]) -> dict:
    with case_root(HONEST) as root:
        contract = root / "architecture-contract.json"
        document = json.loads(contract.read_text())
        change(root, document)
        contract.write_text(json.dumps(document))
        return topology_frame(binary, root)


def test_a_planned_owner_is_listed_as_planned_and_owns_no_module(release_core: Path) -> None:
    frame = topology_after(release_core, planned_owner)
    topology = frame["topology"]
    assert [(c["id"], c["planned"]) for c in topology["components"]] == [
        ("COMP-A", False),
        ("COMP-B", False),
        ("COMP-P", True),
    ]
    assert {m["component"] for m in topology["modules"]} == {"COMP-A", "COMP-B"}
    # The run is UNKNOWN, and the section still says complete: it covers scope and budgets only.
    assert frame["status"] == "UNKNOWN" and topology["complete"] and not topology["gaps"]


def test_a_module_with_two_claimants_is_ambiguous(release_core: Path) -> None:
    topology = topology_after(release_core, two_claimants)["topology"]
    assert [(m["ownership"], m["component"]) for m in topology["modules"]] == [
        ("ambiguous", None),
        ("owned", "COMP-B"),
    ]


def test_an_external_import_is_an_external_edge_with_a_pseudo_component_target(
    release_core: Path,
) -> None:
    topology = topology_after(release_core, node_import)["topology"]
    assert [(e["target"], e["resolution"]) for e in topology["edges"]] == [("node:fs", "external")]
    assert [(e["source"], e["target"], e["resolution"]) for e in topology["component_edges"]] == [
        ("COMP-A", "external", "external")
    ]


def test_module_names_are_unique_in_a_real_frame_and_a_repeat_is_refused(
    release_core: Path,
) -> None:
    with case_root(HONEST) as root:
        tree(root)
        frame = topology_frame(release_core, root)
    names = [m["name"] for m in frame["topology"]["modules"]]
    assert len(names) == len(set(names)) > 1
    frame["topology"]["modules"].append(dict(frame["topology"]["modules"][0]))
    frame["topology"]["total"]["modules"] += 1
    with pytest.raises(CoreError, match="repeated"):
        read_frame(json.dumps(frame).encode(), 0, scan=True)


@pytest.mark.parametrize("level", ["edges", "component_edges"])
@pytest.mark.parametrize("end", ["source", "target"])
def test_an_edge_that_names_no_listed_row_is_refused(
    release_core: Path, level: str, end: str
) -> None:
    with case_root(HONEST) as root:
        import_b(root)
        frame = topology_frame(release_core, root)
    frame["topology"][level][0][end] = "NOT-LISTED"
    with pytest.raises(CoreError, match="names no listed"):
        read_frame(json.dumps(frame).encode(), 0, scan=True)


def test_an_edge_may_name_a_row_beyond_a_truncated_list(release_core: Path) -> None:
    with case_root(HONEST) as root:
        import_b(root)
        frame = topology_frame(release_core, root)
    topology = frame["topology"]
    limit = topology["budgets"]["modules"]
    template = topology["modules"][0]
    topology["modules"] = [
        {
            **template,
            "name": f"m{index}",
            "path": f"p{index}",
            "component": None,
            "ownership": "unowned",
        }
        for index in range(limit)
    ]
    topology["total"]["modules"] = limit + 1
    topology["truncated"], topology["complete"] = True, False
    topology["gaps"] = [] if frame["scope"] == "complete" else [frame["scope"]]
    topology["edges"][0]["source"] = "cut-away-module"
    assert read_frame(json.dumps(frame).encode(), 0, scan=True).topology is not None
    topology["total"]["modules"] = limit
    topology["truncated"] = False
    topology["complete"] = not topology["gaps"]
    with pytest.raises(CoreError, match="names no listed"):
        read_frame(json.dumps(frame).encode(), 0, scan=True)

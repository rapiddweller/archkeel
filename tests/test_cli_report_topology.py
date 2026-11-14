# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The opt-in topology is a bounded read of the same run, not a second verdict."""

import json
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
        (root / "src/a/a.ts").write_text(
            'import type { T } from "../b/t";\nexport const a: T = 1;\n'
        )
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

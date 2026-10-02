# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Target diagrams describe declared architecture, not the observed graph."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from test_architecture_demo import CONFIG, _prepare_repo

from archkeel.analyzer import observe
from archkeel.check.report import run_report
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.model import EvidenceClass, Record, RecordData
from archkeel.render.html import _target_diagrams, _target_roots, render_html
from fixtures.architecture_demo import CATALOG
from fixtures.demo_catalog_support import FIXTURE_DIR


def _walk(nodes: list[dict[str, Any]]):
    for node in nodes:
        yield node
        yield from _walk(node["children"])


def _open_target_node(page: Any, selector: str) -> None:
    page.locator(selector).click()
    open_selected = page.locator(".flow-open-selected")
    if open_selected.is_enabled():
        open_selected.click()


def _open_projection_entry(page: Any, selector: str) -> None:
    page.locator(selector).click()
    open_selected = page.locator(".flow-open-selected")
    if open_selected.is_enabled():
        open_selected.click()


def _component_route(nodes: list[dict[str, Any]], target_id: str, route=()):
    for node in nodes:
        current = (*route, node["id"]) if node["kind"] == "component" else route
        if node["id"] == target_id:
            return route
        found = _component_route(node["children"], target_id, current)
        if found is not None:
            return found
    return None


def _declaration_record(
    identifier: str,
    kind: str,
    title: str,
    *,
    subjects: tuple[str, ...] = (),
    data: dict[str, Any] | None = None,
    provenance: tuple[str, ...] = ("architecture-contract.json",),
) -> Record:
    return Record(
        id=identifier,
        evidence_class=EvidenceClass.DECLARED_RULE,
        area="components",
        kind=kind,
        title=title,
        subjects=subjects,
        evidence_ids=(),
        rule_ids=(),
        fact_ids=(),
        provenance=provenance,
        data=RecordData(
            tuple(
                (
                    key,
                    tuple(
                        RecordData(tuple(entry.items())) if isinstance(entry, dict) else entry
                        for entry in value
                    )
                    if key == "requires" and isinstance(value, tuple)
                    else value,
                )
                for key, value in (data or {}).items()
            )
        ),
    )


def _declared_diagrams(components: list[Record], layouts: list[Record]) -> dict[str, Any]:
    roots, _, _, _ = _target_roots((*components, *layouts))
    return _target_diagrams(roots)


def test_target_physical_frames_preserve_semantic_owners() -> None:
    components = [
        _declaration_record(
            "COMP-RUNTIME",
            "component_responsibility",
            "runtime",
            subjects=("repo.engine.runtime",),
            data={
                "namespace": "repo.engine.runtime",
                "requires": ({"component": "domains", "rationale": "Runtime uses domains."},),
            },
        ),
        _declaration_record(
            "COMP-DOMAINS",
            "component_responsibility",
            "domains",
            subjects=("repo.domains",),
            data={
                "namespace": "repo.domains",
                "requires": ({"component": "io", "rationale": "Domains use IO."},),
            },
        ),
        _declaration_record(
            "COMP-IO",
            "component_responsibility",
            "io",
            subjects=("repo.engine.io",),
            data={"namespace": "repo.engine.io", "requires": ()},
        ),
    ]
    layouts = [
        _declaration_record(
            "LAYOUT-ROOT",
            "root_layout",
            "repo",
            data={"root": "repo", "allowed_children": ("repo.engine", "repo.domains")},
        ),
        _declaration_record(
            "LAYOUT-ENGINE",
            "root_layout",
            "repo.engine",
            data={
                "root": "repo.engine",
                "allowed_children": ("repo.engine.io", "repo.engine.runtime"),
            },
        ),
    ]

    diagrams = _declared_diagrams(components, layouts)
    graph = diagrams["root"]
    containers = graph["containers"]
    ranks = {
        node["id"]: node["dependency_rank"]
        for node in graph["nodes"]
        if node["kind"] == "component"
    }
    component_ids = {node["id"] for node in graph["nodes"] if node["kind"] == "component"}

    assert containers["layout:LAYOUT-ENGINE"]["members"] == ["COMP-IO", "COMP-RUNTIME"]
    assert ranks["COMP-RUNTIME"] < ranks["COMP-DOMAINS"] < ranks["COMP-IO"]
    assert component_ids == {"COMP-RUNTIME", "COMP-DOMAINS", "COMP-IO"}
    assert len(component_ids) == sum(node["kind"] == "component" for node in graph["nodes"])


def test_target_diagram_projects_declared_placement_and_keeps_inventory_reachable() -> None:
    components = [
        _declaration_record(
            "COMP-EXPLICIT",
            "component_responsibility",
            "explicit",
            subjects=("app.engine.explicit",),
            data={"namespace": "app.engine.explicit"},
        ),
        _declaration_record(
            "COMP-INFERRED",
            "component_responsibility",
            "inferred",
            subjects=("app.engine.inferred",),
        ),
        _declaration_record(
            "COMP-SAME-FRAME",
            "component_responsibility",
            "same frame",
            subjects=("app.engine.same", "app.engine.same.api"),
        ),
        _declaration_record(
            "COMP-DISTINCT-FRAMES",
            "component_responsibility",
            "distinct frames",
            subjects=("app.engine.explicit", "app.other"),
        ),
        _declaration_record(
            "COMP-AMBIGUOUS",
            "component_responsibility",
            "ambiguous",
            subjects=("app.engine.shared",),
        ),
        _declaration_record(
            "COMP-UNSUPPORTED",
            "component_responsibility",
            "unsupported",
            subjects=("app.engine.*",),
        ),
    ]
    layouts = [
        _declaration_record(
            "LAYOUT-ROOT",
            "root_layout",
            "app",
            data={"root": "app", "allowed_children": ("app.engine", "app.other")},
        ),
        _declaration_record(
            "LAYOUT-ENGINE",
            "root_layout",
            "app.engine",
            data={
                "root": "app.engine",
                "allowed_children": ("app.engine.shared", "app.engine.*"),
            },
        ),
        _declaration_record(
            "LAYOUT-ENGINE-ALIAS",
            "root_layout",
            "app.engine.shared",
            data={"root": "app.engine.shared", "allowed_children": ()},
        ),
        _declaration_record(
            "LAYOUT-ENGINE-ALIAS-2",
            "root_layout",
            "app.engine.shared",
            data={"root": "app.engine.shared", "allowed_children": ()},
        ),
        _declaration_record(
            "LAYOUT-OTHER",
            "root_layout",
            "app.other",
            data={"root": "app.other", "allowed_children": ()},
        ),
    ]

    diagrams = _declared_diagrams(components, layouts)
    graph = diagrams["root"]
    placements = {
        node["id"]: node["placement"] for node in graph["nodes"] if node["kind"] == "component"
    }

    assert placements["COMP-EXPLICIT"] == {
        "status": "declared",
        "scopes": ["app.engine.explicit"],
        "container": "layout:LAYOUT-ENGINE",
    }
    assert placements["COMP-INFERRED"] == {
        "status": "inferred",
        "scopes": ["app.engine.inferred"],
        "container": "layout:LAYOUT-ENGINE",
    }
    assert placements["COMP-SAME-FRAME"] == {
        "status": "multiple",
        "scopes": ["app.engine.same", "app.engine.same.api"],
        "container": "layout:LAYOUT-ENGINE",
    }
    assert placements["COMP-DISTINCT-FRAMES"]["status"] == "multiple"
    assert placements["COMP-DISTINCT-FRAMES"]["container"] is None
    assert placements["COMP-AMBIGUOUS"]["status"] == "ambiguous"
    assert placements["COMP-AMBIGUOUS"]["container"] is None
    assert placements["COMP-UNSUPPORTED"]["status"] == "unmapped"
    assert placements["COMP-UNSUPPORTED"]["container"] is None

    all_ids = {
        node["id"] for diagram in [graph, *diagrams["nested"].values()] for node in diagram["nodes"]
    }
    assert {"layout:LAYOUT-ROOT", "layout:LAYOUT-ENGINE", "layout:LAYOUT-OTHER"} <= all_ids
    assert "physical:app.engine.*" in all_ids
    assert {node["id"] for node in graph["nodes"] if node["kind"] == "component"} == {
        component.id for component in components
    }


def test_target_dependency_ranks_leave_cycles_and_dependents_unranked() -> None:
    components = [
        _declaration_record("A", "component_responsibility", "A", data={"requires": ()}),
        _declaration_record(
            "DISCONNECTED", "component_responsibility", "disconnected", data={"requires": ()}
        ),
        _declaration_record(
            "B", "component_responsibility", "B", data={"requires": ({"component": "A"},)}
        ),
        _declaration_record(
            "SELF",
            "component_responsibility",
            "self",
            data={"requires": ({"component": "self"},)},
        ),
        _declaration_record(
            "CYCLE-A",
            "component_responsibility",
            "cycle a",
            data={"requires": ({"component": "cycle b"},)},
        ),
        _declaration_record(
            "CYCLE-B",
            "component_responsibility",
            "cycle b",
            data={"requires": ({"component": "cycle a"},)},
        ),
        _declaration_record(
            "DEPENDENT",
            "component_responsibility",
            "dependent",
            data={"requires": ({"component": "cycle a"},)},
        ),
    ]

    graph = _declared_diagrams(components, [])["root"]
    ranks = {node["id"]: node["dependency_rank"] for node in graph["nodes"]}

    assert ranks["B"] < ranks["A"]
    assert isinstance(ranks["DISCONNECTED"], int)
    assert ranks["SELF"] is None
    assert ranks["CYCLE-A"] is None
    assert ranks["CYCLE-B"] is None
    assert ranks["DEPENDENT"] is None


def test_target_diagrams_are_deterministic_and_preserve_declared_interfaces() -> None:
    components = [
        _declaration_record(
            "COMP-DECLARED",
            "component_responsibility",
            "declared",
            subjects=("app.declared",),
            data={
                "namespace": "app.declared",
                "public": ("app.declared.api",),
                "requires": (
                    {
                        "component": "provider",
                        "through": ("provider.api",),
                        "rationale": "Use the provider API.",
                        "decided_by": "architect",
                    },
                ),
            },
            provenance=("docs/architecture/declared.md",),
        ),
        _declaration_record(
            "COMP-EMPTY",
            "component_responsibility",
            "empty",
            data={
                "public": (),
                "requires": ({"component": "provider", "through": (), "rationale": "Empty path."},),
            },
        ),
        _declaration_record(
            "COMP-NULL",
            "component_responsibility",
            "null",
            data={
                "public": None,
                "requires": (
                    {"component": "provider", "through": None, "rationale": "Null path."},
                ),
            },
        ),
        _declaration_record(
            "COMP-ABSENT",
            "component_responsibility",
            "absent",
            data={"requires": ({"component": "provider", "rationale": "Default path."},)},
        ),
    ]

    first = _declared_diagrams(components, [])
    reordered = _declared_diagrams(
        [
            _declaration_record(
                record.id,
                record.kind,
                record.title,
                subjects=record.subjects,
                data=dict(reversed(record.data.entries)),
                provenance=record.provenance,
            )
            for record in reversed(components)
        ],
        [],
    )
    assert first == reordered

    root_nodes = {node["id"]: node for node in first["root"]["nodes"]}
    declared_details = {
        detail["label"]: detail["value"] for detail in root_nodes["COMP-DECLARED"]["details"]
    }
    assert declared_details["Packages"] == "app.declared"
    assert declared_details["Public interface"] == "app.declared.api"
    requirement = next(
        edge["details"] for edge in first["root"]["edges"] if edge["source"] == "COMP-DECLARED"
    )
    assert {detail["label"]: detail["value"] for detail in requirement} == {
        "Rationale": "Use the provider API.",
        "Through": "provider.api",
        "Provenance": "docs/architecture/declared.md",
        "Decided by": "architect",
    }
    requirement_details = {
        edge["source"]: {detail["label"]: detail["value"] for detail in edge["details"]}
        for edge in first["root"]["edges"]
    }
    for identifier, rationale in (
        ("COMP-EMPTY", "Empty path."),
        ("COMP-NULL", "Null path."),
        ("COMP-ABSENT", "Default path."),
    ):
        assert requirement_details[identifier] == {
            "Rationale": rationale,
            "Through": "Entire public interface",
            "Provenance": "architecture-contract.json",
        }
    empty_details = {
        detail["label"]: detail["value"] for detail in root_nodes["COMP-EMPTY"]["details"]
    }
    assert empty_details["Public interface"] == "Explicitly empty"
    null_details = {
        detail["label"]: detail["value"] for detail in root_nodes["COMP-NULL"]["details"]
    }
    absent_details = {
        detail["label"]: detail["value"] for detail in root_nodes["COMP-ABSENT"]["details"]
    }
    assert null_details["Public interface"] == "Not declared"
    assert absent_details["Public interface"] == "Not declared"


def test_target_graph_containers_are_local_and_single_component_frames_fold() -> None:
    components = [
        _declaration_record(
            "ROOT",
            "component_responsibility",
            "root",
            subjects=("app.engine.child",),
            data={"namespace": "app.engine.child"},
        ),
    ]
    layouts = [
        _declaration_record(
            "LAYOUT-ROOT",
            "root_layout",
            "app",
            data={"root": "app", "allowed_children": ("app.engine.child",)},
        ),
        _declaration_record(
            "LAYOUT-CHILD",
            "root_layout",
            "app.engine.child",
            data={"root": "app.engine.child", "allowed_children": ()},
        ),
    ]

    diagrams = _declared_diagrams(components, layouts)
    root_graph = diagrams["root"]
    child_graph = diagrams["nested"]["ROOT"]

    for graph in (root_graph, child_graph):
        nodes = {node["id"] for node in graph["nodes"]}
        containers = graph["containers"]
        assert all(
            member in nodes for container in containers.values() for member in container["members"]
        )
        assert all(
            container["parent"] is None or container["parent"] in containers
            for container in containers.values()
        )
        for node in graph["nodes"]:
            if node["kind"] != "component":
                continue
            container = node["placement"]["container"]
            assert container is None or node["id"] in containers[container]["members"]
            assert all(
                node["id"] not in item["members"]
                for key, item in containers.items()
                if key != container
            )
    assert root_graph["containers"]["layout:LAYOUT-ROOT"]["members"] == ["ROOT"]
    assert child_graph["containers"]["layout:LAYOUT-ROOT"]["members"] == ["ROOT"]
    assert "layout:LAYOUT-CHILD" in {
        node["id"] for node in _walk(_target_roots((*components, *layouts))[0])
    }
    root = next(node for node in root_graph["nodes"] if node["id"] == "ROOT")
    assert root["placement"]["container"] == "layout:LAYOUT-ROOT"
    assert root["placement"]["folded"] == [
        {
            "id": "layout:LAYOUT-CHILD",
            "scope": "app.engine.child",
            "details": [{"label": "Allowed children", "value": ""}],
        }
    ]


def test_parent_graph_folds_frame_for_visible_owner_not_hidden_inside_components() -> None:
    components = [
        _declaration_record(
            "OWNER",
            "component_responsibility",
            "Owner",
            subjects=("app.engine.runtime",),
            data={"namespace": "app.engine.runtime"},
        ),
        *(
            _declaration_record(
                f"INSIDE-{name.upper()}",
                "inside_component_responsibility",
                name,
                subjects=(f"app.engine.runtime.{name.lower()}",),
                data={
                    "namespace": f"app.engine.runtime.{name.lower()}",
                    "parent_id": "Owner",
                },
            )
            for name in ("DSL", "IO", "Workers")
        ),
    ]
    layouts = [
        _declaration_record(
            "LAYOUT-ROOT",
            "root_layout",
            "app",
            data={"root": "app", "allowed_children": ("app.engine",)},
        ),
        _declaration_record(
            "LAYOUT-ENGINE",
            "root_layout",
            "app.engine",
            data={"root": "app.engine", "allowed_children": ("app.engine.runtime",)},
        ),
        _declaration_record(
            "LAYOUT-RUNTIME",
            "root_layout",
            "app.engine.runtime",
            data={"root": "app.engine.runtime", "allowed_children": ()},
        ),
    ]

    diagrams = _declared_diagrams(components, layouts)
    root = diagrams["root"]
    owner_graph = diagrams["nested"]["OWNER"]
    root_layout_graph = diagrams["nested"]["layout:LAYOUT-ROOT"]
    root_owner = next(node for node in root["nodes"] if node["id"] == "OWNER")
    owner = next(node for node in owner_graph["nodes"] if node["id"] == "OWNER")

    assert "layout:LAYOUT-RUNTIME" not in root["containers"]
    assert root_owner["placement"]["container"] == "layout:LAYOUT-ENGINE"
    assert root["containers"]["layout:LAYOUT-ENGINE"]["members"] == ["OWNER"]
    assert owner["placement"]["container"] == "layout:LAYOUT-RUNTIME"
    assert owner_graph["containers"]["layout:LAYOUT-RUNTIME"]["members"] == [
        "INSIDE-DSL",
        "INSIDE-IO",
        "INSIDE-WORKERS",
        "OWNER",
    ]
    assert root_layout_graph["containers"]["layout:LAYOUT-ROOT"]["members"] == []


def _replace_flow_payload(page_html: str, payload: dict[str, Any]) -> str:
    script_start = page_html.index('id="flow-data"')
    payload_start = page_html.index(">", script_start) + 1
    payload_end = page_html.index("</script>", payload_start)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).replace("<", "\\u003c")
    return page_html[:payload_start] + encoded + page_html[payload_end:]


def _target_diagram_page(
    tmp_path: Path,
    *,
    include_module_target: bool = False,
    cycle: bool = False,
    cross_frame_chain: bool = False,
) -> tuple[str, dict[str, Any]]:
    tour = next(item for item in CATALOG if item.id == "tour")
    contract = json.loads((FIXTURE_DIR / "architecture-contract.json").read_text())
    contract["components"].append(
        {
            "id": "COMP-ARCHIVE",
            "label": "archive",
            "role": "component",
            "packages": ["shop.archive"],
            "responsibilities": ["Retain archived orders.", "Keep archive access explicit."],
            "forbidden_responsibilities": [],
            "provenance": ["docs/architecture/shop.md"],
            "decided_by": "architect",
        }
    )
    contract["components"].append(
        {
            "id": "COMP-EMPTY",
            "label": "empty",
            "role": "component",
            "packages": ["shop.empty"],
            "responsibilities": [],
            "forbidden_responsibilities": [],
            "provenance": ["docs/architecture/shop.md"],
            "decided_by": "architect",
        }
    )
    nested_contract = json.loads(
        (FIXTURE_DIR / "shop/store/architecture-contract.json").read_text()
    )
    nested_contract["components"].append(
        {
            "id": "COMP-STORE-EMPTY",
            "label": "empty nested",
            "role": "component",
            "packages": ["shop.store.empty"],
            "responsibilities": [],
            "forbidden_responsibilities": [],
            "provenance": ["docs/architecture/shop.md"],
            "decided_by": "architect",
        }
    )
    app = next(component for component in contract["components"] if component["id"] == "COMP-APP")
    app["requires"] = [
        {
            "component": "archive",
            "rationale": "Archived orders stay behind the declared archive boundary.",
        }
    ]
    root_layout = next(rule for rule in contract["rules"] if rule["kind"] == "root_layout")
    if cross_frame_chain:
        contract["components"].extend(
            [
                {
                    "id": "COMP-RUNTIME",
                    "label": "runtime",
                    "role": "component",
                    "packages": ["shop.engine.runtime"],
                    "namespace": "shop.engine.runtime",
                    "responsibilities": ["Execute runtime work."],
                    "forbidden_responsibilities": [],
                    "provenance": ["docs/architecture/shop.md"],
                    "decided_by": "architect",
                    "requires": [{"component": "domains", "rationale": "Runtime uses domains."}],
                },
                {
                    "id": "COMP-A-DOMAINS",
                    "label": "domains",
                    "role": "component",
                    "packages": ["shop.domains"],
                    "namespace": "shop.domains",
                    "responsibilities": ["Own domain values."],
                    "forbidden_responsibilities": [],
                    "provenance": ["docs/architecture/shop.md"],
                    "decided_by": "architect",
                    "requires": [{"component": "io", "rationale": "Domains use IO."}],
                },
                {
                    "id": "COMP-IO",
                    "label": "io",
                    "role": "component",
                    "packages": ["shop.engine.io"],
                    "namespace": "shop.engine.io",
                    "responsibilities": ["Perform IO."],
                    "forbidden_responsibilities": [],
                    "provenance": ["docs/architecture/shop.md"],
                    "decided_by": "architect",
                },
            ]
        )
        root_layout["allowed_children"].extend(["shop.engine", "shop.domains"])
        contract["rules"].append(
            {
                "id": "ENGINE-LAYOUT",
                "kind": "root_layout",
                "root": "shop.engine",
                "allowed_children": ["shop.engine.io", "shop.engine.runtime"],
                "rationale": "Runtime and IO share the physical engine frame.",
                "provenance": ["docs/architecture/shop.md"],
                "decided_by": "architect",
            }
        )
    if cycle:
        archive = next(
            component for component in contract["components"] if component["id"] == "COMP-ARCHIVE"
        )
        archive["requires"] = [
            {
                "component": "app",
                "rationale": "The browser fixture keeps a deliberate dependency cycle visible.",
            }
        ]
    if include_module_target:
        contract.setdefault("declarations", {}).setdefault("modules", []).append(
            {
                "path": "shop/app/orders.py",
                "responsibility": "Coordinate order workflows.",
            }
        )
    root_layout["allowed_children"].append("shop.archive")
    root_layout["allowed_children"].append("shop.missing")
    files = {
        **dict(tour.files),
        "architecture-contract.json": json.dumps(contract),
        "shop/store/architecture-contract.json": json.dumps(nested_contract),
        "shop/orphan.py": "VALUE = 1\n",
    }
    root = _prepare_repo(tmp_path, files)
    result, architecture = run_report(root, config=CONFIG, analyzer=observe)
    assert architecture is not None
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))
    page = render_html(
        result, observation, repository="shop", architecture_href="architecture.json"
    ).decode()
    start = page.index('id="flow-data"')
    payload = json.loads(page[page.index(">", start) + 1 : page.index("</script>", start)])
    return page, payload


def test_target_diagram_shows_declared_root_and_nested_graphs_only(tmp_path: Path) -> None:
    _, payload = _target_diagram_page(tmp_path)
    explorers = payload["explorers"]
    target_nodes = list(_walk(explorers["target"]))
    target_ids = {node["id"] for node in target_nodes}
    empty = next(node for node in target_nodes if node["id"] == "COMP-EMPTY")
    missing = next(detail for detail in empty["details"] if detail["label"] == "Responsibility")
    assert missing == {"label": "Responsibility", "value": "", "missing": True}
    responsibility_details = [
        detail
        for node in target_nodes
        for detail in node["details"]
        if detail["label"] == "Responsibility"
    ]
    assert sum(detail.get("missing") is not True for detail in responsibility_details) == 11
    assert sum(detail.get("missing") is True for detail in responsibility_details) == 2
    archive = next(node for node in target_nodes if node["id"] == "COMP-ARCHIVE")
    assert {
        detail["value"] for detail in archive["details"] if detail["label"] == "Responsibility"
    } == {"Retain archived orders.", "Keep archive access explicit."}
    require_ids = {node["id"] for node in target_nodes if node["kind"] == "requires"}
    assert len(require_ids) == sum(node["kind"] == "requires" for node in target_nodes)

    diagrams = explorers["target_diagrams"]
    root = diagrams["root"]
    root_nodes = {node["id"]: node for node in root["nodes"]}
    assert "COMP-ARCHIVE" in root_nodes
    assert root_nodes["COMP-ARCHIVE"]["kind"] == "component"
    assert root_nodes["COMP-EMPTY"]["details"] == empty["details"]
    assert "physical:shop.archive" not in root_nodes
    archive_requirement = next(
        edge for edge in root["edges"] if edge.get("declaration") == "requires:COMP-APP:archive"
    )
    assert (archive_requirement["source"], archive_requirement["target"]) == (
        "COMP-APP",
        "COMP-ARCHIVE",
    )

    layout = diagrams["nested"]["layout:ROOT-LAYOUT"]
    layout_nodes = {node["id"]: node for node in layout["nodes"]}
    assert layout_nodes["physical:shop.archive"]["kind"] == "physical_child"
    assert layout_nodes["physical:shop.missing"]["kind"] == "physical_child"
    assert any(
        edge["source"] == "layout:ROOT-LAYOUT" and edge["target"] == "physical:shop.archive"
        for edge in layout["edges"]
    )
    assert set(layout_nodes) <= target_ids

    nested = diagrams["nested"]["COMP-STORE"]
    nested_labels = {node["label"] for node in nested["nodes"]}
    assert {"api", "backend", "codec", "repository"} <= nested_labels
    assert any(edge["kind"] == "requires" for edge in nested["edges"])

    # Tree records are exhaustively reachable as nodes or declared requirement edges.
    reachable: set[str] = set()
    graph_node_ids: set[str] = set()
    edge_declarations: list[str] = []
    pending = [node["id"] for node in root["nodes"]]
    graphs = [root]
    while pending:
        owner = pending.pop()
        if owner in reachable:
            continue
        reachable.add(owner)
        graph = diagrams["nested"].get(owner)
        if graph is None:
            continue
        assert graph["owner"] == owner
        graphs.append(graph)
        pending.extend(node["id"] for node in graph["nodes"])
    for graph in graphs:
        graph_node_ids.update(node["id"] for node in graph["nodes"])
        edge_declarations.extend(
            edge["declaration"] for edge in graph["edges"] if "declaration" in edge
        )
    assert graph_node_ids | set(edge_declarations) == target_ids
    assert set(diagrams["nested"]) <= reachable
    represented_requires = (graph_node_ids | set(edge_declarations)) & require_ids
    assert represented_requires == require_ids
    assert set(edge_declarations) <= target_ids

    for graph in graphs:
        ids = {node["id"] for node in graph["nodes"]}
        assert all(edge["source"] in ids and edge["target"] in ids for edge in graph["edges"])
        assert all(edge.get("state") not in {"violation", "observed"} for edge in graph["edges"])
        assert all(
            node["kind"]
            in {"component", "package_scope", "physical_child", "requires", "root_layout"}
            for node in graph["nodes"]
        )
        assert all(
            edge["kind"] in {"allowed_child", "contains", "owns_package", "requires"}
            for edge in graph["edges"]
        )

    assert all(node["label"] != "shop.orphan" for node in root["nodes"])


def test_target_diagram_is_visible_and_drillable_without_filter_status(tmp_path: Path) -> None:
    page_html, _ = _target_diagram_page(tmp_path)
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            channel=os.environ.get("PLAYWRIGHT_CHANNEL"),
        )
        try:
            page = browser.new_page()
            page.set_content(page_html, wait_until="load")
            page.get_by_role("button", name="Target").click()
            page.locator("[data-flow-details-toggle]").click()
            assert page.locator(".flow-canvas").is_visible()
            assert page.locator(".flow-nodes .node").count() >= 6
            root_labels = {
                label
                for label in page.locator(".flow-nodes .node").evaluate_all(
                    "nodes => nodes.map(node => node.getAttribute('data-label'))"
                )
            }
            assert "archive" in root_labels
            assert page.locator(".flow-edges .edge").count() > 0
            assert page.locator(
                '.target-node[data-target-node="COMP-STORE"] .target-responsibility'
            ).all_text_contents() == ["Persist orders as JSON files."]
            assert (
                page.locator(".flow-filter-status").evaluate(
                    "element => getComputedStyle(element).visibility"
                )
                == "hidden"
            )
            requirement_edge = page.locator(".flow-edges .target-edge.requires").first
            hit_path = requirement_edge.locator(".target-hit")
            hit_path.scroll_into_view_if_needed()
            point = hit_path.evaluate(
                "path => {"
                " const length = path.getTotalLength();"
                " const matrix = path.getScreenCTM();"
                " if (!length || !matrix) return null;"
                " const edge = path.closest('[data-target-edge]');"
                " for (let ratio = 0.2; ratio <= 0.8; ratio += 0.05) {"
                "   const svgPoint = path.getPointAtLength(length * ratio);"
                "   const screen = new DOMPoint(svgPoint.x, svgPoint.y).matrixTransform(matrix);"
                "   const under = document.elementFromPoint(screen.x, screen.y);"
                "   if (under && edge.contains(under)) return {x: screen.x, y: screen.y};"
                " }"
                " return null;"
                "}"
            )
            assert point is not None, "Target requirement edge has no visible hit point in Chrome"
            assert hit_path.evaluate(
                "(path, point) => { const under = document.elementFromPoint(point.x, point.y);"
                " return Boolean(under && path.closest('[data-target-edge]').contains(under)); }",
                point,
            ), "Computed SVG point does not hit the Target requirement edge"
            page.mouse.click(point["x"], point["y"])
            assert (
                page.locator(".flow-inspector")
                .get_by_text("Archived orders stay behind the declared archive boundary.")
                .is_visible()
            )
            requirement_edge.focus()
            page.keyboard.press("Enter")
            assert requirement_edge.get_attribute("aria-pressed") == "true"

            _open_target_node(page, '.flow-nodes .node[data-target-node="layout:ROOT-LAYOUT"]')
            layout_labels = {
                label
                for label in page.locator(".flow-nodes .node").evaluate_all(
                    "nodes => nodes.map(node => node.getAttribute('data-label'))"
                )
            }
            assert {"shop.archive", "shop.missing"} <= layout_labels
            assert page.locator(".flow-edges .edge.allowed_child").count() > 0
            page.keyboard.press("Escape")
            assert page.locator(
                '.flow-nodes .node[data-target-node="layout:ROOT-LAYOUT"]'
            ).is_visible()

            page.locator('.flow-nodes .node[data-target-node="COMP-STORE"]').click()
            page.locator(".flow-open-selected").click()
            nested_labels = {
                label
                for label in page.locator(".flow-nodes .node").evaluate_all(
                    "nodes => nodes.map(node => node.getAttribute('data-label'))"
                )
            }
            assert {"api", "backend", "codec", "repository"} <= nested_labels
            page.locator(".flow-details-toggle").click()
            assert page.locator('[data-target-detail="package:COMP-STORE:shop.store"]').count() == 1
            assert page.locator(".flow-nodes .target-node.package").count() == 0
            page.locator(".flow-details-toggle").click()
            assert page.locator(".flow-breadcrumb").inner_text() == "Target\n/\nshop\n/\nstore"
            assert page.locator(".flow-edges .edge").count() > 0
            assert (
                page.locator(".flow-filter-status").evaluate(
                    "element => getComputedStyle(element).visibility"
                )
                == "hidden"
            )
            page.keyboard.press("Escape")
            assert page.locator(".flow-breadcrumb").inner_text() == "Target\n/\nshop"
            assert page.locator(".flow-inspector").is_hidden()
            page.keyboard.press("Escape")
            assert page.locator(".flow-breadcrumb").inner_text() == "Target"
            assert page.locator('.flow-nodes .node[data-target-node="COMP-STORE"]').is_visible()

            page.get_by_role("button", name="Diff").click()
            if page.locator("[data-flow-details-toggle]").get_attribute("aria-expanded") != "true":
                page.locator("[data-flow-details-toggle]").click()
            for category, entry in (
                ("diff:unmapped", "unmapped:shop.orphan"),
                ("diff:absent", "absent:ROOT-LAYOUT:shop.missing"),
            ):
                _open_projection_entry(page, f'[data-projection-id="{category}"]')
                page.locator(f'[data-projection-id="{entry}"]').click()
                assert page.locator('.flow-inspector [aria-label="Selected entry"]').is_visible()
                page.locator("[data-projection-root]").click()

            page.set_viewport_size({"width": 375, "height": 844})
            page.get_by_role("button", name="Actual").click()
            _open_projection_entry(page, '[data-projection-id="shop"]')
            assert page.locator('[data-projection-id="shop.orphan"]').is_visible()
            page.get_by_role("button", name="Diff").click()
            _open_projection_entry(page, '[data-projection-id="diff:unmapped"]')
            assert page.locator('[data-projection-id="unmapped:shop.orphan"]').is_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        finally:
            browser.close()


def test_target_physical_path_survives_actual_diff_round_trip(tmp_path: Path) -> None:
    page_html, payload = _target_diagram_page(tmp_path)
    diagrams = payload["explorers"]["target_diagrams"]
    target_path = [
        "layout:ROOT-LAYOUT",
        "COMP-STORE",
        "store:COMP-STORE-BACKEND",
    ]
    assert all(identifier in diagrams["nested"] for identifier in target_path)

    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_content(page_html, wait_until="load")
            page.locator('[data-flow-view="target"]').click()
            page.locator('[data-target-container="layout:ROOT-LAYOUT"]').click()
            page.locator(".flow-open-selected").click()
            _open_target_node(page, '[data-target-node="COMP-STORE"]')
            _open_target_node(page, '[data-target-node="store:COMP-STORE-BACKEND"]')
            page.locator(".flow-details-toggle").click()
            page.locator(
                '[data-target-detail="package:store:COMP-STORE-BACKEND:shop.store.backend"]'
            ).press("Enter")

            breadcrumb = page.locator(".flow-breadcrumb").inner_text()
            selection = page.locator('[data-target-detail][aria-pressed="true"]').evaluate_all(
                "nodes => nodes.map(node => node.dataset.targetDetail)"
            )
            assert breadcrumb == "Target\n/\nshop\n/\nstore\n/\nbackend"
            assert selection == ["package:store:COMP-STORE-BACKEND:shop.store.backend"]

            for view in ("actual", "diff", "target"):
                page.locator(f'[data-flow-view="{view}"]').click()

            assert page.locator(".flow-breadcrumb").inner_text() == breadcrumb
            assert (
                page.locator('[data-target-detail][aria-pressed="true"]').evaluate_all(
                    "nodes => nodes.map(node => node.dataset.targetDetail)"
                )
                == selection
            )
            assert page.locator(".flow-inspector h2").text_content() == "shop.store.backend"
        finally:
            browser.close()


def test_target_ranked_components_remain_distinct_in_physical_frames(
    tmp_path: Path,
) -> None:
    page_html, payload = _target_diagram_page(tmp_path, cross_frame_chain=True)
    graph = payload["explorers"]["target_diagrams"]["root"]
    components = {node["id"]: node for node in graph["nodes"] if node["kind"] == "component"}
    assert (
        components["COMP-RUNTIME"]["dependency_rank"]
        < components["COMP-A-DOMAINS"]["dependency_rank"]
    )
    assert (
        components["COMP-A-DOMAINS"]["dependency_rank"] < components["COMP-IO"]["dependency_rank"]
    )
    assert graph["containers"]["layout:ENGINE-LAYOUT"]["members"] == [
        "COMP-IO",
        "COMP-RUNTIME",
    ]

    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_content(page_html, wait_until="load")
            page.locator('[data-flow-view="target"]').click()
            y_positions = page.locator(
                '[data-target-node="COMP-RUNTIME"], [data-target-node="COMP-A-DOMAINS"], '
                '[data-target-node="COMP-IO"]'
            ).evaluate_all(
                "nodes => Object.fromEntries(nodes.map(node => [node.dataset.targetNode, "
                "Number(node.getAttribute('transform').match(/,([\\d.-]+)\\)/)[1])]))"
            )
            assert y_positions["COMP-RUNTIME"] == 0
            assert y_positions["COMP-IO"] >= 0
            assert y_positions["COMP-A-DOMAINS"] == 0
            x_positions = page.locator(
                '[data-target-node="COMP-RUNTIME"], [data-target-node="COMP-IO"]'
            ).evaluate_all(
                "nodes => nodes.map(node => Number(node.getAttribute('transform')"
                r".match(/translate\(([\d.-]+)/)[1]))"
            )
            assert len(set(x_positions)) == 2 or y_positions["COMP-IO"] > 0
        finally:
            browser.close()


def test_target_double_click_does_not_open_a_newly_drawn_frame(tmp_path: Path) -> None:
    page_html, _ = _target_diagram_page(tmp_path, cross_frame_chain=True)
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            observed = {}
            for activation in ("double-click", "single-click", "keyboard"):
                page.set_content(page_html, wait_until="load")
                page.locator('[data-flow-view="target"]').click()
                page.locator('[data-target-container="layout:ENGINE-LAYOUT"]').click()
                page.locator(".flow-open-selected").click()
                runtime = page.locator('[data-target-node="COMP-RUNTIME"]')
                if activation == "double-click":
                    box = runtime.bounding_box()
                    assert box is not None
                    page.mouse.click(
                        box["x"] + box["width"] / 2,
                        box["y"] + box["height"] / 2,
                        click_count=2,
                        delay=100,
                    )
                elif activation == "single-click":
                    runtime.click()
                else:
                    runtime.focus()
                    page.keyboard.press("Enter")

                observed[activation] = page.locator(".flow-breadcrumb").inner_text()
            assert observed == {
                "double-click": "Target\n/\nshop.engine\n/\nruntime",
                "single-click": "Target\n/\nshop.engine",
                "keyboard": "Target\n/\nshop.engine\n/\nruntime",
            }
        finally:
            browser.close()


def test_diagram_physical_frame_opens_on_native_header_double_click(tmp_path: Path) -> None:
    page_html, _ = _target_diagram_page(tmp_path, cross_frame_chain=True)
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_content(page_html, wait_until="load")
            frame = page.locator('[data-diagram-frame="layout:ROOT-LAYOUT"]')
            frame.dblclick(position={"x": 20, "y": 15})
            assert (
                "Physical package · navigation grouping: shop"
                in page.locator(".flow-breadcrumb").inner_text()
            )
            assert page.locator('[data-label="app"]').is_visible()
        finally:
            browser.close()


def test_actual_package_opens_its_observed_diagram_frame(tmp_path: Path) -> None:
    page_html, payload = _target_diagram_page(tmp_path, cross_frame_chain=True)
    root_frame = next(
        (identifier, frame)
        for identifier, frame in payload["explorers"]["target_diagrams"]["root"][
            "containers"
        ].items()
        if frame["scope"] == "shop"
    )
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_content(page_html, wait_until="load")
            page.locator('[data-flow-view="actual"]').click()
            _open_projection_entry(page, '[data-projection-id="shop"]')
            page.locator('[data-flow-view="diagram"]').click()
            assert (
                f"Physical package · navigation grouping: {root_frame[1]['scope']}"
                in page.locator(".flow-breadcrumb").text_content()
            )
            assert page.locator('[data-label="app"]').is_visible()
        finally:
            browser.close()


def test_target_single_click_selects_before_opening(tmp_path: Path) -> None:
    page_html, _ = _target_diagram_page(tmp_path)
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_content(page_html, wait_until="load")
            page.locator('[data-flow-view="target"]').click()
            page.locator('[data-target-node="COMP-STORE"]').click()

            assert page.locator(".flow-breadcrumb").inner_text() == "Target"
            assert (
                page.locator('[data-target-node="COMP-STORE"]').get_attribute("aria-pressed")
                == "true"
            )
            page.get_by_role("button", name="Open selected").click()
            assert page.locator(".flow-breadcrumb").inner_text() == "Target\n/\nstore"
        finally:
            browser.close()


@pytest.mark.parametrize("viewport", [(1920, 1080), (1024, 768), (375, 844)])
def test_explorer_viewport_geometry_is_shared(tmp_path: Path, viewport: tuple[int, int]) -> None:
    page_html, _ = _target_diagram_page(tmp_path)
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})
            page.set_content(page_html, wait_until="load")
            measurements = {}
            toggle = page.locator("[data-flow-details-toggle]")
            for details_open in (False, True):
                if (toggle.get_attribute("aria-expanded") == "true") != details_open:
                    page.evaluate("document.querySelector('[data-flow-details-toggle]').click()")
                for view in ("diagram", "actual", "target", "diff"):
                    page.evaluate(
                        "view => document.querySelector(`[data-flow-view=${view}]`).click()", view
                    )
                    viewport_selector = (
                        ".flow-alternative" if view in {"actual", "diff"} else ".flow-canvas"
                    )
                    measurements[(details_open, view)] = page.evaluate(
                        """selector => {
                          const box = element => {
                            const rect = element.getBoundingClientRect();
                            return [rect.x, rect.y, rect.width, rect.height];
                          };
                            const documentBox = selector => {
                              const rect = document.querySelector(selector).getBoundingClientRect();
                              return [rect.x + scrollX, rect.y + scrollY, rect.width, rect.height];
                            };
                            return {layout: documentBox('.flow-layout'),
                                viewport: documentBox(selector), scrollX, scrollY,
                                scrollWidth: document.documentElement.scrollWidth};
                        }""",
                        viewport_selector,
                    )
            for details_open in (False, True):
                baseline = measurements[(details_open, "diagram")]
                for view in ("actual", "target", "diff"):
                    current = measurements[(details_open, view)]
                    for part in ("layout", "viewport"):
                        assert all(
                            abs(left - right) <= 1
                            for left, right in zip(baseline[part], current[part], strict=True)
                        ), (details_open, view, part, baseline[part], current[part])
                    assert current["scrollWidth"] <= viewport[0]
                    assert (current["scrollX"], current["scrollY"]) == (
                        baseline["scrollX"],
                        baseline["scrollY"],
                    )
            assert page.locator(".flow-zoom-value").text_content() == "100%"
        finally:
            browser.close()


def test_fullscreen_fallback_restores_scope_focus_and_page_scroll(tmp_path: Path) -> None:
    page_html, _ = _target_diagram_page(tmp_path)
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1024, "height": 768})
            page.set_content(page_html, wait_until="load")
            page.evaluate(
                "Object.defineProperty(Element.prototype, 'requestFullscreen', "
                "{value: undefined, configurable: true});"
            )
            page.locator('[data-flow-view="target"]').click()
            _open_target_node(page, '[data-target-node="COMP-STORE"]')
            page.locator(".target-node[data-placement-status]").first.click()
            path_before = page.locator(".flow-breadcrumb").inner_text()
            selected_before = page.locator(".target-node.selected").get_attribute(
                "data-target-node"
            )
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            fullscreen = page.locator(".flow-fullscreen")
            assert page.evaluate("typeof Element.prototype.requestFullscreen") == "undefined"
            fullscreen.focus()
            scroll_before = page.evaluate("window.scrollY")
            fullscreen.click()
            assert page.locator("#flow").get_attribute("data-expanded") == "fallback"
            assert page.get_by_role("status").get_by_text("Expanded in this window").is_visible()
            assert page.locator("#flow").get_attribute("aria-modal") == "true"
            assert (
                page.locator("body").evaluate("element => getComputedStyle(element).overflow")
                == "hidden"
            )
            expanded_bounds = page.evaluate(
                """() => {
                  const box = selector => {
                    const rect = document.querySelector(selector).getBoundingClientRect();
                    return {top: rect.top, bottom: rect.bottom, height: rect.height};
                  };
                  return {
                    root: box('#flow'), layout: box('.flow-layout'),
                    canvas: box('.flow-canvas'), toolbar: box('.flow-toolbar'),
                    legend: box('.flow-legend'),
                    clientHeight: document.querySelector('#flow').clientHeight,
                    scrollHeight: document.querySelector('#flow').scrollHeight,
                  };
                }"""
            )
            assert expanded_bounds["scrollHeight"] <= expanded_bounds["clientHeight"] + 1, (
                expanded_bounds
            )
            for element in ("layout", "canvas", "toolbar", "legend"):
                assert expanded_bounds[element]["top"] >= expanded_bounds["root"]["top"]
                assert expanded_bounds[element]["bottom"] <= expanded_bounds["root"]["bottom"] + 1
            assert expanded_bounds["canvas"]["height"] >= 200
            page.keyboard.press("Escape")
            assert page.locator("#flow").get_attribute("data-expanded") is None
            assert page.locator("#flow").get_attribute("aria-modal") is None
            assert page.evaluate("window.scrollY") == scroll_before
            assert page.evaluate("document.activeElement.className") == "flow-fit flow-fullscreen"
            assert page.locator(".flow-breadcrumb").inner_text() == path_before
            assert (
                page.locator(".target-node.selected").get_attribute("data-target-node")
                == selected_before
            )
        finally:
            browser.close()


def test_fullscreen_request_rejection_uses_the_fallback(tmp_path: Path) -> None:
    page_html, _ = _target_diagram_page(tmp_path)
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1024, "height": 768})
            page.set_content(page_html, wait_until="load")
            page.evaluate(
                """() => {
                  window.fullscreenRequestCount = 0;
                  window.unhandledRejectionCount = 0;
                  window.addEventListener('unhandledrejection', () => {
                    window.unhandledRejectionCount += 1;
                  });
                  Object.defineProperty(document, 'fullscreenEnabled', {value: true});
                  Element.prototype.requestFullscreen = async function() {
                    window.fullscreenRequestCount += 1;
                    throw new DOMException('denied by embedding policy', 'NotAllowedError');
                  };
                }"""
            )
            page.locator(".flow-fullscreen").click()
            assert page.evaluate("window.fullscreenRequestCount") == 1
            assert page.locator("#flow").get_attribute("data-expanded") == "fallback"
            assert page.get_by_role("status").get_by_text("Expanded in this window").is_visible()
            assert page.evaluate("window.unhandledRejectionCount || 0") == 0
        finally:
            browser.close()


def test_target_inspector_explains_graph_local_placement(tmp_path: Path) -> None:
    page_html, payload = _target_diagram_page(tmp_path)
    placements = {
        "COMP-EMPTY": {
            "status": "ambiguous",
            "scopes": ["shop.empty.api"],
            "container": None,
        },
        "COMP-ARCHIVE": {
            "status": "multiple",
            "scopes": ["shop.archive", "shop.other"],
            "container": None,
        },
        "COMP-CLI": {
            "status": "unmapped",
            "scopes": ["shop.*"],
            "container": None,
        },
        "COMP-APP": {
            "status": "declared",
            "scopes": ["shop.app"],
            "container": "layout:ROOT-LAYOUT",
            "folded": [
                {
                    "id": "layout:APP-SOLO",
                    "scope": "shop.app",
                    "details": [{"label": "Allowed children", "value": "shop.app.orders"}],
                }
            ],
        },
    }
    diagrams = payload["explorers"]["target_diagrams"]
    for graph in [diagrams["root"], *diagrams["nested"].values()]:
        for node in graph["nodes"]:
            if node["id"] in placements:
                node["placement"] = placements[node["id"]]

    page_html = _replace_flow_payload(page_html, payload)

    cases = (
        (
            "COMP-EMPTY",
            "empty",
            "ambiguous",
            "shop.empty.api",
            "Multiple frame matches remain ambiguous in this view.",
        ),
        (
            "COMP-ARCHIVE",
            "archive",
            "multiple",
            "shop.archive, shop.other",
            "These scopes do not share one drawable frame in this view.",
        ),
        (
            "COMP-CLI",
            "cli",
            "unmapped",
            "shop.*",
            "No drawable frame resolves these scopes in this view.",
        ),
    )
    assert all(status not in label for _, label, status, _, _ in cases)

    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            for node_id, label, status, scopes, reason in cases:
                page.set_content(page_html, wait_until="load")
                page.locator('[data-flow-view="target"]').click()
                _open_target_node(page, f'[data-target-node="{node_id}"]')
                inspector = page.locator(".flow-inspector")
                assert inspector.locator("h2").text_content() == label
                content = inspector.inner_text()
                assert status in content
                assert scopes in content
                assert reason in content

            page.set_content(page_html, wait_until="load")
            page.locator('[data-flow-view="target"]').click()
            page.locator('[data-target-node="COMP-APP"]').click()
            page.locator(".flow-open-selected").click()
            content = page.locator(".flow-inspector").inner_text()
            assert "layout:ROOT-LAYOUT" in content
            assert "layout:APP-SOLO" in content
            assert "shop.app.orders" in content
        finally:
            browser.close()


def test_target_inspector_explains_folded_null_container(tmp_path: Path) -> None:
    page_html, payload = _target_diagram_page(tmp_path)
    diagrams = payload["explorers"]["target_diagrams"]
    placement = {
        "status": "declared",
        "scopes": ["shop.app"],
        "container": None,
        "folded": [
            {
                "id": "layout:APP-SOLO",
                "scope": "shop.app",
                "details": [{"label": "Allowed children", "value": "shop.app.orders"}],
            }
        ],
    }
    for graph in [diagrams["root"], *diagrams["nested"].values()]:
        for component in graph["nodes"]:
            if component["id"] == "COMP-APP":
                component["placement"] = placement
    page_html = _replace_flow_payload(page_html, payload)

    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_content(page_html, wait_until="load")
            page.locator('[data-flow-view="target"]').click()
            page.locator('[data-target-node="COMP-APP"]').click()
            page.locator(".flow-open-selected").click()
            content = page.locator(".flow-inspector").inner_text()
            assert "No drawable frame is associated in this view;" in content
            assert "matching frame was folded" in content
            assert "layout:APP-SOLO" in content
            assert "shop.app.orders" in content
            assert "No declared frame is associated" not in content
        finally:
            browser.close()


def test_target_cycle_warning_follows_wrapped_rank_bands(tmp_path: Path) -> None:
    page_html, payload = _target_diagram_page(tmp_path)
    graph = payload["explorers"]["target_diagrams"]["root"]
    graph["nodes"].extend(
        [
            {
                "id": f"COMP-WRAPPED-{index:02}",
                "kind": "component",
                "label": f"wrapped {index:02}",
                "dependency_rank": 0,
                "placement": {"status": "unmapped", "scopes": [], "container": None},
                "details": [],
            }
            for index in range(10)
        ]
        + [
            {
                "id": "COMP-RANK-ONE",
                "kind": "component",
                "label": "rank one",
                "dependency_rank": 1,
                "placement": {"status": "unmapped", "scopes": [], "container": None},
                "details": [],
            },
            {
                "id": "COMP-UNRANKED",
                "kind": "component",
                "label": "unranked",
                "dependency_rank": None,
                "placement": {"status": "unmapped", "scopes": [], "container": None},
                "details": [],
            },
        ]
    )
    page_html = _replace_flow_payload(page_html, payload)

    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 550, "height": 1000})
            page.set_content(page_html, wait_until="load")
            page.locator('[data-flow-view="target"]').click()
            bands = page.evaluate(
                """() => {
                  const y = id => Number(document.querySelector(`[data-target-node="${id}"]`)
                    .getAttribute('transform').match(/,([\\d.-]+)\\)/)[1]);
                  const warningY = Number(document.querySelector('.target-cycle-warning')
                    .getAttribute('y'));
                  const wrapped = Array.from({length: 10}, (_, index) =>
                    y(`COMP-WRAPPED-${String(index).padStart(2, '0')}`));
                  return {warningY, wrapped, rankOneY: y('COMP-RANK-ONE'),
                    unrankedY: y('COMP-UNRANKED')};
                }"""
            )
            assert len(set(bands["wrapped"])) > 1
            assert bands["rankOneY"] > max(bands["wrapped"])
            assert bands["warningY"] > bands["rankOneY"]
            assert bands["warningY"] < bands["unrankedY"]
        finally:
            browser.close()


def test_target_cycle_warning_clears_all_residual_frame_header(tmp_path: Path) -> None:
    page_html, payload = _target_diagram_page(tmp_path)
    graph = payload["explorers"]["target_diagrams"]["root"]
    for node in graph["nodes"]:
        if node["kind"] == "component":
            node["dependency_rank"] = None
    page_html = _replace_flow_payload(page_html, payload)

    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_content(page_html, wait_until="load")
            page.locator('[data-flow-view="target"]').click()
            geometry = page.evaluate(
                """() => {
                  const box = node => {
                    const {left, top, right, bottom} = node.getBoundingClientRect();
                    return {left, top, right, bottom};
                  };
                  const warning = box(document.querySelector('.target-cycle-warning'));
                  const titles = [...document.querySelectorAll('.target-frame-title')].map(box);
                  const cards = [...document.querySelectorAll('.flow-nodes .node')].map(box);
                  return {warning, titles, cards,
                    intersectsTitle: titles.some(title => warning.left < title.right
                      && warning.right > title.left && warning.top < title.bottom
                      && warning.bottom > title.top),
                    clearsTitles: titles.every(title => warning.bottom < title.top),
                    clearsCards: cards.every(card => warning.bottom < card.top)};
                }"""
            )
            assert not geometry["intersectsTitle"], geometry
            assert geometry["clearsTitles"], geometry
            assert geometry["clearsCards"], geometry
        finally:
            browser.close()


def test_target_cycle_warning_clears_residual_only_frame_in_mixed_graph(
    tmp_path: Path,
) -> None:
    page_html, payload = _target_diagram_page(tmp_path, cross_frame_chain=True)
    graph = payload["explorers"]["target_diagrams"]["root"]
    graph_nodes = {node["id"]: node for node in graph["nodes"]}
    kept_ids = {"COMP-RUNTIME", "COMP-A-DOMAINS", "COMP-IO"}
    graph["nodes"] = [graph_nodes[node_id] for node_id in sorted(kept_ids)]
    engine = graph["containers"]["layout:ENGINE-LAYOUT"]
    engine["parent"] = "layout:ROOT-LAYOUT"
    root = graph["containers"]["layout:ROOT-LAYOUT"]
    root["parent"] = None
    root["members"] = []
    graph["containers"] = {"layout:ROOT-LAYOUT": root, "layout:ENGINE-LAYOUT": engine}
    graph["edges"] = [
        edge for edge in graph["edges"] if edge["source"] in kept_ids and edge["target"] in kept_ids
    ]
    for node in graph["nodes"]:
        if node["kind"] == "component":
            node["dependency_rank"] = None
            if node["id"] == "COMP-A-DOMAINS":
                node["dependency_rank"] = 0
    assert graph["containers"]["layout:ENGINE-LAYOUT"]["members"] == [
        "COMP-IO",
        "COMP-RUNTIME",
    ]
    nodes = {node["id"]: node for node in graph["nodes"]}
    assert nodes["COMP-A-DOMAINS"]["dependency_rank"] == 0
    assert nodes["COMP-RUNTIME"]["dependency_rank"] is None
    assert nodes["COMP-IO"]["dependency_rank"] is None
    page_html = _replace_flow_payload(page_html, payload)

    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_content(page_html, wait_until="load")
            page.locator('[data-flow-view="target"]').click()
            geometry = page.evaluate(
                """() => {
                  const box = node => {
                    const {left, top, right, bottom} = node.getBoundingClientRect();
                    return {left, top, right, bottom};
                  };
                  const warning = box(document.querySelector('.target-cycle-warning'));
                  const titles = [...document.querySelectorAll('.target-frame-title')].map(box);
                  const cards = ['COMP-RUNTIME', 'COMP-IO'].map(id => box(
                    document.querySelector(`[data-target-node="${id}"]`)));
                  return {warning, titles, cards,
                    intersects: titles.some(title => warning.left < title.right
                      && warning.right > title.left && warning.top < title.bottom
                      && warning.bottom > title.top),
                    clearsCards: cards.every(card => warning.bottom < card.top)};
                }"""
            )
            assert not geometry["intersects"], geometry
            assert geometry["clearsCards"], geometry
        finally:
            browser.close()


def test_target_cycle_warning_clears_frameless_residual_cards(tmp_path: Path) -> None:
    page_html, payload = _target_diagram_page(tmp_path)
    graph = payload["explorers"]["target_diagrams"]["root"]
    graph["nodes"] = [node for node in graph["nodes"] if node["kind"] == "component"]
    graph["containers"] = {}
    graph["edges"] = []
    for node in graph["nodes"]:
        node["dependency_rank"] = None
    page_html = _replace_flow_payload(page_html, payload)

    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_content(page_html, wait_until="load")
            page.locator('[data-flow-view="target"]').click()
            geometry = page.evaluate(
                """() => {
                  const warning = document.querySelector('.target-cycle-warning')
                    .getBoundingClientRect();
                  const cards = [...document.querySelectorAll('.flow-nodes .node')]
                    .map(node => node.getBoundingClientRect());
                  return {warning: {bottom: warning.bottom},
                    firstCardTop: Math.min(...cards.map(card => card.top))};
                }"""
            )
            assert geometry["warning"]["bottom"] < geometry["firstCardTop"]
        finally:
            browser.close()


def test_target_acyclic_ranks_share_a_row_without_a_cycle_caption(tmp_path: Path) -> None:
    page_html, payload = _target_diagram_page(tmp_path, cross_frame_chain=True)
    graph = payload["explorers"]["target_diagrams"]["root"]
    nodes = {node["id"]: node for node in graph["nodes"]}
    graph["nodes"] = [nodes["COMP-A-DOMAINS"], nodes["COMP-IO"]]
    graph["nodes"][0]["dependency_rank"] = 0
    graph["nodes"][1]["dependency_rank"] = 1
    graph["containers"] = {}
    graph["edges"] = []
    page_html = _replace_flow_payload(page_html, payload)

    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_content(page_html, wait_until="load")
            page.locator('[data-flow-view="target"]').click()
            positions = page.evaluate(
                """() => ({positions: Object.fromEntries(['COMP-A-DOMAINS', 'COMP-IO'].map(id => {
                  const transform = document.querySelector(`[data-target-node="${id}"]`)
                    .getAttribute('transform');
                  return [id, Number(transform.match(/,([\\d.-]+)\\)/)[1])];
                })), cardHeight: document.querySelector(
                    '[data-target-node="COMP-A-DOMAINS"] .target-card')
                  .getBBox().height})"""
            )
            assert positions["positions"]["COMP-A-DOMAINS"] == 0
            assert positions["positions"]["COMP-IO"] == 0
            assert page.locator(".target-cycle-warning").count() == 0
        finally:
            browser.close()


def test_target_narrow_layout_keeps_physical_lanes_disjoint(tmp_path: Path) -> None:
    page_html, payload = _target_diagram_page(tmp_path, cross_frame_chain=True)
    graph = payload["explorers"]["target_diagrams"]["root"]
    components = {node["id"]: node for node in graph["nodes"] if node["kind"] == "component"}
    assert graph["containers"]["layout:ENGINE-LAYOUT"]["members"] == [
        "COMP-IO",
        "COMP-RUNTIME",
    ]
    assert (
        components["COMP-RUNTIME"]["dependency_rank"]
        < components["COMP-A-DOMAINS"]["dependency_rank"]
    )
    assert (
        components["COMP-A-DOMAINS"]["dependency_rank"] < components["COMP-IO"]["dependency_rank"]
    )

    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 550, "height": 1000})
            page.set_content(page_html, wait_until="load")
            page.locator('[data-flow-view="target"]').click()
            geometry = page.evaluate(
                """() => {
                  const containers = [...document.querySelectorAll('[data-target-container]')];
                  const frameRects = [...document.querySelectorAll('rect.target-frame')];
                  const engineIndex = containers.findIndex(node =>
                    node.getAttribute('data-target-container') === 'layout:ENGINE-LAYOUT');
                  const frame = frameRects[engineIndex];
                  const frameBox = {
                    left: Number(frame.getAttribute('x')),
                    top: Number(frame.getAttribute('y')),
                    right: Number(frame.getAttribute('x')) + Number(frame.getAttribute('width')),
                    bottom: Number(frame.getAttribute('y')) + Number(frame.getAttribute('height')),
                  };
                  const cards = Object.fromEntries(['COMP-RUNTIME', 'COMP-A-DOMAINS', 'COMP-IO']
                    .map(id => {
                      const node = document.querySelector(`[data-target-node="${id}"]`);
                      const [, x, y] = node.getAttribute('transform')
                        .match(/translate\\(([\\d.-]+),([\\d.-]+)\\)/);
                      return [id, {left: Number(x), top: Number(y),
                        right: Number(x) + 200, bottom: Number(y) + 92}];
                    }));
                  const inside = box => box.left >= frameBox.left && box.right <= frameBox.right &&
                    box.top >= frameBox.top && box.bottom <= frameBox.bottom;
                  const intersects = box =>
                    box.left < frameBox.right && box.right > frameBox.left &&
                    box.top < frameBox.bottom && box.bottom > frameBox.top;
                  return {runtimeInside: inside(cards['COMP-RUNTIME']),
                    ioInside: inside(cards['COMP-IO']),
                    domainsOutside: !intersects(cards['COMP-A-DOMAINS']),
                    canvasWidth: document.querySelector('.flow-canvas').clientWidth};
                }"""
            )
            assert geometry["canvasWidth"] < 600
            assert geometry["runtimeInside"] and geometry["ioInside"]
            assert geometry["domainsOutside"]
        finally:
            browser.close()


def test_target_resize_keeps_graph_coordinates_and_content_anchor(tmp_path: Path) -> None:
    page_html, _ = _target_diagram_page(tmp_path)
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_content(page_html, wait_until="load")
            page.locator('[data-flow-view="target"]').click()
            before = page.evaluate(
                """() => {
                  const canvas = document.querySelector('.flow-canvas');
                  const card = document.querySelector('[data-target-node="COMP-STORE"]');
                  const canvasRect = canvas.getBoundingClientRect();
                  const cardRect = card.getBoundingClientRect();
                  return {
                    positions: Object.fromEntries([...document.querySelectorAll(
                      '.target-node[data-placement-status]')].map(node => [
                        node.dataset.targetNode, node.getAttribute('transform')])),
                    frames: Object.fromEntries([...document.querySelectorAll(
                      '.target-container rect.target-frame')].map(rect => [
                        rect.closest('[data-target-container]').dataset.targetContainer,
                        [rect.getAttribute('x'), rect.getAttribute('y'),
                          rect.getAttribute('width'), rect.getAttribute('height')]])),
                    anchor: [cardRect.left - canvasRect.left, cardRect.top - canvasRect.top],
                    scroll: [canvas.scrollLeft, canvas.scrollTop],
                  };
                }"""
            )
            assert page.locator(".flow-canvas").evaluate("element => element.clientWidth") > 600
            page.set_viewport_size({"width": 520, "height": 1000})
            page.evaluate(
                "() => new Promise(resolve => requestAnimationFrame(() => "
                "requestAnimationFrame(resolve)))"
            )
            after = page.evaluate(
                """() => {
                  const canvas = document.querySelector('.flow-canvas');
                  const card = document.querySelector('[data-target-node="COMP-STORE"]');
                  const canvasRect = canvas.getBoundingClientRect();
                  const cardRect = card.getBoundingClientRect();
                  return {
                    positions: Object.fromEntries([...document.querySelectorAll(
                      '.target-node[data-placement-status]')].map(node => [
                        node.dataset.targetNode, node.getAttribute('transform')])),
                    frames: Object.fromEntries([...document.querySelectorAll(
                      '.target-container rect.target-frame')].map(rect => [
                        rect.closest('[data-target-container]').dataset.targetContainer,
                        [rect.getAttribute('x'), rect.getAttribute('y'),
                          rect.getAttribute('width'), rect.getAttribute('height')]])),
                    anchor: [cardRect.left - canvasRect.left, cardRect.top - canvasRect.top],
                    scroll: [canvas.scrollLeft, canvas.scrollTop],
                  };
                }"""
            )
            assert page.locator(".flow-canvas").evaluate("element => element.clientWidth") < 600
            assert after["positions"] == before["positions"]
            assert after["frames"] == before["frames"]
            assert after["anchor"] == pytest.approx(before["anchor"], abs=2)
            assert after["scroll"] == pytest.approx(before["scroll"], abs=1)
        finally:
            browser.close()


@pytest.mark.parametrize("viewport", [(1440, 1000), (1856, 1336)])
def test_target_hierarchy_browser_layout_and_details_toggle(
    tmp_path: Path, viewport: tuple[int, int]
) -> None:
    page_html, payload = _target_diagram_page(tmp_path, cycle=True)
    graph = payload["explorers"]["target_diagrams"]["root"]
    cyclic = {
        node["id"]
        for node in graph["nodes"]
        if node["kind"] == "component" and node["dependency_rank"] is None
    }
    assert cyclic == {"COMP-APP", "COMP-ARCHIVE"}
    assert graph["containers"]["layout:ROOT-LAYOUT"]["members"]

    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})
            page_errors: list[str] = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.set_content(page_html, wait_until="load")
            diagram_metrics = page.locator(".flow-nodes").evaluate(
                """layer => [...layer.querySelectorAll('.diagram-responsibility, .meta')]
                  .map(text => {
                    const card = text.closest('.node').querySelector('.card').getBBox();
                    const box = text.getBBox();
                    const matrix = text.getScreenCTM();
                    const style = getComputedStyle(text);
                    return {
                      role: text.classList.contains('diagram-responsibility')
                        ? 'responsibility' : 'meta',
                      right: box.x + box.width,
                      cardRight: card.x + card.width - 8,
                      font: parseFloat(style.fontSize) * Math.hypot(matrix.a, matrix.b),
                    };
                  })"""
            )
            assert diagram_metrics
            assert all(item["right"] <= item["cardRight"] for item in diagram_metrics)
            assert (
                min(item["font"] for item in diagram_metrics if item["role"] == "responsibility")
                >= 13
            )
            page.locator('[data-flow-view="target"]').click()
            assert page_errors == []
            canvas = page.locator(".flow-canvas")
            assert canvas.is_visible()
            assert page.locator(".flow-zoom-value").text_content() == "100%"
            rendered_components = set(
                page.locator(".target-node[data-placement-status]").evaluate_all(
                    "nodes => nodes.map(node => node.dataset.targetNode)"
                )
            )
            expected_components = {
                node["id"] for node in graph["nodes"] if node["kind"] == "component"
            }
            assert rendered_components == expected_components
            assert page.locator("[data-target-container='layout:ROOT-LAYOUT']").count() == 1
            assert page.locator("[data-target-container-open='layout:ROOT-LAYOUT']").count() == 1
            assert page.locator(".flow-legend-hint").get_attribute("data-scope-count") == (
                f"{len(graph['nodes'])}/{len(graph['nodes'])}"
            )
            assert page.get_by_text(
                "Dependency order unresolved: cycle or dependency on a cycle."
            ).is_visible()

            # Card text must stay readable after the SVG transform, and placed cards cannot overlap.
            metrics = page.locator(".flow-nodes").evaluate(
                """layer => {
                  const screenBox = element => {
                    const box = element.getBBox();
                    const matrix = element.getScreenCTM();
                    const points = [
                      new DOMPoint(box.x, box.y), new DOMPoint(box.x + box.width, box.y),
                      new DOMPoint(box.x, box.y + box.height),
                      new DOMPoint(box.x + box.width, box.y + box.height),
                    ].map(point => point.matrixTransform(matrix));
                    return {
                      left: Math.min(...points.map(point => point.x)),
                      right: Math.max(...points.map(point => point.x)),
                      top: Math.min(...points.map(point => point.y)),
                      bottom: Math.max(...points.map(point => point.y)),
                    };
                  };
                  const cards = [...layer.querySelectorAll('.target-node[data-placement-status]')]
                    .map(node => ({ id: node.dataset.targetNode, box: screenBox(node) }));
                  const overlap = cards.some((left, index) => cards.slice(index + 1).some(right =>
                    left.box.left < right.box.right && left.box.right > right.box.left &&
                    left.box.top < right.box.bottom && left.box.bottom > right.box.top));
                  const scaledFont = selector => [...layer.querySelectorAll(selector)].map(node => {
                    const style = getComputedStyle(node);
                    const matrix = node.getScreenCTM();
                    return parseFloat(style.fontSize) * Math.hypot(matrix.a, matrix.b);
                  });
                  return {
                    overlap,
                    names: scaledFont('.target-label'),
                    responsibilities: scaledFont('.target-responsibility'),
                  };
                }"""
            )
            assert not metrics["overlap"]
            assert metrics["names"] and min(metrics["names"]) >= 14
            assert metrics["responsibilities"] and min(metrics["responsibilities"]) >= 13

            details_toggle = page.locator("[data-flow-details-toggle]")
            assert details_toggle.get_attribute("aria-expanded") == "false"
            assert details_toggle.get_attribute("aria-controls") == "flow-inspector"
            frame = page.locator("[data-target-container-open='layout:ROOT-LAYOUT']")
            frame.focus()
            page.keyboard.press("Enter")
            assert "shop" in page.locator(".flow-breadcrumb").inner_text()
            inspector = page.locator(".flow-inspector")
            assert details_toggle.get_attribute("aria-expanded") == "false"
            details_toggle.click()
            assert details_toggle.get_attribute("aria-expanded") == "true"
            assert inspector.is_visible()
            inspector_rect = inspector.evaluate(
                "element => element.getBoundingClientRect().toJSON()"
            )
            assert inspector_rect["x"] >= 0
            assert inspector_rect["x"] + inspector_rect["width"] <= viewport[0]
            assert inspector_rect["y"] < viewport[1]
            assert inspector_rect["y"] + inspector_rect["height"] > 0
            page.get_by_role("button", name="Zoom in").click()
            anchor = canvas.evaluate(
                "element => { element.scrollTop = Math.min(80, "
                "element.scrollHeight - element.clientHeight); "
                "return {top: element.scrollTop, left: element.scrollLeft}; }"
            )
            before = {
                "path": page.locator(".flow-breadcrumb").inner_text(),
                "zoom": page.locator(".flow-zoom-value").text_content(),
                "position": page.locator(
                    "[data-target-container='layout:ROOT-LAYOUT'] rect"
                ).evaluate(
                    "element => [element.getAttribute('x'), element.getAttribute('y')].join(',')"
                ),
                "selection": page.locator(".target-node.selected").evaluate_all(
                    "nodes => nodes.map(node => node.dataset.targetNode)"
                ),
                "anchor": anchor,
            }
            details_toggle.click()
            assert details_toggle.get_attribute("aria-expanded") == "false"
            assert page.locator(".flow-inspector").is_hidden()
            assert page.locator(".flow-breadcrumb").inner_text() == before["path"]
            assert page.locator(".flow-zoom-value").text_content() == before["zoom"]
            assert (
                page.locator(".target-node.selected").evaluate_all(
                    "nodes => nodes.map(node => node.dataset.targetNode)"
                )
                == before["selection"]
            )
            assert (
                page.locator("[data-target-container='layout:ROOT-LAYOUT'] rect").evaluate(
                    "element => [element.getAttribute('x'), element.getAttribute('y')].join(',')"
                )
                == before["position"]
            )
            assert (
                canvas.evaluate("element => ({top: element.scrollTop, left: element.scrollLeft})")
                == before["anchor"]
            )

            page.set_viewport_size({"width": viewport[0] + 80, "height": viewport[1] + 60})
            page.evaluate(
                "() => new Promise(resolve => requestAnimationFrame(() => "
                "requestAnimationFrame(resolve)))"
            )
            assert page.locator(".flow-breadcrumb").inner_text() == before["path"]
            assert page.locator(".flow-zoom-value").text_content() == before["zoom"]
            assert details_toggle.get_attribute("aria-expanded") == "false"
            resized_anchor = canvas.evaluate(
                "element => ({top: element.scrollTop, left: element.scrollLeft})"
            )
            assert resized_anchor["left"] == before["anchor"]["left"]
            max_scroll = page.locator(".flow-canvas").evaluate(
                "element => element.scrollHeight - element.clientHeight"
            )
            assert abs(resized_anchor["top"] - min(before["anchor"]["top"], max_scroll)) <= 1
            details_toggle.click()
            assert details_toggle.get_attribute("aria-expanded") == "true"
            inspector = page.locator(".flow-inspector")
            assert inspector.is_visible()
            inspector_rect = inspector.evaluate(
                "element => element.getBoundingClientRect().toJSON()"
            )
            assert inspector_rect["x"] >= 0
            assert inspector_rect["x"] + inspector_rect["width"] <= viewport[0] + 80
            assert inspector_rect["y"] < viewport[1] + 60
            assert inspector_rect["y"] + inspector_rect["height"] > 0
            assert page.locator(".flow-canvas").evaluate("element => element.clientWidth") > 1000
            assert page_errors == []
        finally:
            browser.close()


def test_target_diagram_opens_exact_module_leaf_as_module(tmp_path: Path) -> None:
    page_html, payload = _target_diagram_page(tmp_path, include_module_target=True)
    target_nodes = list(_walk(payload["explorers"]["target"]))
    nested_empty = next(node for node in target_nodes if node["label"] == "empty nested")
    leaf = next(
        node
        for node in target_nodes
        if any(
            detail["label"] == "File" and detail["value"] == "shop/app/orders.py"
            for detail in node["details"]
        )
    )
    route = _component_route(payload["explorers"]["target"], leaf["id"])
    assert route
    navigation_edge = next(
        edge
        for edge in payload["explorers"]["target_diagrams"]["nested"][route[-1]]["edges"]
        if edge["target"] == leaf["id"]
    )
    assert navigation_edge["kind"] == "navigation_grouping"
    assert any(
        detail["label"] == "Navigation"
        and detail["value"] == "Grouped by declared package scope shop.app."
        for detail in leaf["details"]
    )
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            channel=os.environ.get("PLAYWRIGHT_CHANNEL"),
        )
        try:
            page = browser.new_page()
            page.set_content(page_html, wait_until="load")
            page.get_by_role("button", name="Target").click()
            if page.locator("[data-flow-details-toggle]").get_attribute("aria-expanded") != "true":
                page.locator("[data-flow-details-toggle]").click()
            responsibilities = page.locator(".flow-responsibilities")
            responsibilities.locator("summary").click()
            declared_count = sum(
                detail["label"] == "Responsibility" and not detail.get("missing")
                for node in target_nodes
                for detail in node["details"]
            )
            missing_count = sum(
                detail["label"] == "Responsibility" and detail.get("missing") is True
                for node in target_nodes
                for detail in node["details"]
            )
            total_rows = declared_count + missing_count
            assert (
                responsibilities.locator(".flow-responsibility-list button").count() == total_rows
            )
            assert declared_count == sum(
                sum(
                    detail["label"] == "Responsibility" and not detail.get("missing")
                    for detail in node["details"]
                )
                for node in target_nodes
                if node["kind"] in {"component", "module_target"}
            )
            assert responsibilities.locator(".flow-responsibility-total").text_content() == (
                f"({declared_count} declared · {missing_count} missing)"
            )
            responsibilities.locator("input").fill("Retain archived orders.")
            assert responsibilities.locator(".flow-responsibility-count").text_content() == (
                f"1 of {total_rows} shown"
            )
            responsibilities.locator(".flow-responsibility-list button:visible").click()
            assert (
                page.locator(".flow-inspector .kv dd")
                .filter(has_text="Retain archived orders.")
                .is_visible()
            )
            responsibilities.locator("input").fill("Keep archive access explicit.")
            assert responsibilities.locator(".flow-responsibility-count").text_content() == (
                f"1 of {total_rows} shown"
            )
            responsibilities.locator(".flow-responsibility-list button:visible").click()
            assert (
                page.locator(".flow-inspector .kv dd")
                .filter(has_text="Keep archive access explicit.")
                .is_visible()
            )
            responsibilities.locator("input").fill("store / empty nested")
            assert responsibilities.locator(".flow-responsibility-count").text_content() == (
                f"1 of {total_rows} shown"
            )
            responsibilities.locator(".flow-responsibility-list button:visible").click()
            inspector = page.locator(".flow-inspector")
            assert inspector.get_by_role("heading", name="Missing responsibility").is_visible()
            assert (
                inspector.locator("p")
                .get_by_text("No declared responsibility.", exact=True)
                .is_visible()
            )
            assert "store" in page.locator(".flow-breadcrumb").text_content().lower()
            nested_card = page.locator(
                f".flow-nodes .node[data-target-node='{nested_empty['id']}']"
            )
            assert nested_card.is_visible()
            assert "No declared responsibility" in nested_card.locator("title").text_content()
            assert "No declared responsibility" in " ".join(
                nested_card.locator(".target-responsibility").all_text_contents()
            )
            responsibilities.locator("input").fill("Coordinate order workflows")
            assert responsibilities.locator(".flow-responsibility-count").text_content() == (
                f"1 of {total_rows} shown"
            )
            responsibilities.locator(".flow-responsibility-list button:visible").click()
            assert (
                page.locator(".flow-inspector .kv dd")
                .filter(has_text="Coordinate order workflows.")
                .is_visible()
            )
            path = page.locator(".flow-breadcrumb").text_content()
            page.locator(".flow-back").click()
            responsibilities.locator(".flow-responsibility-list button:visible").click()
            assert page.locator(".flow-breadcrumb").text_content() == path
            page.locator('.flow-views [data-flow-view="target"]').click()
            for component_id in route:
                _open_target_node(page, f'.flow-nodes .node[data-target-node="{component_id}"]')
            card = page.locator(f'.flow-nodes .node[data-target-node="{leaf["id"]}"]')
            assert card.is_visible()
            assert card.locator(".target-kind").text_content() == "MODULE"
            card.click()
            inspector = page.locator(".flow-inspector")
            assert (
                inspector.locator(".kv dd")
                .get_by_text("shop/app/orders.py", exact=True)
                .is_visible()
            )
            assert (
                inspector.locator(".kv dd")
                .get_by_text("Coordinate order workflows.", exact=True)
                .is_visible()
            )
        finally:
            browser.close()

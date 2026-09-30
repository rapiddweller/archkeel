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


def _target_diagram_page(
    tmp_path: Path, *, include_module_target: bool = False
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
    if include_module_target:
        contract.setdefault("declarations", {}).setdefault("modules", []).append(
            {
                "path": "shop/app/orders.py",
                "responsibility": "Coordinate order workflows.",
            }
        )
    root_layout = next(rule for rule in contract["rules"] if rule["kind"] == "root_layout")
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
            assert (
                page.locator(
                    '.target-node[data-target-node="COMP-STORE"] .target-meta'
                ).text_content()
                == "Persist orders as JSON"
            )
            assert page.locator(
                '.target-node[data-target-node="COMP-STORE"] .target-responsibility'
            ).all_text_contents() == ["Persist orders as JSON", "files."]
            assert page.locator(".flow-filter-status").text_content().strip() != (
                "No diagram filters active"
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

            page.locator('.flow-nodes .node[data-target-node="layout:ROOT-LAYOUT"]').click()
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
            nested_labels = {
                label
                for label in page.locator(".flow-nodes .node").evaluate_all(
                    "nodes => nodes.map(node => node.getAttribute('data-label'))"
                )
            }
            assert {"api", "backend", "codec", "repository"} <= nested_labels
            assert page.locator(".flow-edges .edge").count() > 0
            assert page.locator(".flow-filter-status").text_content().strip() != (
                "No diagram filters active"
            )
            page.locator(".flow-back").click()
            assert page.locator('.flow-nodes .node[data-target-node="COMP-STORE"]').is_visible()

            page.get_by_role("button", name="Diff").click()
            for category, entry in (
                ("diff:unmapped", "unmapped:shop.orphan"),
                ("diff:absent", "absent:ROOT-LAYOUT:shop.missing"),
            ):
                page.locator(f'[data-projection-id="{category}"]').click()
                page.locator(f'[data-projection-id="{entry}"]').click()
                assert page.locator('.flow-projection [aria-label="Selected entry"]').is_visible()
                page.locator("[data-projection-root]").click()

            page.set_viewport_size({"width": 375, "height": 844})
            page.get_by_role("button", name="Actual").click()
            page.locator('[data-projection-id="shop"]').click()
            assert page.locator('[data-projection-id="shop.orphan"]').is_visible()
            page.get_by_role("button", name="Diff").click()
            page.locator('[data-projection-id="diff:unmapped"]').click()
            assert page.locator('[data-projection-id="unmapped:shop.orphan"]').is_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
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
                page.locator(".flow-inspector")
                .get_by_text("Retain archived orders.", exact=True)
                .is_visible()
            )
            responsibilities.locator("input").fill("Keep archive access explicit.")
            assert responsibilities.locator(".flow-responsibility-count").text_content() == (
                f"1 of {total_rows} shown"
            )
            responsibilities.locator(".flow-responsibility-list button:visible").click()
            assert (
                page.locator(".flow-inspector")
                .get_by_text("Keep archive access explicit.", exact=True)
                .is_visible()
            )
            responsibilities.locator("input").fill("store / empty nested")
            assert responsibilities.locator(".flow-responsibility-count").text_content() == (
                f"1 of {total_rows} shown"
            )
            responsibilities.locator(".flow-responsibility-list button:visible").click()
            inspector = page.locator(".flow-inspector")
            assert inspector.get_by_text("Missing responsibility", exact=True).is_visible()
            assert inspector.get_by_text("No declared responsibility.", exact=True).is_visible()
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
                page.locator(".flow-inspector")
                .get_by_text("Coordinate order workflows.", exact=True)
                .is_visible()
            )
            path = page.locator(".flow-breadcrumb").text_content()
            page.locator(".flow-back").click()
            responsibilities.locator(".flow-responsibility-list button:visible").click()
            assert page.locator(".flow-breadcrumb").text_content() == path
            page.locator('.flow-views [data-flow-view="target"]').click()
            for component_id in route:
                page.locator(f'.flow-nodes .node[data-target-node="{component_id}"]').click()
            card = page.locator(f'.flow-nodes .node[data-target-node="{leaf["id"]}"]')
            assert card.is_visible()
            assert card.locator(".target-kind").text_content() == "MODULE"
            card.click()
            inspector = page.locator(".flow-inspector")
            assert inspector.get_by_text("shop/app/orders.py", exact=True).is_visible()
            assert inspector.get_by_text("Coordinate order workflows.", exact=True).is_visible()
        finally:
            browser.close()

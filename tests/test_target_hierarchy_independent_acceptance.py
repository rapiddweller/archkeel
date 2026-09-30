# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Independent acceptance for declared target hierarchy and browser behavior."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from test_architecture_demo import CONFIG, _prepare_repo
from test_target_diagram_acceptance import _target_diagram_page

from archkeel.analyzer import observe
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.render.html import render_html
from fixtures.architecture_demo import CATALOG
from fixtures.demo_catalog_support import FIXTURE_DIR


def _nodes(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {node["id"]: node for node in graph["nodes"]}


def _cycle_page(tmp_path: Path) -> tuple[str, dict[str, Any]]:
    tour = next(item for item in CATALOG if item.id == "tour")
    contract = json.loads((FIXTURE_DIR / "architecture-contract.json").read_text())
    components = {component["id"]: component for component in contract["components"]}
    app = components["COMP-APP"]
    app["requires"] = [{"component": "archive", "rationale": "The app depends on the archive."}]
    archive = {
        **components["COMP-MODEL"],
        "id": "COMP-ARCHIVE",
        "label": "archive",
        "packages": ["shop.archive"],
        "namespace": "shop.archive",
        "public": [],
        "requires": [{"component": "empty", "rationale": "The archive depends on empty."}],
    }
    empty = {
        **components["COMP-MODEL"],
        "id": "COMP-EMPTY",
        "label": "empty",
        "packages": ["shop.empty"],
        "namespace": "shop.empty",
        "public": None,
        "requires": [{"component": "archive", "rationale": "Empty depends on archive."}],
    }
    store = components["COMP-STORE"]
    store["requires"] = [{"component": "store", "rationale": "Keep the self-cycle visible."}]
    contract["components"].extend([archive, empty])
    root_layout = next(rule for rule in contract["rules"] if rule["kind"] == "root_layout")
    root_layout["allowed_children"].extend(["shop.archive", "shop.empty"])
    nested = (FIXTURE_DIR / "shop/store/architecture-contract.json").read_text()
    files = {
        **dict(tour.files),
        "architecture-contract.json": json.dumps(contract),
        "shop/store/architecture-contract.json": nested,
    }
    root = _prepare_repo(tmp_path, files)
    result, architecture = run_report(root, config=CONFIG, analyzer=observe)
    assert architecture is not None, result.diagnostics
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))
    page = render_html(
        result, observation, repository="shop", architecture_href="architecture.json"
    ).decode()
    start = page.index('id="flow-data"')
    payload = json.loads(page[page.index(">", start) + 1 : page.index("</script>", start)])
    return page, payload


def _placement_page(tmp_path: Path) -> dict[str, Any]:
    tour = next(item for item in CATALOG if item.id == "tour")
    contract = json.loads((FIXTURE_DIR / "architecture-contract.json").read_text())
    model = next(
        component for component in contract["components"] if component["id"] == "COMP-MODEL"
    )

    def component(
        component_id: str, label: str, packages: list[str], *, public: list[str] | None
    ) -> dict[str, Any]:
        item = copy.deepcopy(model)
        item.update(
            id=component_id,
            label=label,
            packages=packages,
            responsibilities=[],
            forbidden_responsibilities=[],
            public=public,
        )
        item.pop("namespace", None)
        return item

    contract["components"].extend(
        [
            component("COMP-MULTI", "multi", ["shop.alpha", "shop.beta"], public=[]),
            component("COMP-AMBIG", "ambiguous", ["shop.ambiguous.api"], public=None),
            component("COMP-UNSUPPORTED", "wildcard", ["shop.*"], public=[]),
        ]
    )
    root_layout = next(rule for rule in contract["rules"] if rule["kind"] == "root_layout")
    root_layout["allowed_children"].extend(
        ["shop.alpha", "shop.beta", "shop.ambiguous", "shop.detached"]
    )
    for layout_id in ("AMBIG-LAYOUT-A", "AMBIG-LAYOUT-B"):
        contract["rules"].append(
            {
                **root_layout,
                "id": layout_id,
                "root": "shop.ambiguous",
                "allowed_children": ["shop.ambiguous.api"],
            }
        )
    app = next(component for component in contract["components"] if component["id"] == "COMP-APP")
    app["requires"] = [
        {
            "component": "store",
            "through": ["shop.store.gateway"],
            "rationale": "Keep the API edge explicit.",
        }
    ]
    contract["components"].append(
        component("COMP-EMPTY-PUBLIC", "empty public", ["shop.empty_public"], public=[])
    )
    absent = component("COMP-ABSENT-PUBLIC", "absent public", ["shop.absent_public"], public=[])
    absent.pop("public")
    contract["components"].append(absent)
    root_layout["allowed_children"].extend(["shop.empty_public", "shop.absent_public"])

    nested = (FIXTURE_DIR / "shop/store/architecture-contract.json").read_text()
    root = _prepare_repo(
        tmp_path,
        {
            **dict(tour.files),
            "architecture-contract.json": json.dumps(contract),
            "shop/store/architecture-contract.json": nested,
            "shop/orphan.py": "VALUE = 1\n",
        },
    )
    result, architecture = run_report(root, config=CONFIG, analyzer=observe)
    assert architecture is not None, result.diagnostics
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))
    page = render_html(
        result, observation, repository="shop", architecture_href="architecture.json"
    ).decode()
    start = page.index('id="flow-data"')
    return json.loads(page[page.index(">", start) + 1 : page.index("</script>", start)])


def _parent_with_inside_components_page(tmp_path: Path) -> dict[str, Any]:
    tour = next(item for item in CATALOG if item.id == "tour")

    def component(
        component_id: str,
        label: str,
        scope: str,
        *,
        inside: str | None = None,
    ) -> dict[str, Any]:
        return {
            "id": component_id,
            "label": label,
            "role": "component",
            "packages": [scope],
            "namespace": scope,
            "responsibilities": [f"Own {label} behavior."],
            "forbidden_responsibilities": [],
            "public": [],
            "provenance": ["docs/architecture/engine.md"],
            "decided_by": "architect",
            **({"inside": inside} if inside else {}),
        }

    def layout(rule_id: str, root: str, children: list[str], rationale: str) -> dict[str, Any]:
        return {
            "id": rule_id,
            "kind": "root_layout",
            "root": root,
            "allowed_children": children,
            "rationale": rationale,
            "provenance": ["docs/architecture/engine.md"],
            "decided_by": "architect",
        }

    def inside_contract(
        root: str,
        layout_id: str,
        children: list[tuple[str, str, str]],
        physical_only: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        return {
            "schema_version": "2.1.0",
            "components": [component(*child) for child in children],
            "rules": [
                layout(
                    layout_id,
                    root,
                    [scope for _, _, scope in children] + list(physical_only),
                    f"Keep the {root} layout explicit.",
                )
            ],
        }

    root_scope = "shop.engine"
    root_components = [
        ("COMP-DSL", "DSL", f"{root_scope}.dsl", "shop/engine/dsl/architecture-contract.json"),
        ("COMP-IO", "IO", f"{root_scope}.io", "shop/engine/io/architecture-contract.json"),
        (
            "COMP-RUNTIME",
            "Runtime",
            f"{root_scope}.runtime",
            "shop/engine/runtime/architecture-contract.json",
        ),
    ]
    contract = {
        "schema_version": "2.1.0",
        "components": [
            component(component_id, label, scope, inside=inside)
            for component_id, label, scope, inside in root_components
        ],
        "rules": [
            layout("ROOT-LAYOUT", "shop", [root_scope], "Keep the package root explicit."),
            layout(
                "LAYOUT-ENGINE",
                root_scope,
                [scope for _, _, scope, _ in root_components],
                "Place the three root owners directly in Engine.",
            ),
            *[
                layout(
                    f"LAYOUT-ENGINE-{label.upper()}",
                    scope,
                    [f"{scope}.leaf", *([f"{scope}.compat"] if label == "Runtime" else [])],
                    f"Preserve the declared {label} layout.",
                )
                for _, label, scope, _ in root_components
            ],
        ],
    }

    nested_files = {
        "shop/engine/dsl/architecture-contract.json": inside_contract(
            "shop.engine.dsl",
            "LAYOUT-DSL-INNER",
            [("COMP-DSL-PARSER", "parser", "shop.engine.dsl.leaf")],
        ),
        "shop/engine/io/architecture-contract.json": inside_contract(
            "shop.engine.io",
            "LAYOUT-IO-INNER",
            [("COMP-IO-FILES", "files", "shop.engine.io.leaf")],
        ),
        "shop/engine/runtime/architecture-contract.json": inside_contract(
            "shop.engine.runtime",
            "LAYOUT-RUNTIME-INNER",
            [
                ("COMP-RUNTIME-TASKS", "tasks", "shop.engine.runtime.tasks"),
                ("COMP-RUNTIME-WORKERS", "workers", "shop.engine.runtime.workers"),
            ],
            physical_only=("shop.engine.runtime.metadata",),
        ),
    }
    files = {
        **dict(tour.files),
        "architecture-contract.json": json.dumps(contract),
        **{path: json.dumps(item) for path, item in nested_files.items()},
    }

    root = _prepare_repo(tmp_path, files)
    result, architecture = run_report(root, config=CONFIG, analyzer=observe)
    assert architecture is not None, result.diagnostics
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))
    page = render_html(
        result, observation, repository="shop", architecture_href="architecture.json"
    ).decode()
    start = page.index('id="flow-data"')
    return json.loads(page[page.index(">", start) + 1 : page.index("</script>", start)])


def _folded_single_component_page(tmp_path: Path) -> tuple[str, dict[str, Any]]:
    tour = next(item for item in CATALOG if item.id == "tour")
    contract = json.loads((FIXTURE_DIR / "architecture-contract.json").read_text())
    app = next(component for component in contract["components"] if component["id"] == "COMP-APP")
    app.pop("inside", None)
    contract["components"] = [app]
    contract["rules"] = [
        {
            "id": "ROOT-SOLO",
            "kind": "root_layout",
            "root": "shop.app",
            "allowed_children": ["shop.app.orders"],
            "rationale": "Keep the single-component layout declaration navigable.",
            "provenance": ["docs/architecture/shop.md"],
            "decided_by": "architect",
        }
    ]
    root = _prepare_repo(
        tmp_path,
        {
            **dict(tour.files),
            "architecture-contract.json": json.dumps(contract),
            "shop/orphan.py": "VALUE = 1\n",
        },
    )
    result, architecture = run_report(root, config=CONFIG, analyzer=observe)
    assert architecture is not None, result.diagnostics
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))
    page = render_html(
        result, observation, repository="shop", architecture_href="architecture.json"
    ).decode()
    start = page.index('id="flow-data"')
    payload = json.loads(page[page.index(">", start) + 1 : page.index("</script>", start)])
    return page, payload


def _ce_nested_route_page(tmp_path: Path) -> tuple[str, dict[str, Any]]:
    def component(
        component_id: str,
        label: str,
        package: str,
        *,
        inside: str | None = None,
        namespace: bool = False,
    ) -> dict[str, Any]:
        record: dict[str, Any] = {
            "id": component_id,
            "label": label,
            "role": "component",
            "packages": [package],
            "responsibilities": [f"Own {label} behavior."],
            "forbidden_responsibilities": [],
            "public": [],
            "provenance": ["docs/architecture/ce.md"],
            "decided_by": "architect",
        }
        if namespace:
            record["namespace"] = package
        if inside:
            record["inside"] = inside
        return record

    def layout(rule_id: str, root: str, children: list[str]) -> dict[str, Any]:
        return {
            "id": rule_id,
            "kind": "root_layout",
            "root": root,
            "allowed_children": children,
            "rationale": "Keep the declared CE route explicit.",
            "provenance": ["docs/architecture/ce.md"],
            "decided_by": "architect",
        }

    root_owners = [
        component("COMP-DSL", "dsl", "datamimic_ce.engine.dsl", namespace=True),
        component("COMP-IO", "io", "datamimic_ce.engine.io", namespace=True),
        component(
            "COMP-RUNTIME",
            "runtime",
            "datamimic_ce.engine.runtime",
            inside="docs/architecture/inner/runtime/architecture-contract.json",
            namespace=True,
        ),
    ]
    runtime_packages = [
        ("RUNTIME-API", "api", "api"),
        ("RUNTIME-CONTRACTS", "contracts", "contracts"),
        ("RUNTIME-STORAGE", "storage", "storage"),
        ("RUNTIME-LOGGING", "logging", "logging"),
        ("RUNTIME-CONTEXTS", "contexts", "contexts"),
        ("RUNTIME-TASKS", "tasks", "tasks"),
        ("RUNTIME-LIFECYCLE", "lifecycle", "lifecycle"),
        ("RUNTIME-EVALUATION", "evaluation", "scripting"),
    ]
    task_packages = [
        ("TASKS-BASE", "base", "base"),
        ("TASKS-SETUP", "setup", "setup"),
        ("TASKS-GENERATE", "generate", "generate"),
        ("TASKS-VALUES", "values", "values"),
        ("TASKS-FLOW", "flow", "flow"),
        ("TASKS-SOURCES", "sources", "sources"),
        ("TASKS-REGISTRY", "registry", "registry"),
    ]
    generate_packages = [
        ("GENERATE-ORCHESTRATION", "orchestration", "task"),
        ("GENERATE-WORKERS", "workers", "workers"),
        ("GENERATE-EXPORT-ORDER", "export_order", "export_order"),
        ("GENERATE-POLICIES", "policies", "policies"),
    ]
    runtime_path = "datamimic_ce.engine.runtime"
    tasks_path = f"{runtime_path}.tasks"
    generate_path = f"{tasks_path}.generate"
    runtime_contract = {
        "schema_version": "2.1.0",
        "components": [
            component(
                f"{component_id}",
                label,
                f"{runtime_path}.{package_suffix}",
                inside=(
                    "docs/architecture/inner/runtime/tasks/architecture-contract.json"
                    if component_id == "RUNTIME-TASKS"
                    else None
                ),
            )
            for component_id, label, package_suffix in runtime_packages
        ],
        "rules": [
            layout(
                "LAYOUT-ENGINE-RUNTIME-TASKS",
                tasks_path,
                [f"{tasks_path}.{package_suffix}" for _, _, package_suffix in task_packages],
            )
        ],
    }
    tasks_contract = {
        "schema_version": "2.1.0",
        "components": [
            component(
                component_id,
                label,
                f"{tasks_path}.{package_suffix}",
                inside=(
                    "docs/architecture/inner/runtime/tasks/generate/architecture-contract.json"
                    if component_id == "TASKS-GENERATE"
                    else None
                ),
            )
            for component_id, label, package_suffix in task_packages
        ],
        "rules": [
            layout(
                "LAYOUT-ENGINE-RUNTIME-TASKS-GENERATE",
                generate_path,
                [f"{generate_path}.{package_suffix}" for _, _, package_suffix in generate_packages],
            )
        ],
    }
    generate_contract = {
        "schema_version": "2.1.0",
        "components": [
            component(component_id, label, f"{generate_path}.{package_suffix}")
            for component_id, label, package_suffix in generate_packages
        ],
        "rules": [
            layout(
                "LAYOUT-ENGINE-RUNTIME-TASKS-GENERATE-WORKERS",
                f"{generate_path}.workers",
                [
                    f"{generate_path}.workers.generate_worker",
                    f"{generate_path}.workers.multiprocessing_generate_worker",
                    f"{generate_path}.workers.ray_generate_worker",
                ],
            )
        ],
    }
    root_contract = {
        "schema_version": "2.1.0",
        "components": root_owners,
        "rules": [
            layout("LAYOUT-ROOT", "datamimic_ce", ["datamimic_ce.engine"]),
            layout(
                "LAYOUT-ENGINE",
                "datamimic_ce.engine",
                [
                    "datamimic_ce.engine.dsl",
                    "datamimic_ce.engine.io",
                    "datamimic_ce.engine.runtime",
                ],
            ),
        ],
    }
    packages = [
        *(owner["packages"][0] for owner in root_owners),
        *(f"{runtime_path}.{suffix}" for _, _, suffix in runtime_packages),
        *(f"{tasks_path}.{suffix}" for _, _, suffix in task_packages),
        *(f"{generate_path}.{suffix}" for _, _, suffix in generate_packages),
    ]
    files = {
        "architecture-contract.json": json.dumps(root_contract),
        "docs/architecture/inner/runtime/architecture-contract.json": json.dumps(runtime_contract),
        "docs/architecture/inner/runtime/tasks/architecture-contract.json": json.dumps(
            tasks_contract
        ),
        "docs/architecture/inner/runtime/tasks/generate/architecture-contract.json": json.dumps(
            generate_contract
        ),
        "datamimic_ce/unlisted.py": "VALUE = 1\n",
    }
    files.update({f"{package.replace('.', '/')}/__init__.py": "" for package in packages})
    root = _prepare_repo(tmp_path, files)
    config = ScanConfig(("datamimic_ce",), "datamimic_ce", "architecture-contract.json", "0" * 64)
    result, architecture = run_report(root, config=config, analyzer=observe)
    assert architecture is not None, result.diagnostics
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))
    page = render_html(
        result, observation, repository="datamimic_ce", architecture_href="architecture.json"
    ).decode()
    start = page.index('id="flow-data"')
    payload = json.loads(page[page.index(">", start) + 1 : page.index("</script>", start)])
    return page, payload


def _cross_frame_domains_page(tmp_path: Path) -> tuple[str, dict[str, Any]]:
    def component(
        component_id: str,
        label: str,
        package: str,
        *,
        inside: str | None = None,
    ) -> dict[str, Any]:
        record: dict[str, Any] = {
            "id": component_id,
            "label": label,
            "role": "component",
            "packages": [package],
            "namespace": package,
            "responsibilities": [f"Own {label} behavior."],
            "forbidden_responsibilities": [],
            "public": [],
            "provenance": ["docs/architecture/ce.md"],
            "decided_by": "architect",
        }
        if inside:
            record["inside"] = inside
        return record

    def layout(rule_id: str, root: str, children: list[str]) -> dict[str, Any]:
        return {
            "id": rule_id,
            "kind": "root_layout",
            "root": root,
            "allowed_children": children,
            "rationale": "Keep the cross-frame dependency route explicit.",
            "provenance": ["docs/architecture/ce.md"],
            "decided_by": "architect",
        }

    domain_path = "datamimic_ce.domains"
    domain_children = [
        component(f"DOMAIN-{index:02}", f"domain {index:02}", f"{domain_path}.item{index:02}")
        for index in range(6)
    ]
    domain_contract = {
        "schema_version": "2.1.0",
        "components": domain_children,
        "rules": [
            layout(
                "LAYOUT-DOMAINS",
                domain_path,
                [f"{domain_path}.item{index:02}" for index in range(6)],
            )
        ],
    }
    runtime = component("COMP-RUNTIME", "runtime", "datamimic_ce.engine.runtime")
    domains = component(
        "COMP-DOMAINS",
        "domains",
        domain_path,
        inside="docs/architecture/inner/domains/architecture-contract.json",
    )
    io = component("COMP-IO", "io", "datamimic_ce.engine.io")
    dsl = component("COMP-DSL", "dsl", "datamimic_ce.engine.dsl")
    runtime["requires"] = [{"component": "domains", "rationale": "Runtime uses domains."}]
    domains["requires"] = [{"component": "io", "rationale": "Domains use IO."}]
    components = [runtime, domains, io, dsl]
    root_contract = {
        "schema_version": "2.1.0",
        "components": components,
        "rules": [
            layout("LAYOUT-ROOT", "datamimic_ce", ["datamimic_ce.engine", domain_path]),
            layout(
                "LAYOUT-ENGINE",
                "datamimic_ce.engine",
                [
                    "datamimic_ce.engine.runtime",
                    "datamimic_ce.engine.io",
                    "datamimic_ce.engine.dsl",
                ],
            ),
        ],
    }
    packages = [
        *(item["packages"][0] for item in components),
        *(item["packages"][0] for item in domain_children),
    ]
    files = {
        "architecture-contract.json": json.dumps(root_contract),
        "docs/architecture/inner/domains/architecture-contract.json": json.dumps(domain_contract),
    }
    files.update({f"{package.replace('.', '/')}/__init__.py": "" for package in packages})
    root = _prepare_repo(tmp_path, files)
    config = ScanConfig(("datamimic_ce",), "datamimic_ce", "architecture-contract.json", "0" * 64)
    result, architecture = run_report(root, config=config, analyzer=observe)
    assert architecture is not None, result.diagnostics
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))
    page = render_html(
        result, observation, repository="datamimic_ce", architecture_href="architecture.json"
    ).decode()
    start = page.index('id="flow-data"')
    payload = json.loads(page[page.index(">", start) + 1 : page.index("</script>", start)])
    return page, payload


def _walk(nodes: list[dict[str, Any]]):
    for node in nodes:
        yield node
        yield from _walk(node["children"])


def _assert_normalized_graphs(diagrams: dict[str, Any]) -> None:
    graphs = [diagrams["root"], *diagrams["nested"].values()]
    checked: set[int] = set()
    while graphs:
        graph = graphs.pop()
        if id(graph) in checked:
            continue
        checked.add(id(graph))
        graphs.extend(graph.get("nested", {}).values())

        nodes = _nodes(graph)
        assert len(nodes) == len(graph["nodes"])
        containers = graph["containers"]
        entries = list(containers.values())
        entry_ids = [entry["id"] for entry in entries]
        assert len(entry_ids) == len(set(entry_ids))
        assert all(container_id == entry["id"] for container_id, entry in containers.items())

        for container_id, container in containers.items():
            parent = container["parent"]
            assert parent is None or parent in containers
            members = container["members"]
            assert len(members) == len(set(members))
            assert set(members) <= set(nodes)
            for member in members:
                placement = nodes[member].get("placement")
                if nodes[member]["kind"] == "component":
                    assert placement is not None
                if placement is not None:
                    assert placement["container"] == container_id

        for node_id, node in nodes.items():
            placement = node.get("placement")
            if placement is None or placement["container"] is None:
                continue
            container_id = placement["container"]
            assert container_id in containers
            assert node_id in containers[container_id]["members"]


def test_target_hierarchy_preserves_declarations_inventory_and_dependency_order(
    tmp_path: Path,
) -> None:
    _, payload = _target_diagram_page(tmp_path)
    diagrams = payload["explorers"]["target_diagrams"]
    _assert_normalized_graphs(diagrams)
    root = diagrams["root"]

    frames = root["containers"]
    frame = frames["layout:ROOT-LAYOUT"]
    assert frame["parent"] is None
    assert frame["scope"] == "shop"
    assert set(frame["members"]) == {
        "COMP-MODEL",
        "COMP-STORE",
        "COMP-APP",
        "COMP-RENDER",
        "COMP-CLI",
        "COMP-ARCHIVE",
        "COMP-EMPTY",
    }

    nodes = _nodes(root)
    assert {node_id for node_id, node in nodes.items() if node["kind"] == "component"} == {
        "COMP-MODEL",
        "COMP-STORE",
        "COMP-APP",
        "COMP-RENDER",
        "COMP-CLI",
        "COMP-ARCHIVE",
        "COMP-EMPTY",
    }
    placements = {
        node_id: node["placement"] for node_id, node in nodes.items() if node["kind"] == "component"
    }
    for component_id, scope in (
        ("COMP-MODEL", "shop.model"),
        ("COMP-STORE", "shop.store"),
        ("COMP-APP", "shop.app"),
        ("COMP-RENDER", "shop.render"),
        ("COMP-CLI", "shop.cli"),
        ("COMP-ARCHIVE", "shop.archive"),
        ("COMP-EMPTY", "shop.empty"),
    ):
        placement = placements[component_id]
        assert placement == {
            "status": (
                "inferred" if component_id in {"COMP-ARCHIVE", "COMP-EMPTY"} else "declared"
            ),
            "scopes": [scope],
            "container": "layout:ROOT-LAYOUT",
        }

    # These are declarations from the contract, never a projection of observed modules.
    assert set(nodes) == {
        "COMP-MODEL",
        "COMP-STORE",
        "COMP-APP",
        "COMP-RENDER",
        "COMP-CLI",
        "COMP-ARCHIVE",
        "COMP-EMPTY",
        "layout:ROOT-LAYOUT",
    }
    ranks = {
        node_id: node["dependency_rank"]
        for node_id, node in nodes.items()
        if node["kind"] == "component"
    }
    assert ranks["COMP-APP"] < ranks["COMP-ARCHIVE"]

    # The declared requires edge remains a semantic edge when cards are placed in a frame.
    requires = [edge for edge in root["edges"] if edge.get("kind") == "requires"]
    assert [(edge["source"], edge["target"]) for edge in requires] == [("COMP-APP", "COMP-ARCHIVE")]


def test_scope_placement_inventory_and_interface_states(tmp_path: Path) -> None:
    payload = _placement_page(tmp_path)
    diagrams = payload["explorers"]["target_diagrams"]
    _assert_normalized_graphs(diagrams)
    nodes = _nodes(diagrams["root"])

    assert nodes["COMP-MULTI"]["placement"] == {
        "status": "multiple",
        "scopes": ["shop.alpha", "shop.beta"],
        "container": "layout:ROOT-LAYOUT",
    }
    assert nodes["COMP-AMBIG"]["placement"] == {
        "status": "ambiguous",
        "scopes": ["shop.ambiguous.api"],
        "container": None,
    }
    assert nodes["COMP-UNSUPPORTED"]["placement"] == {
        "status": "unmapped",
        "scopes": ["shop.*"],
        "container": None,
    }
    layout_inventory = _nodes(diagrams["nested"]["layout:ROOT-LAYOUT"])
    assert "physical:shop.detached" in layout_inventory
    actual_modules = {
        node["id"] for node in _walk(payload["explorers"]["actual"]) if node["kind"] == "module"
    }
    assert "shop.orphan" in actual_modules
    assert not any("orphan" in node_id for node_id in nodes)

    target_nodes = list(_walk(payload["explorers"]["target"]))
    by_id = {node["id"]: node for node in target_nodes}
    empty_public = by_id["COMP-EMPTY-PUBLIC"]["details"]
    assert {detail["label"]: detail["value"] for detail in empty_public}["Public interface"] == (
        "Explicitly empty"
    )
    for component_id in ("COMP-ABSENT-PUBLIC", "COMP-AMBIG"):
        absent_public = by_id[component_id]["details"]
        assert {detail["label"]: detail["value"] for detail in absent_public}[
            "Public interface"
        ] == "Not declared"

    requirement = next(
        node
        for node in target_nodes
        if node["kind"] == "requires"
        and any(detail.get("value") == "Keep the API edge explicit." for detail in node["details"])
    )
    requirement_details = {detail["label"]: detail["value"] for detail in requirement["details"]}
    assert requirement_details["Through"] == "shop.store.gateway"
    assert requirement_details["Rationale"] == "Keep the API edge explicit."
    assert requirement_details["Provenance"] == "docs/architecture/shop.md"


def test_folded_null_container_component_remains_selectable_and_openable(
    tmp_path: Path,
) -> None:
    page_html, payload = _folded_single_component_page(tmp_path)
    explorers = payload["explorers"]
    target_nodes = {node["id"]: node for node in _walk(explorers["target"])}
    assert target_nodes["COMP-APP"]["kind"] == "component"
    assert target_nodes["layout:ROOT-SOLO"]["kind"] == "root_layout"

    diagrams = explorers["target_diagrams"]
    root = diagrams["root"]
    assert root["containers"] == {}
    root_nodes = _nodes(root)
    assert {node_id for node_id, node in root_nodes.items() if node["kind"] == "component"} == {
        "COMP-APP"
    }
    assert root_nodes["layout:ROOT-SOLO"]["kind"] == "root_layout"
    assert root_nodes["COMP-APP"]["placement"] == {
        "status": "declared",
        "scopes": ["shop.app"],
        "container": None,
        "folded": [
            {
                "id": "layout:ROOT-SOLO",
                "scope": "shop.app",
                "details": [{"label": "Allowed children", "value": "shop.app.orders"}],
            }
        ],
    }
    assert "layout:ROOT-SOLO" in diagrams["nested"]
    assert diagrams["nested"]["layout:ROOT-SOLO"]["owner"] == "layout:ROOT-SOLO"
    assert "physical:shop.app.orders" in _nodes(diagrams["nested"]["layout:ROOT-SOLO"])
    actual_modules = {node["id"] for node in _walk(explorers["actual"]) if node["kind"] == "module"}
    assert "shop.orphan" in actual_modules
    assert "shop.orphan" not in root_nodes
    assert "shop.orphan" not in target_nodes

    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_content(page_html, wait_until="load")
            page.get_by_role("button", name="Target").click()
            component = page.locator('.flow-nodes .node[data-target-node="COMP-APP"]')
            assert component.is_visible()
            assert component.get_attribute("data-placement-status") == "declared"

            component.click()
            package = page.locator(
                '.flow-nodes .node[data-target-node="package:COMP-APP:shop.app"]'
            )
            assert package.is_visible()
            page.locator(".flow-back").click()

            component = page.locator('.flow-nodes .node[data-target-node="COMP-APP"]')
            component.focus()
            page.keyboard.press("Enter")
            assert page.locator(
                '.flow-nodes .node[data-target-node="package:COMP-APP:shop.app"]'
            ).is_visible()
        finally:
            browser.close()


def test_ce_route_keeps_semantic_identity_across_actual_diff_target(
    tmp_path: Path,
) -> None:
    page_html, payload = _ce_nested_route_page(tmp_path)
    explorers = payload["explorers"]
    diagrams = explorers["target_diagrams"]
    root = diagrams["root"]
    root_nodes = _nodes(root)
    route_graphs = (
        (
            "COMP-RUNTIME",
            "runtime:RUNTIME-TASKS",
            {
                "runtime:RUNTIME-API",
                "runtime:RUNTIME-CONTRACTS",
                "runtime:RUNTIME-STORAGE",
                "runtime:RUNTIME-LOGGING",
                "runtime:RUNTIME-CONTEXTS",
                "runtime:RUNTIME-TASKS",
                "runtime:RUNTIME-LIFECYCLE",
                "runtime:RUNTIME-EVALUATION",
            },
        ),
        (
            "runtime:RUNTIME-TASKS",
            "runtime:tasks:TASKS-GENERATE",
            {
                "runtime:tasks:TASKS-BASE",
                "runtime:tasks:TASKS-SETUP",
                "runtime:tasks:TASKS-GENERATE",
                "runtime:tasks:TASKS-VALUES",
                "runtime:tasks:TASKS-FLOW",
                "runtime:tasks:TASKS-SOURCES",
                "runtime:tasks:TASKS-REGISTRY",
            },
        ),
        (
            "runtime:tasks:TASKS-GENERATE",
            "runtime:tasks:generate:GENERATE-WORKERS",
            {
                "runtime:tasks:generate:GENERATE-ORCHESTRATION",
                "runtime:tasks:generate:GENERATE-WORKERS",
                "runtime:tasks:generate:GENERATE-EXPORT-ORDER",
                "runtime:tasks:generate:GENERATE-POLICIES",
            },
        ),
    )
    target_nodes = {node["id"]: node for node in _walk(explorers["target"])}
    for graph_owner, expected_route_id, expected_children in route_graphs:
        graph = diagrams["nested"][graph_owner]
        component_ids = {node["id"] for node in graph["nodes"] if node["kind"] == "component"}
        assert component_ids == {graph_owner, *expected_children}
        assert target_nodes[expected_route_id]["kind"] == "component"

    assert len(route_graphs[1][2]) == 7
    assert len(route_graphs[2][2]) == 4
    assert "layout:LAYOUT-ENGINE" in diagrams["nested"]
    assert "physical:datamimic_ce.engine.runtime" in _nodes(
        diagrams["nested"]["layout:LAYOUT-ENGINE"]
    )
    assert "layout:runtime:LAYOUT-ENGINE-RUNTIME-TASKS" in diagrams["nested"]
    assert "layout:runtime:tasks:LAYOUT-ENGINE-RUNTIME-TASKS-GENERATE" in diagrams["nested"]
    workers_layout_id = "layout:runtime:tasks:generate:LAYOUT-ENGINE-RUNTIME-TASKS-GENERATE-WORKERS"
    assert workers_layout_id in diagrams["nested"]
    assert "physical:datamimic_ce.engine.runtime.tasks.generate.workers.generate_worker" in _nodes(
        diagrams["nested"][workers_layout_id]
    )
    actual_modules = {node["id"] for node in _walk(explorers["actual"]) if node["kind"] == "module"}
    assert "datamimic_ce.unlisted" in actual_modules
    assert "datamimic_ce.unlisted" not in target_nodes

    assert {node_id for node_id, node in root_nodes.items() if node["kind"] == "component"} == {
        "COMP-DSL",
        "COMP-IO",
        "COMP-RUNTIME",
    }
    assert set(root["containers"]) == {"layout:LAYOUT-ROOT", "layout:LAYOUT-ENGINE"}
    engine = root["containers"]["layout:LAYOUT-ENGINE"]
    assert engine["parent"] == "layout:LAYOUT-ROOT"
    assert set(engine["members"]) == {"COMP-DSL", "COMP-IO", "COMP-RUNTIME"}
    assert engine["members"] == ["COMP-DSL", "COMP-IO", "COMP-RUNTIME"]

    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_content(page_html, wait_until="load")
            page.get_by_role("button", name="Target").click()

            page.locator('[data-target-container-open="layout:LAYOUT-ENGINE"]').click()
            page.locator('.flow-nodes .node[data-target-node="COMP-RUNTIME"]').click()
            task_owner = page.locator('.flow-nodes .node[data-target-node="runtime:RUNTIME-TASKS"]')
            task_owner.focus()
            page.keyboard.press("Enter")
            generate_owner = page.locator(
                '.flow-nodes .node[data-target-node="runtime:tasks:TASKS-GENERATE"]'
            )
            generate_owner.click()
            workers_owner = page.locator(
                '.flow-nodes .node[data-target-node="runtime:tasks:generate:GENERATE-WORKERS"]'
            )
            workers_owner.focus()
            page.keyboard.press("Enter")
            before = page.evaluate(
                """() => ({
                  selected: document.querySelector('[data-target-node].selected')
                    ?.dataset.targetNode,
                  path: [...document.querySelectorAll('.flow-breadcrumb button')]
                    .map(node => node.textContent.trim()),
                  inspector: document.querySelector('.flow-inspector h2')?.textContent.trim(),
                  details: document.querySelector('[data-flow-details-toggle]')
                    ?.getAttribute('aria-expanded'),
                  zoom: document.querySelector('.flow-zoom-value')?.textContent.trim(),
                  scroll: document.querySelector('.flow-canvas').scrollTop,
                })"""
            )
            assert before["selected"] is None
            assert before["path"] == [
                "Target",
                "datamimic_ce.engine",
                "runtime",
                "tasks",
                "generate",
                "workers",
            ]
            assert before["inspector"] == "workers"
            assert before["details"] == "true"
            assert before["zoom"] == "100%"
            assert before["scroll"] == 0

            page.get_by_role("button", name="Actual", exact=True).click()
            page.get_by_role("button", name="Diff", exact=True).click()
            page.get_by_role("button", name="Target", exact=True).click()
            after = page.evaluate(
                """() => ({
                  selected: document.querySelector('[data-target-node].selected')
                    ?.dataset.targetNode,
                  path: [...document.querySelectorAll('.flow-breadcrumb button')]
                    .map(node => node.textContent.trim()),
                  inspector: document.querySelector('.flow-inspector h2')?.textContent.trim(),
                  details: document.querySelector('[data-flow-details-toggle]')
                    ?.getAttribute('aria-expanded'),
                  zoom: document.querySelector('.flow-zoom-value')?.textContent.trim(),
                  scroll: document.querySelector('.flow-canvas').scrollTop,
                })"""
            )
            assert after == before
        finally:
            browser.close()


def test_cross_frame_dependency_chain_uses_graph_global_render_order(tmp_path: Path) -> None:
    page_html, payload = _cross_frame_domains_page(tmp_path)
    root = payload["explorers"]["target_diagrams"]["root"]
    nodes = _nodes(root)
    assert nodes["COMP-RUNTIME"]["dependency_rank"] < nodes["COMP-DOMAINS"]["dependency_rank"]
    assert nodes["COMP-DOMAINS"]["dependency_rank"] < nodes["COMP-IO"]["dependency_rank"]
    assert root["containers"]["layout:LAYOUT-ENGINE"]["members"] == [
        "COMP-DSL",
        "COMP-IO",
        "COMP-RUNTIME",
    ]
    assert {
        (edge["source"], edge["target"]) for edge in root["edges"] if edge["kind"] == "requires"
    } == {("COMP-RUNTIME", "COMP-DOMAINS"), ("COMP-DOMAINS", "COMP-IO")}

    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_content(page_html, wait_until="load")
            page.get_by_role("button", name="Target", exact=True).click()
            card_centers = page.evaluate(
                """() => Object.fromEntries(
                  ['COMP-RUNTIME', 'COMP-DOMAINS', 'COMP-IO'].map(id => {
                    const box = document.querySelector(`[data-target-node="${id}"]`)
                      .getBoundingClientRect();
                    return [id, box.top + box.height / 2];
                  })
                )"""
            )
            assert card_centers["COMP-RUNTIME"] < card_centers["COMP-DOMAINS"]
            assert card_centers["COMP-DOMAINS"] < card_centers["COMP-IO"]
        finally:
            browser.close()


def test_initial_narrow_canvas_keeps_unframed_lane_outside_engine_frame(
    tmp_path: Path,
) -> None:
    page_html, _ = _cross_frame_domains_page(tmp_path)
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_content(page_html, wait_until="load")
            canvas = page.locator(".flow-canvas")
            canvas.evaluate(
                "node => { node.style.flex = '0 0 552px'; node.style.width = '552px'; }"
            )
            page.get_by_role("button", name="Target", exact=True).click()
            assert canvas.evaluate("node => node.clientWidth") == 550

            geometry = page.evaluate(
                """() => {
                  const box = selector => {
                    const rect = document.querySelector(selector).getBoundingClientRect();
                    return {left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom};
                  };
                  const frameGroup = document.querySelector(
                    '[data-target-container="layout:LAYOUT-ENGINE"]'
                  );
                  const frame = frameGroup.previousElementSibling
                    .querySelector('.target-frame');
                  const rect = frame.getBoundingClientRect();
                  const cards = Object.fromEntries(
                    ['COMP-RUNTIME', 'COMP-DOMAINS', 'COMP-IO'].map(id => [
                      id, box(`[data-target-node="${id}"]`),
                    ])
                  );
                  return {
                    frame: {
                      left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom,
                    },
                    cards,
                  };
                }"""
            )

            runtime = geometry["cards"]["COMP-RUNTIME"]
            domains = geometry["cards"]["COMP-DOMAINS"]
            io = geometry["cards"]["COMP-IO"]
            frame = geometry["frame"]
            assert runtime["left"] >= frame["left"] and runtime["right"] <= frame["right"]
            assert runtime["top"] >= frame["top"] and runtime["bottom"] <= frame["bottom"]
            assert io["left"] >= frame["left"] and io["right"] <= frame["right"]
            assert io["top"] >= frame["top"] and io["bottom"] <= frame["bottom"]
            centers = {
                component_id: rect["top"] + (rect["bottom"] - rect["top"]) / 2
                for component_id, rect in geometry["cards"].items()
            }
            assert centers["COMP-RUNTIME"] < centers["COMP-DOMAINS"]
            assert centers["COMP-DOMAINS"] < centers["COMP-IO"]
            assert (
                domains["right"] <= frame["left"]
                or domains["left"] >= frame["right"]
                or domains["bottom"] <= frame["top"]
                or domains["top"] >= frame["bottom"]
            )
        finally:
            browser.close()


def test_target_resize_preserves_open_graph_card_anchor(tmp_path: Path) -> None:
    page_html, payload = _cross_frame_domains_page(tmp_path)
    diagrams = payload["explorers"]["target_diagrams"]
    domain_graph = diagrams["nested"]["COMP-DOMAINS"]
    domain_ids = {node["id"] for node in domain_graph["nodes"] if node["kind"] == "component"}
    assert domain_ids == {"COMP-DOMAINS", *(f"domains:DOMAIN-{index:02}" for index in range(6))}

    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_default_timeout(2500)
            page.set_content(page_html, wait_until="load")
            page.get_by_role("button", name="Target", exact=True).click()
            page.locator('[data-target-node="COMP-DOMAINS"]').click()
            target = page.locator('[data-target-node="domains:DOMAIN-04"]')

            def anchor_state() -> dict[str, Any]:
                return target.evaluate(
                    """node => {
                      const box = node.getBoundingClientRect();
                      const canvas = document.querySelector('.flow-canvas');
                      return {
                        transform: node.getAttribute('transform'),
                        x: box.left,
                        y: box.top,
                        path: [...document.querySelectorAll('.flow-breadcrumb button')]
                          .map(button => button.textContent.trim()),
                        inspector: document.querySelector('.flow-inspector h2')
                          ?.textContent.trim(),
                        zoom: document.querySelector('.flow-zoom-value')?.textContent.trim(),
                        scrollLeft: canvas.scrollLeft,
                        scrollTop: canvas.scrollTop,
                      };
                    }"""
                )

            before = anchor_state()
            assert before["path"] == ["Target", "domains"]
            assert before["inspector"] == "domains"
            assert before["zoom"] == "100%"
            page.set_viewport_size({"width": 1856, "height": 1336})
            page.wait_for_timeout(100)
            after = anchor_state()
            assert after["path"] == before["path"]
            assert after["inspector"] == before["inspector"]
            assert after["zoom"] == before["zoom"]
            assert after["scrollLeft"] == before["scrollLeft"]
            assert after["scrollTop"] == before["scrollTop"]
            assert after["transform"] == before["transform"]
            assert abs(after["x"] - before["x"]) <= 1
            assert abs(after["y"] - before["y"]) <= 1
        finally:
            browser.close()


def test_parent_with_inside_components_folds_only_current_graph_frames(
    tmp_path: Path,
) -> None:
    payload = _parent_with_inside_components_page(tmp_path)
    diagrams = payload["explorers"]["target_diagrams"]
    _assert_normalized_graphs(diagrams)

    root = diagrams["root"]
    root_nodes = _nodes(root)
    assert set(root["containers"]) == {"layout:ROOT-LAYOUT", "layout:LAYOUT-ENGINE"}
    engine = root["containers"]["layout:LAYOUT-ENGINE"]
    assert engine["parent"] == "layout:ROOT-LAYOUT"
    assert engine["scope"] == "shop.engine"
    assert engine["members"] == ["COMP-DSL", "COMP-IO", "COMP-RUNTIME"]
    assert {
        (
            root_nodes[node_id]["placement"]["status"],
            tuple(root_nodes[node_id]["placement"]["scopes"]),
            root_nodes[node_id]["placement"]["container"],
        )
        for node_id in engine["members"]
    } == {
        ("declared", ("shop.engine.dsl",), "layout:LAYOUT-ENGINE"),
        ("declared", ("shop.engine.io",), "layout:LAYOUT-ENGINE"),
        ("declared", ("shop.engine.runtime",), "layout:LAYOUT-ENGINE"),
    }
    folded_layout_ids = {
        "layout:LAYOUT-ENGINE-DSL",
        "layout:LAYOUT-ENGINE-IO",
        "layout:LAYOUT-ENGINE-RUNTIME",
    }
    assert folded_layout_ids.isdisjoint(root["containers"])

    target_nodes = {node["id"]: node for node in _walk(payload["explorers"]["target"])}
    for layout_id, scope, allowed_children in (
        (
            "layout:LAYOUT-ENGINE-DSL",
            "shop.engine.dsl",
            {"shop.engine.dsl.leaf"},
        ),
        (
            "layout:LAYOUT-ENGINE-IO",
            "shop.engine.io",
            {"shop.engine.io.leaf"},
        ),
        (
            "layout:LAYOUT-ENGINE-RUNTIME",
            "shop.engine.runtime",
            {"shop.engine.runtime.compat", "shop.engine.runtime.leaf"},
        ),
    ):
        declaration = target_nodes[layout_id]
        assert declaration["kind"] == "root_layout"
        assert declaration["label"] == scope
        details = {detail["label"]: detail["value"] for detail in declaration["details"]}
        assert set(details["Allowed children"].split(", ")) == allowed_children
        navigation = diagrams["nested"][layout_id]
        assert navigation["owner"] == layout_id

    folded_runtime = diagrams["nested"]["layout:LAYOUT-ENGINE-RUNTIME"]
    assert "physical:shop.engine.runtime.compat" in _nodes(folded_runtime)
    assert {
        detail["value"]
        for detail in target_nodes["COMP-RUNTIME"]["details"]
        if detail["label"] == "Responsibility"
    } == {"Own Runtime behavior."}

    runtime = diagrams["nested"]["COMP-RUNTIME"]
    assert len(runtime["containers"]) == 1
    runtime_frame_id, runtime_frame = next(iter(runtime["containers"].items()))
    assert runtime_frame["scope"] == "shop.engine.runtime"
    runtime_nodes = _nodes(runtime)
    runtime_components = {
        node_id: node for node_id, node in runtime_nodes.items() if node["kind"] == "component"
    }
    assert set(runtime_components) == {
        "COMP-RUNTIME",
        "Runtime:COMP-RUNTIME-TASKS",
        "Runtime:COMP-RUNTIME-WORKERS",
    }
    assert runtime_components["COMP-RUNTIME"]["label"] == "Runtime"
    runtime_child_ids = {
        "Runtime:COMP-RUNTIME-TASKS",
        "Runtime:COMP-RUNTIME-WORKERS",
    }
    assert {runtime_components[node_id]["label"] for node_id in runtime_child_ids} == {
        "tasks",
        "workers",
    }
    assert set(runtime_frame["members"]) == runtime_child_ids
    assert "COMP-RUNTIME" not in runtime_frame["members"]
    assert "physical:shop.engine.runtime.metadata" in _nodes(diagrams["nested"][runtime_frame_id])
    assert not {"DSL", "IO"} & {node["label"] for node in runtime_nodes.values()}


def test_cycles_keep_self_loop_and_dependents_in_unranked_band(tmp_path: Path) -> None:
    _, payload = _cycle_page(tmp_path)
    root = payload["explorers"]["target_diagrams"]["root"]
    nodes = _nodes(root)
    assert {
        node_id
        for node_id in ("COMP-APP", "COMP-ARCHIVE", "COMP-EMPTY", "COMP-STORE")
        if nodes[node_id]["dependency_rank"] is None
    } == {"COMP-APP", "COMP-ARCHIVE", "COMP-EMPTY", "COMP-STORE"}
    requires = {
        (edge["source"], edge["target"]) for edge in root["edges"] if edge.get("kind") == "requires"
    }
    assert requires == {
        ("COMP-APP", "COMP-ARCHIVE"),
        ("COMP-ARCHIVE", "COMP-EMPTY"),
        ("COMP-EMPTY", "COMP-ARCHIVE"),
        ("COMP-STORE", "COMP-STORE"),
    }


def test_cycle_unresolved_band_is_visible_in_target_browser(tmp_path: Path) -> None:
    page_html, _ = _cycle_page(tmp_path)
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        browser_page = browser.new_page(viewport={"width": 1440, "height": 1000})
        browser_page.set_default_timeout(2500)
        browser_page.set_content(page_html, wait_until="networkidle")
        browser_page.get_by_role("button", name="Target").click()
        unresolved = browser_page.get_by_text(
            "Dependency order unresolved: cycle or dependency on a cycle.", exact=True
        )
        assert unresolved.is_visible()
        browser.close()


@pytest.mark.parametrize(("width", "height"), [(1440, 1000), (1856, 1336)])
def test_target_hierarchy_is_readable_and_details_toggle_preserves_state(
    tmp_path: Path, width: int, height: int
) -> None:
    page_html, _ = _target_diagram_page(tmp_path)
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
        page.set_default_timeout(2500)
        page.set_content(page_html, wait_until="networkidle")
        page.get_by_role("button", name="Target").click()
        toggle = page.locator("[data-flow-details-toggle]")
        assert toggle.get_attribute("aria-expanded") == "false"
        assert toggle.get_attribute("aria-controls")
        assert page.locator(".flow-zoom-value").inner_text() == "100%"

        page.locator('[data-target-node="COMP-APP"]').click()
        assert (
            page.locator('[data-target-node="COMP-APP"]').get_attribute("data-placement-status")
            == "declared"
        )

        before = page.evaluate(
            """() => ({
              path: [...document.querySelectorAll('.flow-breadcrumb button')]
                .map(x => x.textContent.trim()),
              selected: document.querySelector('[data-target-node].selected')?.dataset.targetNode,
              inspector: document.querySelector('.flow-inspector h2')?.textContent.trim(),
              scroll: document.querySelector('.flow-canvas').scrollTop,
              zoom: document.querySelector('.flow-zoom-value').textContent,
              details: document.querySelector('[data-flow-details-toggle]')
                ?.getAttribute('aria-expanded'),
            })"""
        )
        assert before["selected"] is None
        assert before["path"] == ["Target", "app"]
        assert before["inspector"] == "app"
        assert before["details"] == "true"
        assert before["zoom"] == "100%"
        expanded_before = toggle.get_attribute("aria-expanded")
        toggle.focus()
        page.keyboard.press("Enter")
        expanded_after = toggle.get_attribute("aria-expanded")
        assert expanded_after != expanded_before
        assert page.locator(".flow-inspector").is_visible() == (expanded_after == "true")
        toggle.focus()
        page.keyboard.press("Enter")
        assert toggle.get_attribute("aria-expanded") == expanded_before
        after = page.evaluate(
            """() => ({
              path: [...document.querySelectorAll('.flow-breadcrumb button')]
                .map(x => x.textContent.trim()),
              selected: document.querySelector('[data-target-node].selected')?.dataset.targetNode,
              inspector: document.querySelector('.flow-inspector h2')?.textContent.trim(),
              scroll: document.querySelector('.flow-canvas').scrollTop,
              zoom: document.querySelector('.flow-zoom-value').textContent,
              details: document.querySelector('[data-flow-details-toggle]')
                ?.getAttribute('aria-expanded'),
            })"""
        )
        assert after == before

        name_sizes = page.locator(".flow-nodes .target-label").evaluate_all(
            "nodes => nodes.map(node => parseFloat(getComputedStyle(node).fontSize))"
        )
        responsibility_sizes = page.locator(".flow-nodes .target-responsibility").evaluate_all(
            "nodes => nodes.map(node => parseFloat(getComputedStyle(node).fontSize))"
        )
        assert name_sizes and min(name_sizes) >= 14
        assert responsibility_sizes and min(responsibility_sizes) >= 12
        for selector, minimum in (
            (".flow-nodes .target-label", 14),
            (".flow-nodes .target-responsibility", 12),
        ):
            effective_sizes = page.locator(selector).evaluate_all(
                """nodes => nodes.map(node => {
                  const matrix = node.getScreenCTM();
                  const bounds = node.getBoundingClientRect();
                  return {
                    effectiveFontPx: parseFloat(getComputedStyle(node).fontSize)
                      * Math.hypot(matrix.c, matrix.d),
                    width: bounds.width,
                    height: bounds.height,
                  };
                })"""
            )
            assert effective_sizes
            assert min(item["effectiveFontPx"] for item in effective_sizes) >= minimum
            assert all(item["width"] > 0 and item["height"] > 0 for item in effective_sizes)
        assert page.locator("[data-target-container='layout:ROOT-LAYOUT']").count() == 1
        assert page.locator("[data-target-container-open='layout:ROOT-LAYOUT']").count() == 1
        browser.close()

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

from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.render.html import render_html
from fixtures.architecture_demo import CATALOG
from fixtures.demo_catalog_support import FIXTURE_DIR


def _nodes(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {node["id"]: node for node in graph["nodes"]}


def _cycle_page(
    tmp_path: Path,
    *,
    wrapped_rank_count: int = 0,
) -> tuple[str, dict[str, Any]]:
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
    files = dict(tour.files)
    if wrapped_rank_count:
        provider = {
            **components["COMP-MODEL"],
            "id": "COMP-RANK-PROVIDER",
            "label": "rank-provider",
            "packages": ["shop.rank.provider"],
            "namespace": "shop.rank.provider",
            "public": [],
        }
        consumers = []
        for index in range(wrapped_rank_count):
            package = f"shop.rank.consumer{index:02}"
            consumer = {
                **components["COMP-MODEL"],
                "id": f"COMP-RANK-{index:02}",
                "label": f"ranked {index:02}",
                "packages": [package],
                "namespace": package,
                "public": [],
                "requires": [
                    {
                        "component": "rank-provider",
                        "rationale": "Keep all consumer cards in the same rank.",
                    }
                ],
            }
            consumers.append(consumer)
        contract["components"].extend([provider, *consumers])
        root_layout["allowed_children"].append("shop.rank")
        rank_packages = ["shop.rank", "shop.rank.provider"] + [
            f"shop.rank.consumer{index:02}" for index in range(wrapped_rank_count)
        ]
        files.update({f"{package.replace('.', '/')}/__init__.py": "" for package in rank_packages})
    nested = (FIXTURE_DIR / "shop/store/architecture-contract.json").read_text()
    files.update(
        {
            "architecture-contract.json": json.dumps(contract),
            "shop/store/architecture-contract.json": nested,
        }
    )
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


def _placement_page_data(
    tmp_path: Path,
    *,
    neutral_labels: bool = False,
) -> tuple[str, dict[str, Any]]:
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

    labels = (
        {
            "COMP-MULTI": "Orders API",
            "COMP-AMBIG": "Catalog API",
            "COMP-UNSUPPORTED": "Import Adapter",
        }
        if neutral_labels
        else {
            "COMP-MULTI": "multi",
            "COMP-AMBIG": "ambiguous",
            "COMP-UNSUPPORTED": "wildcard",
        }
    )
    contract["components"].extend(
        [
            component("COMP-MULTI", labels["COMP-MULTI"], ["shop.alpha", "shop.beta"], public=[]),
            component("COMP-AMBIG", labels["COMP-AMBIG"], ["shop.ambiguous.api"], public=None),
            component("COMP-UNSUPPORTED", labels["COMP-UNSUPPORTED"], ["shop.*"], public=[]),
        ]
    )
    if neutral_labels:
        ambiguous = next(item for item in contract["components"] if item["id"] == "COMP-AMBIG")
        ambiguous["responsibilities"] = ['Literal <script>alert("no")</script> & text.']
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
    payload = json.loads(page[page.index(">", start) + 1 : page.index("</script>", start)])
    return page, payload


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


def _ce_nested_route_page(
    tmp_path: Path,
    *,
    include_worker_module_target: bool = False,
    include_domain_route: bool = False,
    include_overlapping_actual_modules: bool = False,
    include_engine_owner: bool = False,
    include_root_compat_target: bool = False,
    include_scoped_diff_controls: bool = False,
    include_overlapping_worker_owner: bool = False,
) -> tuple[str, dict[str, Any]]:
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
    if include_engine_owner:
        root_owners.append(component("COMP-ENGINE", "engine", "datamimic_ce.engine"))
    if include_root_compat_target:
        root_owners.append(component("COMP-PYTHON-COMPAT", "python_compat", "datamimic_ce"))
    if include_domain_route:
        root_owners.append(component("COMP-DOMAINS", "domains", "datamimic_ce.domains"))
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
    if include_scoped_diff_controls:
        worker_scope = f"{generate_path}.workers"
        generate_contract["components"][1]["public"] = [f"{worker_scope}:make"]
        generate_contract["rules"].append(
            {
                "id": "WORKER-TYPES",
                "kind": "boundary_types",
                "source": worker_scope,
                "rationale": "Keep worker inputs and results explicit.",
                "provenance": ["docs/architecture/ce.md"],
                "decided_by": "architect",
            }
        )
    if include_overlapping_worker_owner:
        generate_contract["components"].append(
            component("GENERATE-OTHER-WORKERS", "other workers", f"{generate_path}.workers")
        )
    if include_worker_module_target:
        generate_contract["declarations"] = {
            "modules": [
                {
                    "path": "datamimic_ce/engine/runtime/tasks/generate/workers/generate_worker.py",
                    "responsibility": "Own worker page generation.",
                },
                {
                    "path": "datamimic_ce/engine/runtime/tasks/generate/workers/single/one.py",
                    "responsibility": "Own the single physical module.",
                },
            ]
        }
    root_contract = {
        "schema_version": "2.1.0",
        "components": root_owners,
        "rules": [
            layout(
                "LAYOUT-ROOT",
                "datamimic_ce",
                [
                    "datamimic_ce.engine",
                    *(["datamimic_ce.domains"] if include_domain_route else []),
                ],
            ),
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
    if include_root_compat_target:
        root_contract["declarations"] = {
            "modules": [
                {
                    "path": "datamimic_ce/_compat.py",
                    "responsibility": "This module provides compatibility helpers.",
                }
            ]
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
    if include_worker_module_target:
        files.update(
            {
                "datamimic_ce/engine/runtime/tasks/generate/workers/generate_worker.py": (
                    "class GenerateWorker: pass\n"
                ),
                "datamimic_ce/engine/runtime/tasks/generate/workers/single/one.py": ("VALUE = 1\n"),
            }
        )
    if include_overlapping_actual_modules:
        files.update(
            {
                "datamimic_ce/engine/runtime/tasks/values/variable/__init__.py": "",
                "datamimic_ce/engine/runtime/tasks/values/variable/task.py": "VALUE = 1\n",
            }
        )
    if include_domain_route:
        files["datamimic_ce/domains/domain_core.py"] = "VALUE = 1\n"
    if include_root_compat_target:
        files["datamimic_ce/_compat.py"] = "VALUE = 1\n"
    files.update({f"{package.replace('.', '/')}/__init__.py": "" for package in packages})
    if include_scoped_diff_controls:
        files[f"{generate_path.replace('.', '/')}/workers/__init__.py"] = (
            "from external import Value\n\ndef make(value: object) -> Value: return value\n"
        )
        files.update(
            {
                f"{generate_path.replace('.', '/')}/workers/{name}.py": "VALUE = 1\n"
                for name in (
                    "generate_worker",
                    "multiprocessing_generate_worker",
                    "ray_generate_worker",
                )
            }
        )
        files[f"{generate_path.replace('.', '/')}/policies/policy.py"] = "VALUE = 1\n"
        files.update(
            {
                f"datamimic_ce/engine/runtime/storage/extra_{index}.py": "VALUE = 1\n"
                for index in range(470)
            }
        )
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


def _cross_frame_domains_page(
    tmp_path: Path,
    *,
    observed_cross_frame_edge: bool = False,
    incoming_engine_requirements: bool = False,
    engine_scope: str = "datamimic_ce.engine",
) -> tuple[str, dict[str, Any]]:
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
    runtime = component("COMP-RUNTIME", "runtime", f"{engine_scope}.runtime")
    domains = component(
        "COMP-DOMAINS",
        "domains",
        domain_path,
        inside="docs/architecture/inner/domains/architecture-contract.json",
    )
    io = component("COMP-IO", "io", f"{engine_scope}.io")
    dsl = component("COMP-DSL", "dsl", f"{engine_scope}.dsl")
    external_dependencies = []
    if incoming_engine_requirements:
        for component_id, label in (
            ("COMP-AUTHORING", "authoring"),
            ("COMP-RESOURCES", "resources"),
        ):
            dependency = component(component_id, label, f"datamimic_ce.{label}")
            dependency["requires"] = [
                {"component": "runtime", "rationale": f"{label} uses runtime."}
            ]
            external_dependencies.append(dependency)
    runtime["requires"] = [{"component": "domains", "rationale": "Runtime uses domains."}]
    domains["requires"] = [{"component": "io", "rationale": "Domains use IO."}]
    components = [runtime, domains, io, dsl, *external_dependencies]
    root_contract = {
        "schema_version": "2.1.0",
        "components": components,
        "rules": [
            layout(
                "LAYOUT-ROOT",
                "datamimic_ce",
                [
                    engine_scope,
                    domain_path,
                    *(item["packages"][0] for item in external_dependencies),
                ],
            ),
            layout(
                "LAYOUT-ENGINE",
                engine_scope,
                [
                    f"{engine_scope}.runtime",
                    f"{engine_scope}.io",
                    f"{engine_scope}.dsl",
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
    if observed_cross_frame_edge:
        files["datamimic_ce/engine/runtime/__init__.py"] = "import datamimic_ce.domains\n"
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
    _, payload = _placement_page_data(tmp_path)
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


@pytest.mark.parametrize(
    ("node_id", "label", "status", "scopes", "container"),
    [
        (
            "COMP-MULTI",
            "Orders API",
            "multiple",
            ("shop.alpha", "shop.beta"),
            "layout:ROOT-LAYOUT",
        ),
        (
            "COMP-AMBIG",
            "Catalog API",
            "ambiguous",
            ("shop.ambiguous.api",),
            None,
        ),
        (
            "COMP-UNSUPPORTED",
            "Import Adapter",
            "unmapped",
            ("shop.*",),
            None,
        ),
    ],
)
def test_selected_placement_status_and_scope_are_visible_in_details(
    tmp_path: Path,
    node_id: str,
    label: str,
    status: str,
    scopes: tuple[str, ...],
    container: str | None,
) -> None:
    page_html, _ = _placement_page_data(tmp_path, neutral_labels=True)
    assert not any(token in label.casefold() for token in ("ambiguous", "multiple", "unmapped"))
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_content(page_html, wait_until="networkidle")
            page.get_by_role("button", name="Target").click()
            card = page.locator(f'.flow-nodes .node[data-target-node="{node_id}"]')
            assert card.is_visible()
            assert card.get_attribute("data-placement-status") == status
            card.click()
            if page.locator("[data-flow-details-toggle]").get_attribute("aria-expanded") != "true":
                page.locator("[data-flow-details-toggle]").click()

            inspector = page.locator(".flow-inspector")
            assert inspector.is_visible()
            text = inspector.inner_text()
            assert label in text
            assert "Placement" in text
            assert status in text
            assert "Scopes" in text
            for scope in scopes:
                assert scope in text
            if container is None:
                assert "Unplaced" in text
            else:
                assert container in text
            if node_id == "COMP-AMBIG":
                literal = 'Literal <script>alert("no")</script> & text.'
                assert literal in text
                assert inspector.locator("script").count() == 0
                assert inspector.locator("img").count() == 0
        finally:
            browser.close()


def test_selected_component_details_retain_folded_layout_context(tmp_path: Path) -> None:
    page_html, payload = _folded_single_component_page(tmp_path)
    diagrams = payload["explorers"]["target_diagrams"]
    assert diagrams["root"]["containers"] == {}
    app = _nodes(diagrams["root"])["COMP-APP"]
    assert app["placement"]["container"] is None
    assert app["placement"]["folded"] == [
        {
            "id": "layout:ROOT-SOLO",
            "scope": "shop.app",
            "details": [{"label": "Allowed children", "value": "shop.app.orders"}],
        }
    ]
    assert diagrams["nested"]["COMP-APP"]["containers"] == {}
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_content(page_html, wait_until="networkidle")
            page.get_by_role("button", name="Target").click()
            page.locator('.flow-nodes .node[data-target-node="COMP-APP"]').click()
            page.locator(".flow-open-selected").click()
            if page.locator("[data-flow-details-toggle]").get_attribute("aria-expanded") != "true":
                page.locator("[data-flow-details-toggle]").click()
            inspector = page.locator(".flow-inspector")
            assert inspector.is_visible()
            text = inspector.inner_text()
            assert [
                item.text_content().strip()
                for item in page.locator(".flow-breadcrumb button").all()
            ] == ["Target", "app"]
            for value in (
                "layout:ROOT-SOLO",
                "shop.app",
                "Allowed children",
                "shop.app.orders",
                "Public interface",
                "shop.app.orders:place_order",
                "Provenance",
                "docs/architecture/shop.md",
            ):
                assert value in text
            assert "no declared frame" not in text.casefold()
        finally:
            browser.close()


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
            page.locator(".flow-open-selected").click()
            page.locator(".flow-details-toggle").click()
            package = page.locator('[data-target-detail="package:COMP-APP:shop.app"]')
            assert package.is_visible()
            page.locator(".flow-back").click()

            component = page.locator('.flow-nodes .node[data-target-node="COMP-APP"]')
            component.focus()
            page.keyboard.press("Enter")
            assert page.locator('[data-target-detail="package:COMP-APP:shop.app"]').is_visible()
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
            page.locator("[data-flow-details-toggle]").click()

            page.locator('[data-target-container="layout:LAYOUT-ENGINE"]').click()
            page.locator(".flow-open-selected").click()
            page.locator('.flow-nodes .node[data-target-node="COMP-RUNTIME"]').click()
            page.locator(".flow-open-selected").click()
            task_owner = page.locator('.flow-nodes .node[data-target-node="runtime:RUNTIME-TASKS"]')
            task_owner.focus()
            page.keyboard.press("Enter")
            generate_owner = page.locator(
                '.flow-nodes .node[data-target-node="runtime:tasks:TASKS-GENERATE"]'
            )
            generate_owner.click()
            page.locator(".flow-open-selected").click()
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


def test_diagram_keeps_exact_nested_component_responsibilities(tmp_path: Path) -> None:
    page_html, payload = _ce_nested_route_page(tmp_path)
    expected = [
        ("COMP-RUNTIME", "api", "runtime:RUNTIME-API", "Own api behavior."),
        ("COMP-RUNTIME", "tasks", "runtime:RUNTIME-TASKS", "Own tasks behavior."),
        (
            "runtime:RUNTIME-TASKS",
            "generate",
            "runtime:tasks:TASKS-GENERATE",
            "Own generate behavior.",
        ),
        (
            "runtime:tasks:TASKS-GENERATE",
            "workers",
            "runtime:tasks:generate:GENERATE-WORKERS",
            "Own workers behavior.",
        ),
    ]
    target_ids = {node["id"] for node in _walk(payload["explorers"]["target"])}
    assert {declaration_id for _, _, declaration_id, _ in expected} <= target_ids

    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_content(page_html, wait_until="load")
            details = page.locator("[data-flow-details-toggle]")
            details.click()
            page.locator('.flow-nodes .node[data-label="runtime"]').click()
            page.locator(".flow-open-selected").click()
            for index, (_, label, _, sentence) in enumerate(expected):
                card = page.locator(f'.flow-nodes .node[data-label="{label}"]')
                card.click()
                assert sentence in card.locator(".diagram-responsibility").text_content()
                if index in {1, 2}:
                    page.locator(".flow-open-selected").click()
        finally:
            browser.close()


def test_diagram_worker_module_uses_its_exact_target_responsibility(tmp_path: Path) -> None:
    page_html, payload = _ce_nested_route_page(tmp_path, include_worker_module_target=True)
    target = next(
        node
        for node in _walk(payload["explorers"]["target"])
        if node["kind"] == "module_target"
        and any(
            detail["label"] == "File"
            and detail["value"]
            == "datamimic_ce/engine/runtime/tasks/generate/workers/generate_worker.py"
            for detail in node["details"]
        )
    )
    module_id = "datamimic_ce.engine.runtime.tasks.generate.workers.generate_worker"
    assert target["id"] == "MODULE-TARGET-9b62f66da7603113"
    assert (
        next(detail["value"] for detail in target["details"] if detail["label"] == "File")
        == "datamimic_ce/engine/runtime/tasks/generate/workers/generate_worker.py"
    )
    assert isinstance(payload["modules"][module_id], dict)

    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_content(page_html, wait_until="load")
            page.locator("[data-flow-details-toggle]").click()
            for label in ("runtime", "tasks", "generate", "workers"):
                page.locator(f'.flow-nodes .node[data-label="{label}"]').press("Enter")
            card = page.locator(f'.flow-nodes .node[data-label="{module_id}"]')
            assert card.is_visible()
            assert card.locator(".diagram-responsibility").count() == 1
            assert (
                "Own worker page generation."
                in card.locator(".diagram-responsibility").text_content()
            )
            card.press("Space")
            assert (
                page.locator(".flow-selected-responsibility")
                .get_by_text("Own worker page generation.", exact=True)
                .is_visible()
            )
            assert (
                page.locator(".flow-selected-responsibility").get_attribute("data-declaration-id")
                == target["id"]
            )
            assert (
                page.locator(".flow-selected-responsibility")
                .get_by_text("No matching entry in this view", exact=False)
                .count()
                == 0
            )
        finally:
            browser.close()


def test_single_module_physical_folder_does_not_inherit_module_responsibility(
    tmp_path: Path,
) -> None:
    page_html, _ = _ce_nested_route_page(tmp_path, include_worker_module_target=True)
    folder_id = "datamimic_ce.engine.runtime.tasks.generate.workers.single"
    module_id = f"{folder_id}.one"
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_content(page_html, wait_until="load")
            for label in ("runtime", "tasks", "generate", "workers"):
                page.locator(f'.flow-nodes .node[data-label="{label}"]').press("Enter")
            folder = page.locator(f'.flow-nodes .node[data-label="{folder_id}"]')
            assert folder.is_visible()
            assert folder.locator(".diagram-responsibility").count() == 0
            folder.press("Enter")
            module = page.locator(f'.flow-nodes .node[data-label="{module_id}"]')
            assert module.is_visible()
            assert (
                "Own the single physical module."
                in module.locator(".diagram-responsibility").text_content()
            )
        finally:
            browser.close()


def test_selected_generate_maps_to_its_exact_actual_module(tmp_path: Path) -> None:
    page_html, payload = _ce_nested_route_page(tmp_path, include_overlapping_actual_modules=True)
    generate_id = "datamimic_ce.engine.runtime.tasks.generate"
    wrong_id = "datamimic_ce.engine.runtime.tasks.values.variable.task"
    actual_ids = {node["id"] for node in _walk(payload["explorers"]["actual"])}
    assert generate_id in actual_ids
    assert wrong_id in actual_ids

    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_content(page_html, wait_until="load")
            for label in ("runtime", "tasks"):
                page.locator(f'.flow-nodes .node[data-label="{label}"]').press("Enter")
            page.locator('.flow-nodes .node[data-label="generate"]').press("Space")
            page.locator('[data-flow-view="actual"]').click()
            result = page.evaluate(
                """() => ({
                  crumb: [...document.querySelectorAll('.flow-breadcrumb button')]
                    .map(node => node.textContent.trim()),
                  details: [...document.querySelectorAll(
                    '.flow-projection-details dd'
                  )].map(node => node.textContent.trim()),
                })"""
            )
            assert result["crumb"] == [
                "Actual",
                "datamimic_ce",
                "engine",
                "runtime",
                "tasks",
                "generate",
            ]
            assert "datamimic_ce/engine/runtime/tasks/generate/__init__.py" in result["details"]
            assert wrong_id not in result["crumb"]
        finally:
            browser.close()


def test_target_runtime_switches_to_its_observed_diagram_frame(tmp_path: Path) -> None:
    page_html, _ = _ce_nested_route_page(tmp_path)
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_content(page_html, wait_until="load")
            page.locator('[data-flow-view="target"]').click()
            runtime = page.locator('[data-target-node="COMP-RUNTIME"]')
            runtime.click()
            page.locator(".flow-open-selected").click()
            assert page.locator(".flow-breadcrumb").inner_text().endswith("runtime")
            page.locator('[data-flow-view="diagram"]').click()
            assert page.locator(
                '.flow-nodes .node[data-label="runtime"][aria-pressed="true"]'
            ).is_visible()
            assert (
                page.locator(".flow-selected-responsibility").get_attribute("data-declaration-id")
                == "COMP-RUNTIME"
            )
        finally:
            browser.close()


def test_actual_domains_cannot_restore_an_old_diagram_route(tmp_path: Path) -> None:
    page_html, payload = _ce_nested_route_page(tmp_path, include_domain_route=True)
    actual_ids = {node["id"] for node in _walk(payload["explorers"]["actual"])}
    assert "datamimic_ce.domains" in actual_ids
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_content(page_html, wait_until="load")
            for label in ("runtime", "tasks"):
                page.locator(f'.flow-nodes .node[data-label="{label}"]').press("Enter")
            assert page.locator(".flow-breadcrumb").inner_text().endswith("tasks")
            page.locator('[data-flow-view="actual"]').click()
            page.locator(".flow-breadcrumb button").first.click()
            for module_id in ("datamimic_ce", "datamimic_ce.domains"):
                page.locator(f'[data-projection-id="{module_id}"]').press("Enter")
            assert page.locator(".flow-breadcrumb").inner_text().endswith("domains")
            page.locator('[data-flow-view="diagram"]').click()
            domains = page.locator('.flow-nodes .node[data-label="domains"][aria-pressed="true"]')
            assert domains.is_visible(), page.evaluate(
                """() => ({
                  breadcrumb: document.querySelector('.flow-breadcrumb').innerText,
                  selected: document.querySelector('.flow-nodes .node.selected')?.dataset.label,
                  context: document.querySelector('.flow-projection-context')?.textContent,
                  responsibility: document.querySelector('.flow-selected-responsibility')
                    ?.innerText,
                })"""
            )
            assert (
                page.locator(".flow-selected-responsibility").get_attribute("data-declaration-id")
                == "COMP-DOMAINS"
            )
            assert page.locator(
                ".flow-selected-responsibility p:not(.flow-responsibility-match)"
            ).inner_text() == ("Own domains behavior.")
            assert "runtime / tasks" not in page.locator(".flow-breadcrumb").inner_text()
        finally:
            browser.close()


def test_target_module_file_maps_to_its_exact_diagram_leaf(tmp_path: Path) -> None:
    page_html, payload = _ce_nested_route_page(tmp_path, include_worker_module_target=True)
    target = next(
        node
        for node in _walk(payload["explorers"]["target"])
        if node["kind"] == "module_target" and node["label"] == "generate_worker.py"
    )
    module_id = "datamimic_ce.engine.runtime.tasks.generate.workers.generate_worker"
    assert target["details"]
    assert next(item["value"] for item in target["details"] if item["label"] == "File") == (
        "datamimic_ce/engine/runtime/tasks/generate/workers/generate_worker.py"
    )
    assert module_id in payload["modules"]

    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_default_timeout(2500)
            page.set_content(page_html, wait_until="load")
            page.locator('[data-flow-view="target"]').click()
            for owner_id in (
                "COMP-RUNTIME",
                "runtime:RUNTIME-TASKS",
                "runtime:tasks:TASKS-GENERATE",
                "runtime:tasks:generate:GENERATE-WORKERS",
            ):
                page.locator(f'[data-target-node="{owner_id}"]').press("Enter")
            page.locator(f'[data-target-node="{target["id"]}"]').click()
            page.locator('[data-flow-view="diagram"]').click()
            assert page.locator(
                f'.flow-nodes .node[data-label="{module_id}"][aria-pressed="true"]'
            ).is_visible()
            assert (
                page.locator(".flow-selected-responsibility").get_attribute("data-declaration-id")
                == target["id"]
            )
        finally:
            browser.close()


def test_selected_diagram_module_round_trips_to_actual_and_target_by_file(
    tmp_path: Path,
) -> None:
    page_html, payload = _ce_nested_route_page(tmp_path, include_worker_module_target=True)
    module_id = "datamimic_ce.engine.runtime.tasks.generate.workers.generate_worker"
    target = next(
        node
        for node in _walk(payload["explorers"]["target"])
        if node["kind"] == "module_target"
        and any(
            detail["label"] == "File"
            and detail["value"]
            == "datamimic_ce/engine/runtime/tasks/generate/workers/generate_worker.py"
            for detail in node["details"]
        )
    )
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_content(page_html, wait_until="load")
            for label in ("runtime", "tasks", "generate", "workers"):
                page.locator(f'.flow-nodes .node[data-label="{label}"]').press("Enter")
            page.locator(f'.flow-nodes .node[data-label="{module_id}"]').press("Space")
            page.locator('[data-flow-view="actual"]').click()
            actual = page.locator(f'[data-projection-id="{module_id}"]')
            assert actual.is_visible()
            assert actual.get_attribute("aria-pressed") == "true"
            page.locator('[data-flow-view="diagram"]').click()
            assert page.locator(
                f'.flow-nodes .node[data-label="{module_id}"][aria-pressed="true"]'
            ).is_visible()
            page.locator('[data-flow-view="target"]').click()
            assert page.locator(f'[data-target-node="{target["id"]}"]').is_visible()
            assert page.locator(
                f'[data-target-node="{target["id"]}"][aria-pressed="true"]'
            ).is_visible()
            assert page.locator(".flow-projection-context").count() == 0
        finally:
            browser.close()


def test_actual_open_engine_package_maps_to_its_exact_physical_frame(
    tmp_path: Path,
) -> None:
    page_html, payload = _ce_nested_route_page(tmp_path, include_engine_owner=True)
    engine = next(
        node
        for node in _walk(payload["explorers"]["actual"])
        if node["id"] == "datamimic_ce.engine"
    )
    assert engine["kind"] == "module"
    assert {child["id"] for child in engine["children"]} >= {
        "datamimic_ce.engine.dsl",
        "datamimic_ce.engine.io",
        "datamimic_ce.engine.runtime",
    }
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_content(page_html, wait_until="load")
            for label in ("runtime", "tasks", "generate", "workers"):
                page.locator(f'.flow-nodes .node[data-label="{label}"]').press("Enter")
            page.locator('[data-flow-view="actual"]').click()
            page.locator(".flow-breadcrumb button").first.click()
            page.locator('[data-projection-id="datamimic_ce"]').press("Enter")
            engine = page.locator('[data-projection-id="datamimic_ce.engine"]')
            assert engine.is_visible()
            engine.press("Enter")
            page.locator('[data-flow-view="diagram"]').click()
            assert page.locator('[data-diagram-frame="layout:LAYOUT-ENGINE"]').is_visible()
            assert "Physical package · navigation grouping: datamimic_ce.engine" in (
                page.locator(".flow-breadcrumb").inner_text()
            )
            assert (
                "No matching scope"
                not in page.locator(".flow-projection-context").all_text_contents()
            )
            assert (
                page.locator('.flow-nodes .node[data-label="Unassigned modules"].selected').count()
                == 0
            )
        finally:
            browser.close()


def test_actual_root_module_keeps_its_exact_target_responsibility_in_diagram(
    tmp_path: Path,
) -> None:
    page_html, payload = _ce_nested_route_page(tmp_path, include_root_compat_target=True)
    target = next(
        node
        for node in _walk(payload["explorers"]["target"])
        if node["kind"] == "module_target"
        and any(
            detail["label"] == "File" and detail["value"] == "datamimic_ce/_compat.py"
            for detail in node["details"]
        )
    )
    actual_module = next(
        node
        for node in _walk(payload["explorers"]["actual"])
        if node["id"] == "datamimic_ce._compat"
    )
    assert actual_module["kind"] == "module"
    assert next(
        detail["value"] for detail in actual_module["details"] if detail["label"] == "File"
    ) == ("datamimic_ce/_compat.py")
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_content(page_html, wait_until="load")
            page.locator('[data-flow-view="actual"]').click()
            page.locator('[data-projection-id="datamimic_ce"]').press("Enter")
            actual_leaf = page.locator('[data-projection-id="datamimic_ce._compat"]')
            assert actual_leaf.is_visible()
            actual_leaf.click()
            assert actual_leaf.get_attribute("aria-pressed") == "true"
            page.locator('[data-flow-view="diagram"]').click()
            module = page.locator(
                '.flow-nodes .node[data-label="datamimic_ce._compat"][aria-pressed="true"]'
            )
            assert module.is_visible(), page.evaluate(
                "() => ({crumb:document.querySelector('.flow-breadcrumb').textContent,"
                "selected:[...document.querySelectorAll('.flow-nodes .selected')]"
                ".map(n=>n.dataset.label),"
                "cards:[...document.querySelectorAll('.flow-nodes .node')]"
                ".map(n=>n.dataset.label),"
                "details:document.querySelector('.flow-selected-responsibility').textContent,"
                "declaration:document.querySelector('.flow-selected-responsibility').dataset.declarationId})"
            )
            details = page.locator(".flow-selected-responsibility")
            assert details.get_attribute("data-declaration-id") == target["id"]
            assert "This module provides compatibility helpers." in details.inner_text(), (
                details.inner_text()
            )
            assert details.get_by_text("Own python_compat behavior.", exact=True).count() == 0
        finally:
            browser.close()


def test_back_restoration_does_not_steal_focus_from_view_switcher(tmp_path: Path) -> None:
    page_html, _payload = _ce_nested_route_page(tmp_path, include_engine_owner=True)
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_content(page_html, wait_until="load")
            actual_button = page.locator('.flow-views [data-flow-view="actual"]')
            page.locator('.flow-views [data-flow-view="structure"]').click()
            page.locator('.flow-alternative [data-flow-card="runtime"]').first.click()
            assert page.locator(".flow-back").is_enabled()

            page.locator(".flow-back").click()
            actual_button.focus()
            page.wait_for_timeout(25)
            page.keyboard.press("Enter")

            assert actual_button.get_attribute("aria-pressed") == "true"
        finally:
            browser.close()


def test_actual_and_target_back_to_root_restore_meaningful_focus(tmp_path: Path) -> None:
    page_html, _payload = _ce_nested_route_page(tmp_path, include_engine_owner=True)
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_content(page_html, wait_until="load")
            page.locator('.flow-views [data-flow-view="actual"]').click()
            root_module = page.locator('.flow-alternative [data-projection-id="datamimic_ce"]')
            root_module.focus()
            page.keyboard.press("Enter")
            page.locator(".flow-back").click()
            assert page.evaluate("() => document.activeElement.matches('[data-projection-id]')")

            page.set_content(page_html, wait_until="load")
            page.locator('.flow-views [data-flow-view="target"]').click()
            component = page.locator('.flow-nodes .node[data-target-node="COMP-RUNTIME"]')
            component.click()
            page.locator(".flow-open-selected").click()
            page.locator(".flow-back").click()
            assert page.evaluate("() => document.activeElement.matches('[data-target-node]')")
        finally:
            browser.close()


@pytest.mark.parametrize(
    ("width", "height", "fallback", "minimum_content_height"),
    [
        (375, 844, False, 337),
        (375, 844, True, 337),
        (1024, 768, False, 300),
        (1920, 1080, False, 680),
    ],
)
def test_fullscreen_keeps_explorer_content_usable(
    tmp_path: Path,
    width: int,
    height: int,
    fallback: bool,
    minimum_content_height: int,
) -> None:
    page_html, _payload = _ce_nested_route_page(tmp_path)
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            if fallback:
                page.add_init_script("Element.prototype.requestFullscreen = undefined")
            page.set_content(page_html, wait_until="load")
            page.locator('.flow-views [data-flow-view="target"]').click()
            assert page.locator(".flow-details-toggle").get_attribute("aria-expanded") == "false"
            page.locator(".flow-fullscreen").click()
            page.wait_for_timeout(50)

            result = page.evaluate(
                """() => {
                  const root = document.querySelector('#flow');
                  const content = [...root.querySelectorAll('.flow-canvas, .flow-alternative')]
                    .find(element => getComputedStyle(element).display !== 'none');
                  const box = content.getBoundingClientRect();
                  const toolbar = root.querySelector('.flow-toolbar');
                  return {
                    expanded: root.dataset.expanded,
                    contentHeight: box.height,
                    viewportHeight: innerHeight,
                    documentWidth: document.documentElement.scrollWidth,
                    viewportWidth: innerWidth,
                    toolbarWidth: toolbar.clientWidth,
                    toolbarContentWidth: toolbar.scrollWidth,
                  fullscreenVisible: root.querySelector('.flow-fullscreen')
                    .getClientRects().length > 0,
                  openVisible: root.querySelector('.flow-open-selected')
                    .getClientRects().length > 0,
                  };
                }"""
            )
            assert result["expanded"] in {"native", "fallback"}
            assert result["contentHeight"] >= minimum_content_height, result
            assert result["documentWidth"] <= result["viewportWidth"] + 1, result
            assert result["fullscreenVisible"] and result["openVisible"], result

            page.locator('.flow-nodes .node[data-target-node="COMP-RUNTIME"]').click()
            page.locator(".flow-open-selected").click()
            assert page.locator(".flow-back").is_visible()
            page.locator(".flow-zoom-in").click()
            page.locator('.flow-views [data-flow-view="actual"]').click()
            assert (
                page.locator('.flow-views [data-flow-view="actual"]').get_attribute("aria-pressed")
                == "true"
            )
            page.locator(".flow-fullscreen").click()
        finally:
            browser.close()


@pytest.mark.parametrize("view", ["diagram", "target", "actual", "diff"])
@pytest.mark.parametrize("fallback", [False, True])
def test_mobile_fullscreen_content_height_is_stable_across_views(
    tmp_path: Path, view: str, fallback: bool
) -> None:
    page_html, _payload = _ce_nested_route_page(tmp_path)
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 375, "height": 844})
            if fallback:
                page.add_init_script("Element.prototype.requestFullscreen = undefined")
            page.set_content(page_html, wait_until="load")
            page.locator(f'.flow-views [data-flow-view="{view}"]').click()
            page.locator(".flow-fullscreen").click()
            page.wait_for_timeout(50)
            result = page.evaluate(
                """() => {
                  const root = document.querySelector('#flow');
                  const content = [...root.querySelectorAll('.flow-canvas, .flow-alternative')]
                    .find(element => getComputedStyle(element).display !== 'none');
                  return {
                    view: root.dataset.view,
                    expanded: root.dataset.expanded,
                    contentHeight: content.getBoundingClientRect().height,
                    viewportHeight: innerHeight,
                  };
                }"""
            )
            assert result["contentHeight"] >= 337, result
        finally:
            browser.close()


@pytest.mark.parametrize(
    ("view", "frame_selector", "role"),
    [
        ("diagram", '[data-diagram-frame="layout:LAYOUT-ENGINE"]', "Physical package"),
        ("target", '[data-target-node="layout:LAYOUT-ENGINE"]', "Package layout"),
    ],
)
def test_frame_headers_compact_visible_labels_keep_full_scope_accessible(
    tmp_path: Path, view: str, frame_selector: str, role: str
) -> None:
    page_html, _payload = _cross_frame_domains_page(tmp_path)
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_default_timeout(2_500)
            page.set_content(page_html, wait_until="load")
            page.locator(f'.flow-views [data-flow-view="{view}"]').click()
            frame = page.locator(frame_selector)
            assert frame.is_visible()
            visible = frame.locator(".target-frame-title").evaluate("node => node.textContent")
            assert frame.locator(".target-frame-role").evaluate("node => node.textContent") == role
            assert "engine" in visible
            assert "datamimic_ce.engine" not in visible
            assert "datamimic_ce.engine" in frame.get_attribute("aria-label")
            assert "datamimic_ce.engine" in frame.locator("title").text_content()
            page.locator(".flow-details-toggle").click()
            frame.locator(".target-frame-header-hit").click(position={"x": 10, "y": 10})
            assert "datamimic_ce.engine" in page.locator(".flow-inspector").inner_text()
        finally:
            browser.close()


def test_normal_explorer_geometry_is_stable_across_all_views(tmp_path: Path) -> None:
    page_html, _payload = _ce_nested_route_page(tmp_path)
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1920, "height": 1080})
            page.set_content(page_html, wait_until="load")
            measurements = {}
            for view in ("diagram", "structure", "review", "actual", "target", "diff"):
                page.locator(f'.flow-views [data-flow-view="{view}"]').click()
                measurements[view] = page.evaluate(
                    """() => {
                      const flow = document.querySelector('#flow').getBoundingClientRect();
                      const layout = document.querySelector('.flow-layout').getBoundingClientRect();
                      const legend = document.querySelector('.flow-legend').getBoundingClientRect();
                      return {top: flow.top, height: flow.height, layoutTop: layout.top,
                        layoutHeight: layout.height, legendHeight: legend.height};
                    }"""
                )
            baseline = measurements["diagram"]
            for _view, measurement in measurements.items():
                assert abs(measurement["top"] - baseline["top"]) <= 2, measurements
                assert abs(measurement["height"] - baseline["height"]) <= 2, measurements
                assert abs(measurement["layoutTop"] - baseline["layoutTop"]) <= 2, measurements
                assert abs(measurement["layoutHeight"] - baseline["layoutHeight"]) <= 2, (
                    measurements
                )
                assert abs(measurement["legendHeight"] - baseline["legendHeight"]) <= 2, (
                    measurements
                )
        finally:
            browser.close()


@pytest.mark.parametrize(
    ("view", "frame_selector", "role"),
    [
        ("diagram", '[data-diagram-frame="layout:LAYOUT-ENGINE"]', "Physical package"),
        ("target", '[data-target-node="layout:LAYOUT-ENGINE"]', "Package layout"),
    ],
)
def test_long_frame_header_ellipsizes_to_measured_width_but_keeps_full_scope(
    tmp_path: Path, view: str, frame_selector: str, role: str
) -> None:
    scope = f"datamimic_ce.engine_{'scope' * 24}"
    page_html, _payload = _cross_frame_domains_page(tmp_path, engine_scope=scope)
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_default_timeout(2_500)
            page.set_content(page_html, wait_until="load")
            page.locator(f'.flow-views [data-flow-view="{view}"]').click()
            frame = page.locator(frame_selector)
            measurement = frame.evaluate(
                """frame => {
                  const name = frame.querySelector('.target-frame-title');
                  const header = frame.querySelector('.target-frame-header-hit');
                  return {
                    role: frame.querySelector('.target-frame-role').textContent,
                    name: name.textContent,
                    textWidth: name.getComputedTextLength(),
                    availableWidth: header.getBBox().width - 28,
                  };
                }"""
            )
            assert measurement["role"] == role
            assert measurement["name"].endswith("…")
            assert measurement["textWidth"] <= measurement["availableWidth"] + 1
            assert scope in frame.get_attribute("aria-label")
            assert scope in frame.locator("title").text_content()
            page.locator(".flow-details-toggle").click()
            frame.locator(".target-frame-header-hit").click(position={"x": 10, "y": 10})
            assert scope in page.locator(".flow-inspector").inner_text()
        finally:
            browser.close()


def test_clicking_active_diagram_tab_preserves_open_scope_and_selection(
    tmp_path: Path,
) -> None:
    page_html, _payload = _ce_nested_route_page(tmp_path)
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_content(page_html, wait_until="load")
            runtime = page.locator('.flow-nodes .node[data-label="runtime"]')
            runtime.press("Enter")
            before = page.evaluate(
                """() => ({
                  breadcrumb: document.querySelector('.flow-breadcrumb').textContent,
                  cards: [...document.querySelectorAll('.flow-nodes .node')]
                    .map(node => node.dataset.label),
                  heading: document.querySelector('.flow-inspector h2')?.textContent,
                })"""
            )
            assert "runtime" in before["breadcrumb"]
            page.locator('.flow-views [data-flow-view="diagram"]').click()
            after = page.evaluate(
                """() => ({
                  breadcrumb: document.querySelector('.flow-breadcrumb').textContent,
                  cards: [...document.querySelectorAll('.flow-nodes .node')]
                    .map(node => node.dataset.label),
                  heading: document.querySelector('.flow-inspector h2')?.textContent,
                })"""
            )
            assert after == before
        finally:
            browser.close()


@pytest.mark.parametrize("view", ["diagram", "target"])
def test_edges_route_around_frame_headers_and_share_one_geometry(tmp_path: Path, view: str) -> None:
    page_html, payload = _cross_frame_domains_page(tmp_path, observed_cross_frame_edge=True)
    graph = payload["explorers"]["target_diagrams"]["root"]
    frame_ids = set(graph["containers"])
    frame_edges = (
        [
            edge
            for edge in graph["edges"]
            if edge["source"] in frame_ids or edge["target"] in frame_ids
        ]
        if view == "target"
        else []
    )
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_content(page_html, wait_until="load")
            page.locator(f'.flow-views [data-flow-view="{view}"]').click()
            if view == "diagram":
                page.locator(".flow-reset-filters").click()
            result = page.evaluate(
                """args => {
                  const {frameEdges, frameIds: frameIdList} = args;
                  const frameIds = new Set(frameIdList);
                  const root = document.querySelector('#flow');
                  const svg = root.querySelector('svg.flow-graph');
                  const headers = [...svg.querySelectorAll(
                    '.diagram-frame .target-frame-header-hit, ' +
                    '.target-container .target-frame-header-hit'
                  )].map(header => {
                    const box = header.getBBox();
                    return {left: box.x, top: box.y, right: box.x + box.width,
                      bottom: box.y + box.height};
                  });
                  const collisions = [], frameNormals = [];
                  const paths = [...svg.querySelectorAll('.edge .line, .target-edge .line')];
                  for (const path of paths) {
                    const length = path.getTotalLength();
                    for (let at = 0; at <= length; at += 1) {
                      const point = path.getPointAtLength(at);
                      if (headers.some(box => point.x > box.left && point.x < box.right &&
                        point.y > box.top && point.y < box.bottom)) {
                        collisions.push(path.closest('.edge, .target-edge')
                          ?.getAttribute('aria-label'));
                        break;
                      }
                    }
                  }
                  const aligned = [...svg.querySelectorAll('.edge, .target-edge')].every(group => {
                    const selectors = group.matches('.target-edge')
                      ? ['.line', '.hit'] : ['.line', '.pulse', '.hit'];
                    const paths = selectors.map(selector =>
                      group.querySelector(selector)?.getAttribute('d'));
                    return paths[0] && paths.every(path => path === paths[0]);
                  });
                  for (const edge of frameEdges) {
                    const group = svg.querySelector(`[data-target-edge="${edge.declaration}"]`);
                    const frameId = frameIds.has(edge.source) ? edge.source : edge.target;
                    const frame = svg.querySelector(`[data-target-container="${frameId}"]`);
                    const path = group?.querySelector('.line');
                    const rect = frame?.querySelector('.target-frame');
                    if (!path || !rect) { frameNormals.push(false); continue; }
                    const bounds = element => {
                      const b = element.getBBox(), m = element.getScreenCTM();
                      const p = [[b.x,b.y],[b.x+b.width,b.y],[b.x,b.y+b.height],
                        [b.x+b.width,b.y+b.height]].map(([x,y])=>
                          new DOMPoint(x,y).matrixTransform(m));
                      return {left:Math.min(...p.map(v=>v.x)),right:Math.max(...p.map(v=>v.x)),
                        top:Math.min(...p.map(v=>v.y)),bottom:Math.max(...p.map(v=>v.y))};
                    };
                    const box = bounds(rect), length = path.getTotalLength();
                    const matrix = path.getScreenCTM();
                    const at = distance => { const p=path.getPointAtLength(distance);
                      return new DOMPoint(p.x,p.y).matrixTransform(matrix); };
                    const sourceFrame = edge.source === frameId;
                    const point = at(sourceFrame ? 0 : length);
                    const adjacent = at(sourceFrame ? Math.min(2,length) : Math.max(0,length-2));
                    const onSide = Math.abs(point.x-box.left)<=1 || Math.abs(point.x-box.right)<=1;
                    const outward = sourceFrame
                      ? (point.x<=box.left ? adjacent.x<point.x : adjacent.x>point.x)
                      : (point.x<=box.left ? adjacent.x<point.x : adjacent.x>point.x);
                    frameNormals.push(onSide && Math.abs(adjacent.y-point.y)<=0.5 && outward);
                  }
                  return {collisions, aligned, edgeCount: paths.length, frameNormals};
                }""",
                {"frameEdges": frame_edges, "frameIdList": sorted(frame_ids)},
            )
            assert result["edgeCount"] > 0, result
            assert result["collisions"] == [], result
            assert result["aligned"], result
            assert all(result["frameNormals"]), result
        finally:
            browser.close()


def test_diagram_keeps_clear_framed_card_edges_on_normal_ports(tmp_path: Path) -> None:
    page_html, _payload = _cross_frame_domains_page(tmp_path, observed_cross_frame_edge=True)
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_content(page_html, wait_until="load")
            page.locator('.flow-views [data-flow-view="diagram"]').click()
            result = page.evaluate(
                """() => {
                  const svg = document.querySelector('svg.flow-graph');
                  const group = [...svg.querySelectorAll('.edge')].find(item =>
                    item.querySelector('.hit')?.dataset.key === 'runtime>domains');
                  const path = group?.querySelector('.line');
                  const card = svg.querySelector('.flow-nodes .node[data-label="runtime"] .card');
                  if (!path || !card) return null;
                  const matrix = path.getScreenCTM();
                  const length = path.getTotalLength();
                  const screenPoint = at => {
                    const point = path.getPointAtLength(at);
                    return new DOMPoint(point.x, point.y).matrixTransform(matrix);
                  };
                  const first = screenPoint(0), next = screenPoint(Math.min(2, length));
                  const box = card.getBBox(), cardMatrix = card.getScreenCTM();
                  const corners = [[box.x, box.y], [box.x + box.width, box.y],
                    [box.x, box.y + box.height], [box.x + box.width, box.y + box.height]]
                    .map(([x, y]) => new DOMPoint(x, y).matrixTransform(cardMatrix));
                  const bounds = {top: Math.min(...corners.map(p => p.y)),
                    bottom: Math.max(...corners.map(p => p.y))};
                  return {atCardTopOrBottom: Math.min(Math.abs(first.y - bounds.top),
                    Math.abs(first.y - bounds.bottom)) <= 1,
                    normalTangent: Math.abs(next.x - first.x) <= 0.5,
                    aligned: [...group.querySelectorAll('.line, .hit, .pulse')]
                      .every(item => item.getAttribute('d') === path.getAttribute('d'))};
                }"""
            )
            assert result is not None
            assert result["atCardTopOrBottom"] and result["normalTangent"], result
            assert result["aligned"], result
        finally:
            browser.close()


def test_target_incoming_requirements_detour_around_engine_header(tmp_path: Path) -> None:
    page_html, _payload = _cross_frame_domains_page(tmp_path, incoming_engine_requirements=True)
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_content(page_html, wait_until="load")
            page.locator('.flow-views [data-flow-view="target"]').click()
            result = page.evaluate(
                """() => {
                  const svg = document.querySelector('svg.flow-graph');
                  const header = svg.querySelector(
                    '[data-target-node="layout:LAYOUT-ENGINE"] .target-frame-header-hit');
                  const headerBox = header.getBBox(), headerMatrix = header.getScreenCTM();
                  const corners = [[headerBox.x, headerBox.y],
                    [headerBox.x + headerBox.width, headerBox.y],
                    [headerBox.x, headerBox.y + headerBox.height],
                    [headerBox.x + headerBox.width, headerBox.y + headerBox.height]]
                    .map(([x, y]) => new DOMPoint(x, y).matrixTransform(headerMatrix));
                  const protectedBox = {left: Math.min(...corners.map(p => p.x)),
                    right: Math.max(...corners.map(p => p.x)),
                    top: Math.min(...corners.map(p => p.y)),
                    bottom: Math.max(...corners.map(p => p.y))};
                  const collisions = [], endpoints = {}, normals = {}, cardCrossings = [];
                  for (const id of ['COMP-AUTHORING', 'COMP-RESOURCES']) {
                    const key = `requires:${id}:runtime`;
                    const group = svg.querySelector(`[data-target-edge="${key}"]`);
                    const path = group?.querySelector('.line');
                    if (!path) return {missing: key};
                    const matrix = path.getScreenCTM(), length = path.getTotalLength();
                    const at = distance => {
                      const p = path.getPointAtLength(distance);
                      return new DOMPoint(p.x, p.y).matrixTransform(matrix);
                    };
                    for (let distance = 0; distance <= length; distance += 0.5) {
                      const p = at(distance);
                      if (p.x > protectedBox.left && p.x < protectedBox.right &&
                          p.y > protectedBox.top && p.y < protectedBox.bottom) {
                        collisions.push(key);
                        break;
                      }
                    }
                    for (const node of svg.querySelectorAll('.target-node .target-card')) {
                      const owner = node.closest('[data-target-node]')?.dataset.targetNode;
                      if (owner === id || owner === 'COMP-RUNTIME') continue;
                      const box = node.getBBox(), nodeMatrix = node.getScreenCTM();
                      const points = [[box.x, box.y], [box.x + box.width, box.y],
                        [box.x, box.y + box.height], [box.x + box.width, box.y + box.height]]
                        .map(([x, y]) => new DOMPoint(x, y).matrixTransform(nodeMatrix));
                      const card = {left: Math.min(...points.map(p => p.x)),
                        right: Math.max(...points.map(p => p.x)),
                        top: Math.min(...points.map(p => p.y)),
                        bottom: Math.max(...points.map(p => p.y))};
                      for (let distance = 0; distance <= length; distance += 0.5) {
                        const p = at(distance);
                        if (p.x > card.left && p.x < card.right &&
                            p.y > card.top && p.y < card.bottom) {
                          cardCrossings.push(`${key}:${owner}`);
                          break;
                        }
                      }
                    }
                    const node = svg.querySelector(
                      '[data-target-node="COMP-RUNTIME"] .target-card');
                    const box = node.getBBox(), nodeMatrix = node.getScreenCTM();
                    const points = [[box.x, box.y], [box.x + box.width, box.y],
                      [box.x, box.y + box.height], [box.x + box.width, box.y + box.height]]
                      .map(([x, y]) => new DOMPoint(x, y).matrixTransform(nodeMatrix));
                    const nodeBox = {left: Math.min(...points.map(p => p.x)),
                      right: Math.max(...points.map(p => p.x)),
                      top: Math.min(...points.map(p => p.y)),
                      bottom: Math.max(...points.map(p => p.y))};
                    const end = at(length);
                    endpoints[key] = Math.min(Math.abs(end.x - nodeBox.left),
                      Math.abs(end.x - nodeBox.right), Math.abs(end.y - nodeBox.top),
                      Math.abs(end.y - nodeBox.bottom)) <= 1;
                    const sourceNode = svg.querySelector(`[data-target-node="${id}"] .target-card`);
                    const sourceBox = sourceNode.getBBox();
                    const sourceMatrix = sourceNode.getScreenCTM();
                    const sourceCorners = [[sourceBox.x, sourceBox.y],
                      [sourceBox.x + sourceBox.width, sourceBox.y],
                      [sourceBox.x, sourceBox.y + sourceBox.height],
                      [sourceBox.x + sourceBox.width, sourceBox.y + sourceBox.height]]
                      .map(([x, y]) => new DOMPoint(x, y).matrixTransform(sourceMatrix));
                    const sourceBounds = {left: Math.min(...sourceCorners.map(p => p.x)),
                      right: Math.max(...sourceCorners.map(p => p.x)),
                      top: Math.min(...sourceCorners.map(p => p.y)),
                      bottom: Math.max(...sourceCorners.map(p => p.y))};
                    const start = at(0), next = at(Math.min(2, length));
                    const previous = at(Math.max(0, length - 2));
                    const sourceSide = Math.min(
                      Math.abs(start.x - sourceBounds.left), Math.abs(start.x - sourceBounds.right),
                      Math.abs(start.y - sourceBounds.top),
                      Math.abs(start.y - sourceBounds.bottom));
                    const targetSide = Math.min(
                      Math.abs(end.x - nodeBox.left), Math.abs(end.x - nodeBox.right),
                      Math.abs(end.y - nodeBox.top), Math.abs(end.y - nodeBox.bottom));
                    const sourceIsHorizontal = Math.min(Math.abs(start.x - sourceBounds.left),
                      Math.abs(start.x - sourceBounds.right)) < Math.min(
                      Math.abs(start.y - sourceBounds.top),
                      Math.abs(start.y - sourceBounds.bottom));
                    const targetIsHorizontal = Math.min(Math.abs(end.x - nodeBox.left),
                      Math.abs(end.x - nodeBox.right)) < Math.min(
                      Math.abs(end.y - nodeBox.top), Math.abs(end.y - nodeBox.bottom));
                    normals[key] = sourceSide <= 1 && targetSide <= 1 &&
                      (sourceIsHorizontal ? Math.abs(next.y - start.y) <= 0.5
                        : Math.abs(next.x - start.x) <= 0.5) &&
                      (targetIsHorizontal ? Math.abs(previous.y - end.y) <= 0.5
                        : Math.abs(previous.x - end.x) <= 0.5);
                    if (![...group.querySelectorAll('.line, .hit')].every(item =>
                      item.getAttribute('d') === path.getAttribute('d'))) {
                      collisions.push(`${key}:geometry`);
                    }
                  }
                  return {collisions, endpoints, normals, cardCrossings};
                }"""
            )
            assert "missing" not in result, result
            assert result["collisions"] == [], result
            assert result["cardCrossings"] == [], result
            assert all(result["endpoints"].values()), result
            assert all(result["normals"].values()), result
        finally:
            browser.close()


@pytest.mark.parametrize("view", ["diagram", "structure", "review", "actual", "target", "diff"])
def test_active_explorer_tab_preserves_selection_in_every_view(tmp_path: Path, view: str) -> None:
    page_html, _payload = _ce_nested_route_page(tmp_path)
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_default_timeout(2_500)
            page.set_content(page_html, wait_until="load")
            page.locator(f'.flow-views [data-flow-view="{view}"]').click()
            if view == "diagram":
                page.locator(".flow-nodes .node:not(.diagram-frame)").first.click()
            elif view == "structure":
                page.locator(".flow-alternative [data-flow-card]").first.click()
            elif view == "review":
                page.locator('.flow-alternative details summary:has-text("Open an entry")').click()
                page.locator(".flow-alternative [data-flow-card]").first.click()
            elif view in {"actual", "diff"}:
                page.locator(".flow-alternative [data-projection-id]").first.click()
            else:
                page.locator(".flow-nodes .target-node:not(.target-container)").first.click()
            before = page.evaluate(
                """() => ({
                  heading: document.querySelector('.flow-inspector h2')?.textContent,
                  selected: [...document.querySelectorAll(
                    '.flow-alternative [aria-pressed="true"], .flow-nodes [aria-pressed="true"]'
                  )].map(node => node.dataset.flowCard || node.dataset.flowEdge ||
                    node.dataset.projectionId || node.dataset.targetNode || node.dataset.label),
                })"""
            )
            assert before["selected"] or before["heading"]
            page.locator(f'.flow-views [data-flow-view="{view}"]').click()
            after = page.evaluate(
                """() => ({
                  heading: document.querySelector('.flow-inspector h2')?.textContent,
                  selected: [...document.querySelectorAll(
                    '.flow-alternative [aria-pressed="true"], .flow-nodes [aria-pressed="true"]'
                  )].map(node => node.dataset.flowCard || node.dataset.flowEdge ||
                    node.dataset.projectionId || node.dataset.targetNode || node.dataset.label),
                })"""
            )
            assert after == before
        finally:
            browser.close()


def test_returning_to_diagram_from_structure_preserves_open_scope(
    tmp_path: Path,
) -> None:
    page_html, _payload = _ce_nested_route_page(tmp_path)
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_default_timeout(3_000)
            page.set_content(page_html, wait_until="load")
            page.locator('.flow-views [data-flow-view="structure"]').click()
            page.locator('.flow-alternative [data-flow-card="runtime"]').first.click()
            before = page.locator(".flow-inspector h2").text_content()
            assert before == "runtime"
            page.locator('.flow-views [data-flow-view="diagram"]').click()
            assert page.locator(".flow-inspector h2").text_content() == before
            assert page.locator(".flow-back").is_visible()
        finally:
            browser.close()


def test_cross_frame_dependency_chain_retains_ranks_with_compact_rendering(tmp_path: Path) -> None:
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
            assert card_centers["COMP-RUNTIME"] == card_centers["COMP-DOMAINS"]
            assert card_centers["COMP-IO"] >= card_centers["COMP-RUNTIME"]
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
            assert centers["COMP-RUNTIME"] <= centers["COMP-IO"]
            assert centers["COMP-DOMAINS"] == centers["COMP-RUNTIME"]
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
            page.locator("[data-flow-details-toggle]").click()
            page.locator('[data-target-node="COMP-DOMAINS"]').click()
            page.locator(".flow-open-selected").click()
            target = page.locator('[data-target-node="domains:DOMAIN-04"]')

            def anchor_state() -> dict[str, Any]:
                return target.evaluate(
                    """node => {
                      const box = node.getBoundingClientRect();
                      const canvas = document.querySelector('.flow-canvas');
                      const canvasBox = canvas.getBoundingClientRect();
                      return {
                        transform: node.getAttribute('transform'),
                        x: box.left - canvasBox.left,
                        y: box.top - canvasBox.top,
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
            assert abs(after["x"] - before["x"]) <= 2
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


def test_cycle_warning_tracks_null_band_after_wrapped_ranked_rows(tmp_path: Path) -> None:
    page_html, payload = _cycle_page(tmp_path, wrapped_rank_count=10)
    root = payload["explorers"]["target_diagrams"]["root"]
    nodes = _nodes(root)
    consumer_ids = [f"COMP-RANK-{index:02}" for index in range(10)]
    assert {nodes[node_id]["dependency_rank"] for node_id in consumer_ids} == {0}
    assert nodes["COMP-RANK-PROVIDER"]["dependency_rank"] == 1
    null_ids = {"COMP-APP", "COMP-ARCHIVE", "COMP-EMPTY", "COMP-STORE"}
    assert {
        node_id
        for node_id, node in nodes.items()
        if node.get("kind") == "component" and node.get("dependency_rank") is None
    } == null_ids
    ranked_ids = [
        node_id
        for node_id, node in nodes.items()
        if node["kind"] == "component" and node["dependency_rank"] is not None
    ]

    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_content(page_html, wait_until="networkidle")
            canvas = page.locator(".flow-canvas")
            canvas.evaluate(
                "node => { node.style.flex = '0 0 552px'; node.style.width = '552px'; }"
            )
            page.get_by_role("button", name="Target").click()
            assert canvas.evaluate("node => node.clientWidth") == 550
            warning = page.get_by_text(
                "Dependency order unresolved: cycle or dependency on a cycle.", exact=True
            )
            assert warning.is_visible()
            geometry = page.evaluate(
                """({rankedIds, nullIds, consumerIds}) => {
                  const rects = ids => ids.map(id => {
                    const rect = document.querySelector(`[data-target-node="${id}"]`)
                      .getBoundingClientRect();
                    return {top: rect.top, bottom: rect.bottom};
                  });
                  const warning = document.querySelector('.target-cycle-warning')
                    .getBoundingClientRect();
                  const consumerTops = [...new Set(rects(consumerIds).map(rect => rect.top))]
                    .sort((left, right) => left - right);
                  const rowSteps = consumerTops.slice(1).map(
                    (top, index) => top - consumerTops[index]
                  );
                  const ranked = rects(rankedIds);
                  const residual = rects(nullIds);
                  return {
                    warning: {top: warning.top, bottom: warning.bottom},
                    rankedBottom: Math.max(...ranked.map(rect => rect.bottom)),
                    residualTop: Math.min(...residual.map(rect => rect.top)),
                    rowStep: Math.min(...rowSteps),
                    wrappedRows: consumerTops.length,
                  };
                }""",
                {"rankedIds": ranked_ids, "nullIds": sorted(null_ids), "consumerIds": consumer_ids},
            )
            assert geometry["wrappedRows"] > 1
            assert geometry["rowStep"] > 0
            assert geometry["warning"]["top"] >= geometry["rankedBottom"], geometry
            assert geometry["warning"]["top"] <= geometry["residualTop"] + geometry["rowStep"]
        finally:
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
        assert page.locator('[data-target-node="COMP-APP"]').get_attribute("aria-pressed") == "true"
        assert [
            item.text_content().strip() for item in page.locator(".flow-breadcrumb button").all()
        ] == ["Target"]
        assert toggle.get_attribute("aria-expanded") == "false"
        toggle.click()

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
        assert before["selected"] == "COMP-APP"
        assert before["path"] == ["Target"]
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

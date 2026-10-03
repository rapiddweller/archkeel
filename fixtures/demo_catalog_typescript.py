# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""TypeScript source-only rule examples and explicit limits."""

from __future__ import annotations

import json
from pathlib import Path

from archkeel.ir.model import DiagnosticCode
from fixtures.demo_catalog_support import Variant, contract_measurement_budgets

TYPESCRIPT_FIXTURE_DIR = Path(__file__).resolve().parent / "H-typescript"


def contract() -> dict:
    return json.loads((TYPESCRIPT_FIXTURE_DIR / "architecture-contract.json").read_text())


def with_rule(kind: str, **fields: object) -> str:
    value = contract()
    value["rules"].append(
        {
            "id": "PROBE",
            "kind": kind,
            "rationale": "Exercise the declared TypeScript capability.",
            "provenance": ["docs/architecture/shop.md"],
            "decided_by": "architect",
            **fields,
        }
    )
    return json.dumps(value, indent=2) + "\n"


def appended(path: str, text: str) -> str:
    return (TYPESCRIPT_FIXTURE_DIR / path).read_text() + text


def example(
    name: str,
    item: str,
    summary: str,
    files: dict[str, str],
    violations: tuple[str, ...] = (),
    *,
    codes: tuple[DiagnosticCode, ...] = (),
    refused: bool = False,
    unknown: bool = False,
    gap: bool = False,
) -> Variant:
    return Variant(
        id=f"typescript-{name}",
        section="validation" if refused or gap else "class_a",
        item=f"typescript:{item}",
        summary=summary,
        files=files,
        expected_violations=violations,
        expected_codes=(*codes, *("rule.violated" for _ in violations)),
        expected_kinds=("parse_error",)
        if gap
        else ("rule_unsupported_by_profile",)
        if refused
        else (),
        expected_declared_rules=None
        if refused
        else "FAIL"
        if violations
        else "UNKNOWN"
        if unknown
        else "PASS",
        fixture=TYPESCRIPT_FIXTURE_DIR,
    )


UNSUPPORTED_RULES = {
    "forbidden_construct": {"source": "shop", "constructs": ["eval"]},
    "symbol_placement": {
        "source": "shop",
        "class_kinds": ["class"],
        "allowed_sources": ["shop.src.domain"],
    },
    "boundary_types": {"source": "shop"},
}

UNMEASURED = (
    "private_crossings",
    "typing_positions",
    "calls_unresolved",
    "untyped_private_accesses",
)

RULE_EXAMPLES = {
    "forbidden_dependency": ("clean", "forbidden-type-import"),
    "allowed_dependency": ("allowed-pair",),
    "complete_requires": ("clean", "requires"),
    "complete_assignment": ("clean", "unassigned"),
    "complete_external_scope": ("clean", "undeclared-external"),
    "external_dependency_scope": ("external-allowed", "external-forbidden"),
    "root_layout": ("clean", "unassigned"),
    "no_component_cycles": ("clean", "component-cycle", "module-cycle"),
    "sibling_isolation": ("clean", "sibling"),
    "interface_boundary": ("module-interface", "private-module"),
    **{kind: (f"unsupported-{kind}",) for kind in UNSUPPORTED_RULES},
}

NAME_BUDGET_EXAMPLES = {
    "facade_names": ("unsupported-facade-budget",),
    "coupling_names": ("unsupported-coupling-budget",),
}


STRUCTURE_EXAMPLES = {
    name: ("clean",)
    for name in (
        "scope",
        "level",
        "modules",
        "inner_edges",
        "fan_in",
        "fan_out",
        "calls",
        "unresolved",
    )
}


MEASUREMENT_EXAMPLES = {
    "violations": ("clean", "forbidden-type-import"),
    "cycle_edges": ("clean", "component-cycle", "module-cycle"),
    "coverage_failures": ("clean", "syntax-error"),
    "unknown_positions": ("clean", "computed-import"),
    **{name: ("clean", f"unsupported-budget-{name}") for name in UNMEASURED},
}


def _interfaces() -> dict:
    value = contract()
    public = {
        "app": [],
        "data": ["shop.src.data.local_x2e_ts"],
        "presentation": ["shop.src.presentation.page_x2e_ts"],
        "domain": ["shop.src.domain.index_x2e_ts", "shop.src.domain.repository_x2e_ts"],
    }
    for component in value["components"]:
        component["public"] = public[component["label"]]
    value["rules"].append(json.loads(with_rule("interface_boundary"))["rules"][-1])
    return value


def _external_names() -> str:
    value = contract()
    for dependency in ("transport-client", "transport.client"):
        value["rules"].append(
            json.loads(
                with_rule(
                    "external_dependency_scope",
                    dependency=dependency,
                    allowed_sources=["shop.src.data"],
                )
            )["rules"][-1]
            | {"id": f"EXTERNAL-{dependency}"}
        )
    return json.dumps(value)


def _nested_symbol_rule() -> dict[str, str]:
    value = contract()
    domain = next(component for component in value["components"] if component["label"] == "domain")
    nested = {
        "schema_version": value["schema_version"],
        "components": [{**domain, "id": "COMP-CORE", "label": "core"}],
        "rules": [json.loads(with_rule("boundary_types", source="shop.src.domain"))["rules"][-1]],
    }
    domain["inside"] = "contracts/domain.json"
    return {
        "architecture-contract.json": json.dumps(value),
        "contracts/domain.json": json.dumps(nested),
    }


def _symbol_interface() -> str:
    value = _interfaces()
    domain = next(component for component in value["components"] if component["label"] == "domain")
    domain["public"] = ["shop.src.domain.index_x2e_ts:Order"]
    return json.dumps(value)


def _symbol_requires() -> str:
    value = contract()
    presentation = next(
        component for component in value["components"] if component["label"] == "presentation"
    )
    presentation["requires"][0]["through"] = ["shop.src.domain.index_x2e_ts:Order"]
    return json.dumps(value)


def _name_budget(*, coupling: bool) -> str:
    value = _interfaces()
    key = "coupling_budgets" if coupling else "facade_budgets"
    owner = {"source": "presentation", "target": "domain"} if coupling else {"component": "domain"}
    value["declarations"] = {
        key: [{**owner, "max_names": 1, "provenance": ["docs/architecture/shop.md"]}]
    }
    return json.dumps(value)


def _budget(name: str) -> dict[str, str]:
    return {
        "architecture-contract.json": contract_measurement_budgets(
            name, fixture=TYPESCRIPT_FIXTURE_DIR
        ),
        "architecture-baseline.json": json.dumps(
            {"schema_version": "1.2.0", "budgets": {name: 0}, "violations": []}
        ),
    }


VARIANTS: tuple[Variant, ...] = (
    example("clean", "clean", "Seven modules and a complete acyclic import graph.", {}),
    example(
        "forbidden-type-import",
        "forbidden_dependency",
        "A type-only domain import still breaks dependency direction.",
        {
            "src/domain/order.ts": appended(
                "src/domain/order.ts", 'import type { local } from "../data/local";\n'
            )
        },
        ("COMPONENT-CYCLES", "DOMAIN-NO-DATA", "MODULE-CYCLES", "REQUIRES"),
        codes=("closed_world.observed_forbidden", "graph.drift"),
    ),
    example(
        "requires",
        "complete_requires",
        "Data reaches presentation without a requires entry.",
        {
            "src/data/remote.ts": appended(
                "src/data/remote.ts", 'import { page } from "../presentation/page";\n'
            )
        },
        ("REQUIRES",),
        codes=("graph.drift",),
    ),
    example(
        "unassigned",
        "complete_assignment",
        "A stray immediate child has no owner and breaks layout.",
        {"src/stray.ts": "export const stray = 1;\n"},
        ("ASSIGNMENT", "LAYOUT"),
    ),
    example(
        "component-cycle",
        "no_component_cycles",
        "A reverse import closes both component and module cycles.",
        {
            "src/domain/repository.ts": appended(
                "src/domain/repository.ts", 'import { local } from "../data/local";\n'
            )
        },
        ("COMPONENT-CYCLES", "DOMAIN-NO-DATA", "MODULE-CYCLES", "REQUIRES"),
        codes=("closed_world.observed_forbidden", "graph.drift"),
    ),
    example(
        "module-cycle",
        "no_component_cycles",
        "Two modules cycle inside domain; the component graph stays acyclic.",
        {
            "src/domain/order.ts": appended(
                "src/domain/order.ts", 'import type { OrderRepository } from "./repository";\n'
            )
        },
        ("MODULE-CYCLES",),
    ),
    example(
        "sibling",
        "sibling_isolation",
        "Alternative data adapters import neither peer.",
        {
            "src/data/remote.ts": appended(
                "src/data/remote.ts", 'import { local } from "./local";\n'
            )
        },
        ("DATA-PEERS",),
    ),
    example(
        "allowed-pair",
        "allowed_dependency",
        "A permission records a decision and creates no violation.",
        {
            "architecture-contract.json": with_rule(
                "allowed_dependency", source="shop.src.data", target="shop.src.domain"
            )
        },
    ),
    example(
        "external-allowed",
        "external_dependency_scope",
        "The data layer may import the declared scoped package.",
        {"src/data/remote.ts": appended("src/data/remote.ts", 'import "@shop/transport";\n')},
    ),
    example(
        "external-forbidden",
        "external_dependency_scope",
        "The domain may not import the scoped transport package.",
        {"src/domain/order.ts": appended("src/domain/order.ts", 'import "@shop/transport";\n')},
        ("EXTERNAL-SHOP",),
    ),
    example(
        "undeclared-external",
        "complete_external_scope",
        "An external dependency needs an explicit scope decision.",
        {"src/data/remote.ts": appended("src/data/remote.ts", 'import "unreviewed-package";\n')},
        ("EXTERNAL-COMPLETE",),
    ),
    example(
        "external-names",
        "external_dependency_scope:package_names",
        "Scoped subpaths, hyphens and dots preserve package identity.",
        {
            "architecture-contract.json": _external_names(),
            "src/data/remote.ts": appended(
                "src/data/remote.ts",
                'import "@shop/transport/client";\n'
                'import "transport-client";\n'
                'import "transport.client";\n',
            ),
        },
    ),
    example(
        "builtin",
        "complete_external_scope:builtin",
        "A proven Node builtin needs no external package scope rule.",
        {"src/data/remote.ts": appended("src/data/remote.ts", 'import "node:fs";\n')},
    ),
    example(
        "module-interface",
        "interface_boundary",
        "A structural module boundary uses whole-module public entries.",
        {"architecture-contract.json": json.dumps(_interfaces())},
    ),
    example(
        "private-module",
        "interface_boundary",
        "Presentation imports a module outside the declared domain facade.",
        {
            "architecture-contract.json": json.dumps(_interfaces()),
            "src/presentation/page.ts": appended(
                "src/presentation/page.ts", 'import type { Order } from "../domain/order";\n'
            ),
        },
        ("PROBE",),
    ),
    example(
        "computed-import",
        "unknown_positions",
        "Computed imports cannot prove complete dependency absence.",
        {
            "src/main.ts": appended(
                "src/main.ts", "export const load = (name: string) => import(name);\n"
            )
        },
        unknown=True,
        gap=True,
    ),
    example(
        "unsupported-target-symbol",
        "forbidden_dependency:target_symbol",
        "Import-only facts do not establish symbol usage.",
        {
            "architecture-contract.json": with_rule(
                "forbidden_dependency",
                source="shop.src.presentation",
                target="shop.src.domain",
                target_symbol="Order",
                include_type_checking=True,
            )
        },
        refused=True,
    ),
    example(
        "mixed-known-and-unknown",
        "known_and_unknown",
        "A known forbidden dependency remains visible beside a computed import.",
        {
            "src/domain/order.ts": appended(
                "src/domain/order.ts", 'import type { local } from "../data/local";\n'
            ),
            "src/main.ts": appended(
                "src/main.ts", "export const load = (name: string) => import(name);\n"
            ),
        },
        ("COMPONENT-CYCLES", "DOMAIN-NO-DATA", "MODULE-CYCLES", "REQUIRES"),
        codes=("closed_world.observed_forbidden", "graph.drift"),
        gap=True,
    ),
    *(
        example(
            f"unsupported-{kind}",
            kind,
            "The import-only profile refuses symbol or statement semantics.",
            {"architecture-contract.json": with_rule(kind, **fields)},
            refused=True,
        )
        for kind, fields in UNSUPPORTED_RULES.items()
    ),
    *(
        Variant(
            id=f"typescript-unsupported-budget-{name}",
            section="validation",
            item=f"typescript:measurement:{name}",
            summary="An unmeasured scalar cannot satisfy a budget.",
            files=_budget(name),
            expected_violations=(),
            expected_codes=(),
            expected_kinds=("rule_unsupported_by_profile",),
            baseline="architecture-baseline.json",
            fixture=TYPESCRIPT_FIXTURE_DIR,
        )
        for name in UNMEASURED
    ),
    example(
        "unsupported-nested-symbol-rule",
        "boundary_types:nested",
        "A nested contract cannot acquire symbol capabilities the root profile lacks.",
        _nested_symbol_rule(),
        refused=True,
    ),
    example(
        "unsupported-symbol-interface",
        "interface_boundary:symbol",
        "A whole-module boundary does not prove a named symbol facade.",
        {"architecture-contract.json": _symbol_interface()},
        refused=True,
    ),
    example(
        "unsupported-symbol-requires",
        "complete_requires:symbol",
        "A declared import route cannot prove which exported symbol was used.",
        {"architecture-contract.json": _symbol_requires()},
        refused=True,
    ),
    example(
        "unsupported-facade-budget",
        "measurement:facade_names",
        "Unobserved exported symbols cannot satisfy a facade-name budget.",
        {"architecture-contract.json": _name_budget(coupling=False)},
        refused=True,
    ),
    example(
        "unsupported-coupling-budget",
        "measurement:coupling_names",
        "Import-graph edges do not measure imported facade names.",
        {"architecture-contract.json": _name_budget(coupling=True)},
        refused=True,
    ),
    Variant(
        id="typescript-syntax-error",
        section="validation",
        item="typescript:coverage_failures",
        summary="Malformed source cannot produce complete measurements.",
        files={"src/domain/order.ts": "export const = ;\n"},
        expected_violations=(),
        expected_codes=(),
        expected_kinds=("parse_error",),
        fixture=TYPESCRIPT_FIXTURE_DIR,
    ),
)

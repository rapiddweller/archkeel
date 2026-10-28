# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""TypeScript source-only rule examples and explicit limits."""

from __future__ import annotations

import json
from pathlib import Path

from archkeel.ir.contract_version import ContractVersion
from archkeel.ir.model import DiagnosticCode
from fixtures.demo_catalog_support import Variant, contract_measurement_budgets

TYPESCRIPT_FIXTURE_DIR = Path(__file__).resolve().parent / "H-typescript"


def contract() -> dict:
    return json.loads((TYPESCRIPT_FIXTURE_DIR / "architecture-contract.json").read_text())


def with_rule(kind: str, **fields: object) -> str:
    value = contract()
    if kind in UNSUPPORTED_RULES:
        # The newest contract admits every kind, so only the TypeScript profile can refuse it.
        value["schema_version"] = tuple(ContractVersion)[-1]
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
        expected_declared_rules=None if refused else "FAIL" if violations else "UNKNOWN",
        fixture=TYPESCRIPT_FIXTURE_DIR,
    )


def _bundler_package(*, asset: bool) -> dict[str, str]:
    """A bundler-mode project that imports a stylesheet through a package `exports` map."""
    files = {
        "tsconfig.json": json.dumps(
            {
                "compilerOptions": {
                    "target": "ES2022",
                    "module": "ESNext",
                    "moduleResolution": "Bundler",
                    "strict": True,
                    "noEmit": True,
                },
                "include": ["src/**/*.ts"],
            },
            indent=2,
        )
        + "\n",
        "archkeel.toml": (TYPESCRIPT_FIXTURE_DIR / "archkeel.toml").read_text()
        + "bundler = true\n",
        "resolver-inputs/styled/package.json": json.dumps(
            {
                "name": "styled",
                "version": "1.0.0",
                "exports": {
                    ".": {"types": "./dist/index.d.ts", "default": "./dist/index.js"},
                    "./dist/styles.css": "./dist/styles.css",
                },
            }
        ),
        "resolver-inputs/styled/dist/index.d.ts": "export declare const sheet: number;\n",
        "src/main.ts": appended("src/main.ts", 'import "styled/dist/styles.css";\n'),
    }
    if asset:
        files["resolver-inputs/styled/dist/styles.css"] = ""
    return files


def _tsconfig(**options: object) -> str:
    """The fixture TSConfig with extra compiler options."""
    value = json.loads((TYPESCRIPT_FIXTURE_DIR / "tsconfig.json").read_text())
    value["compilerOptions"].update(options)
    return json.dumps(value, indent=2) + "\n"


def _global_use(name: str) -> str:
    return appended("src/main.ts", f"export const global_{name.lower()} = {name};\n")


UNSUPPORTED_RULES = {
    "protocol_declarations": {
        "source": "shop",
        "protocol": "shop.Port",
        "selectors": [
            {"role": "parameter", "name": "port", "visibility": "all", "optional": False}
        ],
    },
    "bounded_numeric_operand": {
        "source": "shop",
        "form": "both",
        "terminal_suffix": "nonce",
        "minimum_value": 4,
    },
    "call_owner": {"source": "shop", "target": "shop.src.main_x2e_ts.main"},
    "forbidden_call_argument": {
        "source": "shop",
        "target": "shop.src.main_x2e_ts.main",
        "parameter": "query",
    },
    "catalog_argument": {
        "source": "shop",
        "target": "shop.src.main_x2e_ts.main",
        "parameter": "query",
        "catalog": "shop.src.domain.Kind",
    },
    "catalog_use": {
        "source": "shop",
        "target": "shop.src.main_x2e_ts.main",
        "parameter": "query",
        "catalog": "shop.src.domain.Kind",
    },
    "forbidden_effect_under_condition": {
        "source": "shop",
        "target": "shop.src.main_x2e_ts.main",
        "condition": {"kind": "parameter", "owner": "shop.src.main_x2e_ts.main", "name": "seeded"},
    },
    "forbidden_construct": {
        "source": "shop",
        "constructs": ["string_literal_compare"],
        "selector": {
            "receiver": "shop.src.domain.Connection",
            "member": "backend",
            "role": "equality",
            "literal": "flat",
        },
    },
    "symbol_placement": {
        "source": "shop",
        "class_kinds": ["class"],
        "allowed_sources": ["shop.src.domain"],
    },
    "boundary_types": {"source": "shop"},
    "source_ownership": {
        "source": "shop",
        "mode": "retired",
        "symbols": ["shop.src.old"],
        "roles": ["read"],
    },
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
    "layer_order": ("layer-order-positive", "layer-order-forbidden-permission"),
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
    "unknown_positions": ("clean", "computed-import", "indirect-require"),
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


def _layer_order(*, outer_permission: bool) -> str:
    value = json.loads(with_rule("layer_order", layers=["Core", "Edge"]))
    value["schema_version"] = "2.3.0"
    for component in value["components"]:
        component["layer"] = "Core" if component["label"] == "domain" else "Edge"
        if component["label"] == "domain" and outer_permission:
            component["requires"] = [
                {"component": "presentation", "rationale": "Probe an outer layer permission."}
            ]
    return json.dumps(value, indent=2) + "\n"


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
        "layer-order-positive",
        "layer_order",
        "Edge components require only their own layer or Core.",
        {"architecture-contract.json": _layer_order(outer_permission=False)},
    ),
    example(
        "layer-order-forbidden-permission",
        "layer_order",
        "Core declares an Edge permission without importing it; the layer rule rejects it.",
        {"architecture-contract.json": _layer_order(outer_permission=True)},
        ("PROBE",),
    ),
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
        gap=True,
    ),
    example(
        "indirect-require",
        "unknown_positions",
        "An indirect CommonJS loader cannot prove dependency absence.",
        {
            "src/main.ts": appended(
                "src/main.ts", "module.require.call(module, './hidden.cjs');\n"
            ),
            "src/hidden.cjs": "module.exports = 7;\n",
        },
        gap=True,
    ),
    example(
        "unsupported-target-symbol",
        "forbidden_dependency:target_symbol",
        "Type-only reexports do not establish the requested runtime symbol route.",
        {
            "architecture-contract.json": with_rule(
                "forbidden_dependency",
                source="shop.src.presentation",
                target="shop.src.domain",
                target_symbol="Order",
                include_type_checking=True,
            )
        },
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
        "Private repository imports fail while the type-only named facade remains undecided.",
        {"architecture-contract.json": _symbol_interface()},
        ("PROBE", "PROBE"),
    ),
    example(
        "unsupported-symbol-requires",
        "complete_requires:symbol",
        "A type-only reexport does not prove the declared runtime symbol route.",
        {"architecture-contract.json": _symbol_requires()},
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
    # AD-274 (#682, #721): `types` adds globals, and a project `declare` publishes its name.
    example(
        "types-keep-the-catalog",
        "standard_globals:types",
        "A `types` entry keeps `Math` and `document` proven; the project is complete.",
        {
            "tsconfig.json": _tsconfig(lib=["ES2023", "DOM"], types=["vite/client"]),
            "src/main.ts": appended(
                "src/main.ts", "export const m = Math.max(1, 2);\nexport const d = document;\n"
            ),
        },
    ),
    example(
        "types-unlisted-global",
        "standard_globals:types_unlisted",
        "A name that only a types package adds stays a gap.",
        {
            "tsconfig.json": _tsconfig(lib=["ES2023", "DOM"], types=["node"]),
            "src/main.ts": _global_use("process"),
        },
        gap=True,
    ),
    example(
        "declared-global",
        "standard_globals:declared",
        "A `declare global` block publishes its name for every file.",
        {
            "src/domain/order.ts": appended(
                "src/domain/order.ts", "declare global { const __APP_VERSION__: string; }\n"
            ),
            "src/main.ts": _global_use("__APP_VERSION__"),
        },
    ),
    example(
        "declared-global-in-a-module",
        "standard_globals:declared_in_module",
        "A top-level `declare const` in a file with `export` is local and publishes nothing.",
        {
            "src/domain/order.ts": appended(
                "src/domain/order.ts", "declare const __APP_VERSION__: string;\n"
            ),
            "src/main.ts": _global_use("__APP_VERSION__"),
        },
        gap=True,
    ),
    example(
        "module-binding-is-not-a-publication",
        "standard_globals:module_binding",
        "A module-local `function open` does not make `window.open` a second publication.",
        {
            "src/domain/order.ts": appended(
                "src/domain/order.ts", "function open(n: number): number { return n + 1; }\n"
            ),
            "src/main.ts": appended(
                "src/main.ts", "export const go = () => window.open('/x', '_blank');\n"
            ),
        },
    ),
    example(
        "module-local-write-is-not-a-global-write",
        "standard_globals:module_local_write",
        "A write to a module-local `let open` does not write `window.open`.",
        {
            "src/domain/order.ts": appended(
                "src/domain/order.ts",
                "let open = false;\nexport function toggle(): void { open = !open; }\n",
            ),
            "src/main.ts": appended(
                "src/main.ts", "export const go = () => window.open('/x', '_blank');\n"
            ),
        },
    ),
    example(
        "module-binding-and-global-write",
        "standard_globals:module_binding_global_write",
        "A module that binds `open` and writes `window.open` still writes the global.",
        {
            "src/domain/order.ts": appended(
                "src/domain/order.ts",
                "let open = false;\n"
                "export function toggle(): void { open = !open; window.open = () => null; }\n",
            ),
            "src/main.ts": appended(
                "src/main.ts", "export const go = () => window.open('/x', '_blank');\n"
            ),
        },
        gap=True,
    ),
    # #728: a package that exports an asset is an edge to its package in bundler mode.
    example(
        "bundler-exported-asset",
        "bundler:exported_asset",
        "A stylesheet that a package exports is an edge to the package, so the package is seen.",
        _bundler_package(asset=True),
        ("EXTERNAL-COMPLETE",),
    ),
    example(
        "bundler-exported-asset-missing",
        "bundler:exported_asset_missing",
        "An exported stylesheet that is not installed stays an unresolved import.",
        _bundler_package(asset=False),
        gap=True,
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

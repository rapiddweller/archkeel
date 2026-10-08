# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Independent inner Target intent exercised through the ordinary CLI."""

import json
from pathlib import Path
from typing import get_args

from archkeel.ir.architecture_graph import EntityKind, RelationshipKind
from archkeel.ir.model import stable_id
from fixtures.demo_catalog_support import Variant

UML_FIXTURE_DIR = Path(__file__).resolve().parent / "H-uml"
CORE_SOURCE = (UML_FIXTURE_DIR / "demo/core.py").read_text()

VARIANTS = tuple(
    Variant(
        id=identity,
        section="class_c",
        item="ContractDeclarations.uml",
        summary=summary,
        files=files,
        expected_violations=(stable_id("UML-TARGET", "architecture-contract.json"),)
        if status == "FAIL"
        else (),
        expected_codes=("rule.violated",) if status == "FAIL" else (),
        expected_declared_rules=status,
        fixture=UML_FIXTURE_DIR,
    )
    for identity, summary, files, status in (
        ("uml-match", "Independent inner intent matches recorded Python facts.", {}, "PASS"),
        (
            "uml-mismatch",
            "A changed operation return type fails the independent signature.",
            {
                "demo/core.py": CORE_SOURCE.replace(
                    "def run(self, value: int) -> str:\n        return helper(value)",
                    "def run(self, value: int) -> int:\n        return helper(value)",
                )
            },
            "FAIL",
        ),
        (
            "uml-partial",
            "Dynamic enum generation leaves literal existence UNKNOWN.",
            {
                "demo/core.py": CORE_SOURCE.replace(
                    "from enum import Enum", "from enum import Enum, auto"
                ).replace('READY = "ready"', "READY = auto()")
            },
            "UNKNOWN",
        ),
    )
)


# Extend authored intent, never the observation, so the matching demo stays an open-scope control.
complete_contract = json.loads((UML_FIXTURE_DIR / "architecture-contract.json").read_text())
complete_uml = complete_contract["declarations"]["uml"]
complete_uml["entities"].append(
    {
        "id": "init-module",
        "kind": "module",
        "qualified_name": "demo",
        "parent_id": "demo-component",
        "language": "python",
        "presence": "planned",
        "file_path": "demo/__init__.py",
        "responsibilities": ["Initialize the demo namespace."],
        "provenance": ["docs/target.md"],
    }
)
for identity, name in (
    ("namespace", "demo"),
    ("core-namespace", "demo.core"),
    ("app-namespace", "demo.app"),
):
    complete_uml["entities"].append(
        {
            "id": identity,
            "kind": "package",
            "qualified_name": name,
            "language": "python",
            "presence": "planned",
            "responsibilities": ["Group the " + name + " namespace."],
            "provenance": ["docs/target.md"],
        }
    )
for identity, name in (
    ("protocol", "typing.Protocol"),
    ("str", "builtins.str"),
    ("enum-base", "enum.Enum"),
    ("enum-library", "enum"),
    ("typing-library", "typing"),
):
    complete_uml["entities"].append(
        {
            "id": identity,
            "kind": "symbol",
            "qualified_name": name,
            "language": "python",
            "presence": "referenced",
            "provenance": ["docs/target.md"],
        }
    )
complete_uml["entities"].append(
    {
        "id": "describe",
        "kind": "function",
        "qualified_name": "demo.core.describe",
        "parent_id": "core-module",
        "language": "python",
        "presence": "planned",
        "responsibilities": ["Describe the ready state and demo version."],
        "visibility": {"kind": "public", "basis": "declared"},
        "signature": {"parameters": [], "returns": "str"},
        "provenance": ["docs/target.md"],
    }
)
for identity, kind, source, target in (
    ("describe-state", "references", "describe", "state"),
    ("describe-version", "references", "describe", "version"),
    ("helper-str", "calls", "helper", "str"),
    ("build-unit-call", "calls", "build", "unit"),
    ("port-protocol", "inherits", "port", "protocol"),
    ("state-enum", "inherits", "state", "enum-base"),
    ("core-port-reference", "references", "core-module", "port"),
    ("core-base-reference", "references", "core-module", "base"),
    ("core-enum-import", "imports", "core-module", "enum-library"),
    ("core-typing-import", "imports", "core-module", "typing-library"),
    ("namespace-init", "owns", "namespace", "init-module"),
    ("namespace-core", "owns", "core-namespace", "core-module"),
    ("namespace-app", "owns", "app-namespace", "app-module"),
):
    complete_uml["relationships"].append(
        {
            "id": identity,
            "kind": kind,
            "source_id": source,
            "target_id": target,
            "provenance": ["docs/target.md"],
        }
    )
for scope in ("demo-component", "init-module", "core-module", "app-module"):
    complete_uml["scopes"].append(
        {
            "scope_id": scope,
            "mode": "closed",
            "rationale": "Declare every static demo definition and use.",
            "provenance": ["docs/target.md"],
            "entity_kinds": [
                kind for kind in get_args(EntityKind) if kind not in {"component", "symbol"}
            ],
            "relationship_kinds": [
                kind for kind in get_args(RelationshipKind) if kind not in {"requires", "publishes"}
            ],
        }
    )
complete_contract["declarations"]["modules"] = [
    {"path": entity["file_path"], "responsibility": entity["responsibilities"][0]}
    for entity in complete_uml["entities"]
    if entity["kind"] == "module"
]
VARIANTS += (
    Variant(
        id="uml-complete",
        section="class_c",
        item="ContractDeclarations.uml",
        summary="Closed static Target with internal uses; incomplete observation stays UNKNOWN.",
        files={
            "architecture-contract.json": json.dumps(complete_contract, indent=2) + "\n",
            "demo/core.py": CORE_SOURCE
            + '\n\ndef describe() -> str:\n    return f"{State.READY}:v{VERSION}"\n',
        },
        expected_violations=(),
        expected_codes=(),
        expected_declared_rules="UNKNOWN",
        fixture=UML_FIXTURE_DIR,
    ),
)


DART_FIXTURE_DIR = UML_FIXTURE_DIR.with_name("H-uml-dart")
DART_ORDER_SOURCE = (DART_FIXTURE_DIR / "lib/ordering/domain/orders/order.dart").read_text()
DART_DISCOUNT_SOURCE = (
    DART_FIXTURE_DIR / "lib/ordering/domain/pricing/discount_policy.dart"
).read_text()
DART_BASE = {
    "section": "class_c",
    "item": "ContractDeclarations.uml",
    "fixture": DART_FIXTURE_DIR,
}
VARIANTS += (
    Variant(
        id="uml-dart-match",
        summary="Native Dart source matches its independently authored nested Target.",
        files={},
        expected_violations=(),
        expected_codes=(),
        expected_declared_rules="PASS",
        **DART_BASE,
    ),
    Variant(
        id="uml-dart-signature-fail",
        summary="A deep Order method signature differs from the unchanged Target.",
        files={
            "lib/ordering/domain/orders/order.dart": DART_ORDER_SOURCE.replace(
                "isValidQuantity(int quantity)", "isValidQuantity(num quantity)"
            )
        },
        expected_violations=(stable_id("UML-TARGET", "architecture-contract.json"),),
        expected_codes=("rule.violated",),
        expected_declared_rules="FAIL",
        **DART_BASE,
    ),
    Variant(
        id="uml-dart-missing-member-fail",
        summary="A Target-only enum literal is absent from valid Dart source.",
        files={
            "lib/ordering/domain/orders/order.dart": DART_ORDER_SOURCE.replace(
                "enum OrderStatus { draft, placed, cancelled }",
                "enum OrderStatus { draft, placed }",
            )
        },
        expected_violations=(stable_id("UML-TARGET", "architecture-contract.json"),),
        expected_codes=("rule.violated",),
        expected_declared_rules="FAIL",
        **DART_BASE,
    ),
    Variant(
        id="uml-dart-forbidden-dependency-fail",
        summary="Order source adds an unapproved cross-component pricing dependency.",
        files={
            "lib/ordering/domain/orders/order.dart": "import '../pricing/discount_policy.dart';\n"
            + DART_ORDER_SOURCE
            + "\nint previewDiscount(DiscountPolicy policy, int cents) => "
            "policy.discountCents(cents);\n"
        },
        expected_violations=("ordering:domain:REQUIRES-COMPLETE",),
        expected_codes=("rule.violated",),
        expected_declared_rules="FAIL",
        **DART_BASE,
    ),
    Variant(
        id="uml-dart-partial-unknown",
        summary="A dynamic receiver leaves one Target-required call unresolved.",
        files={
            "lib/ordering/domain/pricing/discount_policy.dart": DART_DISCOUNT_SOURCE.replace(
                "int discountCents(int subtotalCents) => super.clampDiscount(\n    subtotalCents,",
                "int discountCents(int subtotalCents) {\n"
                "    final dynamic base = this;\n"
                "    return base.clampDiscount(\n    subtotalCents,",
            ).replace(
                "subtotalCents * _percent.clamp(0, MAX_DISCOUNT_PERCENT) ~/ 100,\n  );",
                "subtotalCents * _percent.clamp(0, MAX_DISCOUNT_PERCENT) ~/ 100,\n  );\n  }",
            )
        },
        expected_violations=(),
        expected_codes=(),
        expected_declared_rules="UNKNOWN",
        **DART_BASE,
    ),
)

for language in ("typescript",):
    fixture = UML_FIXTURE_DIR.with_name("H-uml-" + language)
    VARIANTS += (
        Variant(
            id="uml-" + language,
            section="class_c",
            item="ContractDeclarations.uml",
            summary="Independent " + language + " intent; incomplete inner coverage stays UNKNOWN.",
            files={},
            expected_violations=(),
            expected_codes=(),
            expected_declared_rules="UNKNOWN",
            fixture=fixture,
        ),
    )


TS_FIXTURE_DIR = UML_FIXTURE_DIR.with_name("H-uml-typescript")
TS_CONTRACT = json.loads((TS_FIXTURE_DIR / "architecture-contract.json").read_text())
TS_CLOSED_CONTRACT = json.loads(json.dumps(TS_CONTRACT))
TS_UML = TS_CLOSED_CONTRACT["declarations"]["uml"]
TS_UML["scopes"] = [
    {
        "scope_id": scope_id,
        "mode": "closed",
        "entity_kinds": kinds,
        "rationale": "Declare the complete classifier member inventory recorded by the analyzer.",
        "provenance": ["docs/target.md"],
    }
    for scope_id, kinds in (
        ("client", ["attribute", "method"]),
        ("state", ["enum_literal"]),
        ("base", ["attribute", "method"]),
        ("unit", ["attribute", "method"]),
        ("port", ["attribute", "method"]),
    )
]
TS_CORE_SOURCE = (TS_FIXTURE_DIR / "src/core.ts").read_text()
TS_MATCH_SOURCE = TS_CORE_SOURCE.replace("return String(value);", "return `${value}`;")
TS_MISMATCH_SOURCE = TS_CORE_SOURCE.replace(
    "static reset(): void {}",
    "static reset(): number { return 0; }",
)
TS_PARTIAL_SOURCE = TS_CORE_SOURCE.replace(
    "const item = new Unit();",
    "const constructors = [Unit];\n  const item = new constructors[0]();",
)
TS_CLOSED_CONTRACT_JSON = json.dumps(TS_CLOSED_CONTRACT, indent=2) + "\n"
VARIANTS += (
    Variant(
        id="uml-typescript-match",
        section="class_c",
        item="ContractDeclarations.uml",
        summary="TypeScript source matches the independently declared classifier contract.",
        files={
            "architecture-contract.json": TS_CLOSED_CONTRACT_JSON,
            "src/core.ts": TS_MATCH_SOURCE,
        },
        expected_violations=(),
        expected_codes=(),
        expected_declared_rules="PASS",
        fixture=TS_FIXTURE_DIR,
    ),
    Variant(
        id="uml-typescript-mismatch",
        section="class_c",
        item="ContractDeclarations.uml",
        summary="A changed TypeScript static method return type fails its independent signature.",
        files={
            "architecture-contract.json": TS_CLOSED_CONTRACT_JSON,
            "src/core.ts": TS_MISMATCH_SOURCE,
        },
        expected_violations=(stable_id("UML-TARGET", "architecture-contract.json"),),
        expected_codes=("rule.violated",),
        expected_declared_rules="FAIL",
        fixture=TS_FIXTURE_DIR,
    ),
    Variant(
        id="uml-typescript-partial",
        section="class_c",
        item="ContractDeclarations.uml",
        summary="A computed TypeScript constructor keeps the result UNKNOWN.",
        files={
            "architecture-contract.json": TS_CLOSED_CONTRACT_JSON,
            "src/core.ts": TS_PARTIAL_SOURCE,
        },
        expected_violations=(),
        expected_codes=(),
        expected_declared_rules="UNKNOWN",
        fixture=TS_FIXTURE_DIR,
    ),
)

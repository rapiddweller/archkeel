# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Shared primitives for the AD-11 demo catalog family modules.

They live apart from `architecture_demo.py` because that module imports every family module.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from archkeel.ir.model import DiagnosticCode, DiagnosticKind

FIXTURE_DIR = Path(__file__).resolve().parent / "F-architecture"
Section = Literal[
    "showcase", "clean", "class_a", "validation", "class_b", "protocol", "class_c", "class_d"
]
HEADER = (
    "# Archkeel\n# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.\n# SPDX-License-Identifier: MIT\n"
)
CLEAN_SHOP_MD = (FIXTURE_DIR / "docs/architecture/shop.md").read_text()


# Named after the check_git_order and check_order predicate each scenario keeps or breaks,
# except "empty_declaration", named after the AD-39 declaration it demonstrates instead.
CheckScenario = Literal[
    "ordered", "published_after_candidate", "candidate_changed_expectation", "empty_declaration"
]


@dataclass(frozen=True, slots=True)
class CheckExpectation:
    """Typed M/B/E/H check-protocol outcome: verdicts and the regressed measurement names."""

    scenario: CheckScenario
    exit_code: Literal[0, 1]
    expectation_fulfilled: Literal["PASS", "FAIL"]
    git_predicate: Literal["PASS", "FAIL"]
    host_order: Literal["PASS", "FAIL"]
    regressed_scalars: tuple[str, ...] = ()
    regressed_dimensions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Variant:
    """One catalogued demonstration: an overlay on the clean sample, or cited evidence."""

    id: str
    section: Section
    item: str
    summary: str
    files: Mapping[str, str | None]
    expected_violations: tuple[str, ...]
    expected_codes: tuple[DiagnosticCode, ...]
    expected_kinds: tuple[DiagnosticKind, ...] = ()
    evidence: str | None = None
    check: CheckExpectation | None = None


def apply_overlay(root: Path, files: Mapping[str, str | None]) -> None:
    """Materialize one variant's file changes over a copy of the clean shop sample."""
    for relative, content in files.items():
        target = root / relative
        if content is None:
            target.unlink()
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)


def _clean_contract() -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / "architecture-contract.json").read_text())


def _dump_contract(contract: dict[str, Any]) -> str:
    return json.dumps(contract, indent=2) + "\n"


def contract_rule_field(rule_id: str, **fields: object) -> str:
    """Clean contract JSON with one rule's fields overridden by id."""
    contract = _clean_contract()
    rule = next(item for item in contract["rules"] if item["id"] == rule_id)
    rule.update(fields)
    return _dump_contract(contract)


def contract_without_rule(rule_id: str) -> str:
    """Clean contract JSON with one rule removed by id."""
    contract = _clean_contract()
    contract["rules"] = [item for item in contract["rules"] if item["id"] != rule_id]
    return _dump_contract(contract)


def contract_with_rule(rule: dict[str, object]) -> str:
    """Clean contract JSON with one extra rule appended."""
    contract = _clean_contract()
    contract["rules"].append(rule)
    return _dump_contract(contract)


def contract_rule_replaced(rule_id: str, rule: dict[str, object]) -> str:
    """Clean contract JSON with one rule removed by id and a new rule appended.

    Keeps the pair decided (AD-15) when a demo probe removes the rule that decided it.
    """
    contract = _clean_contract()
    contract["rules"] = [item for item in contract["rules"] if item["id"] != rule_id]
    contract["rules"].append(rule)
    return _dump_contract(contract)


def contract_component_field_appended(label: str, field: str, value: object) -> str:
    """Clean contract JSON with one value appended to a component's list field."""
    contract = _clean_contract()
    component = next(item for item in contract["components"] if item["label"] == label)
    component[field] = [*component[field], value]
    return _dump_contract(contract)


def inside_requires_replaced(label: str, entries: list[dict[str, str]]) -> str:
    """The clean `shop.store` inside contract with one sub-component's `requires` replaced.

    Its own helper because the inside is a second file: a variant that changed both contracts
    would otherwise have to chain two helpers, and every helper here starts from the clean one.
    """
    contract = json.loads((FIXTURE_DIR / "shop/store/architecture-contract.json").read_text())
    component = next(item for item in contract["components"] if item["label"] == label)
    component["requires"] = entries
    return _dump_contract(contract)


def inside_contract(public: list[str], allowed_target: str | None = None) -> str:
    """A contract describing shop.store's inside, for the AD-20 level checks.

    One sub-component over `shop.store.repository`: `public` is the surface the inside
    declares, which the level above must declare identically, and `allowed_target` an edge
    the inside grants itself, which the level above may forbid to store.
    """
    rules: list[dict[str, object]] = []
    if allowed_target is not None:
        rules.append(
            {
                "id": "DEP-REPOSITORY-ALLOWS-RENDER",
                "kind": "allowed_dependency",
                "source": "shop.store.repository",
                "target": allowed_target,
                "rationale": "The inside grants an edge the level above denies to store.",
                "provenance": ["docs/architecture/shop.md"],
                "decided_by": "architect",
            }
        )
    return _dump_contract(
        {
            "schema_version": "2.1.0",
            "components": [
                {
                    "id": "COMP-REPOSITORY",
                    "label": "repository",
                    "role": "component",
                    "packages": ["shop.store.repository"],
                    "responsibilities": [],
                    "forbidden_responsibilities": [],
                    "provenance": ["docs/architecture/shop.md"],
                    "public": public,
                }
            ],
            "rules": rules,
        }
    )


def contract_with_requires(
    requires: dict[str, list[dict[str, str]]], rule: dict[str, object]
) -> str:
    """Clean contract JSON with a `requires` list per named component and one extra rule.

    The two travel together because every helper here starts from the clean contract and
    returns finished JSON, so a variant cannot chain two of them (AD-32).
    """
    contract = _clean_contract()
    for component in contract["components"]:
        entries = requires.get(component["label"])
        if entries is not None:
            component["requires"] = entries
    contract["rules"].append(rule)
    return _dump_contract(contract)


def contract_component_field_set(label: str, field: str, value: object) -> str:
    """Clean contract JSON with one component field replaced by label."""
    contract = _clean_contract()
    component = next(item for item in contract["components"] if item["label"] == label)
    component[field] = value
    return _dump_contract(contract)


def contract_without_component_field(label: str, field: str) -> str:
    """Clean contract JSON with one component field removed by label."""
    contract = _clean_contract()
    component = next(item for item in contract["components"] if item["label"] == label)
    del component[field]
    return _dump_contract(contract)


def contract_rule_provenance_appended(rule_id: str, path: str) -> str:
    """Clean contract JSON with one extra provenance path appended to a rule."""
    contract = _clean_contract()
    rule = next(item for item in contract["rules"] if item["id"] == rule_id)
    rule["provenance"] = [*rule["provenance"], path]
    return _dump_contract(contract)


def contract_top_field(field: str, value: object) -> str:
    """Clean contract JSON with one top-level field replaced."""
    contract = _clean_contract()
    contract[field] = value
    return _dump_contract(contract)


def contract_without_top_field(field: str) -> str:
    """Clean contract JSON with one top-level field removed."""
    contract = _clean_contract()
    del contract[field]
    return _dump_contract(contract)

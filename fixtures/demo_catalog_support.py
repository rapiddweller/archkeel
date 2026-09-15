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


def contract_component_field_appended(label: str, field: str, value: object) -> str:
    """Clean contract JSON with one value appended to a component's list field."""
    contract = _clean_contract()
    component = next(item for item in contract["components"] if item["label"] == label)
    component[field] = [*component[field], value]
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

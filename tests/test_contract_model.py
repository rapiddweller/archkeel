# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Verify the typed Contract 2.0 structure parser."""

import json
from collections.abc import Iterator
from dataclasses import fields, is_dataclass
from pathlib import Path
from types import NoneType, UnionType
from typing import get_args, get_origin, get_type_hints

import pytest
from jsonschema import Draft202012Validator

from archkeel.ir.codec import contract_bytes, parse_contract
from archkeel.ir.model import ArchitectureContract, module_references

ROOT = Path(__file__).parents[1]
SCHEMA = json.loads((ROOT / "schema/architecture-contract.schema.json").read_bytes())
VALIDATOR = Draft202012Validator(SCHEMA)


@pytest.mark.parametrize("path", sorted((ROOT / "tests/contracts").glob("*/*.json")))
def test_contract_parser_matches_structure_corpus(path: Path) -> None:
    raw = json.loads(path.read_bytes())
    should_pass = path.parent.name == "valid"
    try:
        parse_contract(raw)
        parser_accepts = True
    except ValueError:
        parser_accepts = False
    schema_accepts = not list(VALIDATOR.iter_errors(raw))
    assert parser_accepts == schema_accepts == should_pass


@pytest.mark.parametrize(
    "path",
    [*sorted((ROOT / "tests/contracts/valid").glob("*.json")), ROOT / "architecture-contract.json"],
)
def test_contract_encoding_round_trips_and_matches_the_schema(path: Path) -> None:
    contract = parse_contract(json.loads(path.read_bytes()))
    encoded = json.loads(contract_bytes(contract))
    assert not list(VALIDATOR.iter_errors(encoded))
    assert parse_contract(encoded) == contract


def test_contract_schema_is_draft_2020_12() -> None:
    Draft202012Validator.check_schema(SCHEMA)


def test_contract_parser_rejects_distinct_records_with_duplicate_ids() -> None:
    raw = json.loads((ROOT / "tests/contracts/valid/minimal.json").read_bytes())
    raw["rules"][0]["id"] = raw["components"][0]["id"]
    with pytest.raises(ValueError, match="duplicate contract ID"):
        parse_contract(raw)


def test_component_namespace_round_trips_and_must_name_an_owned_package() -> None:
    raw = json.loads((ROOT / "tests/contracts/valid/minimal.json").read_bytes())
    raw["components"][0]["namespace"] = raw["components"][0]["packages"][0]
    contract = parse_contract(raw)
    assert contract.components[0].namespace == "sample.core"
    assert parse_contract(json.loads(contract_bytes(contract))) == contract

    raw["components"][0]["namespace"] = "sample.other"
    with pytest.raises(ValueError, match="must name one of"):
        parse_contract(raw)

    raw = json.loads((ROOT / "tests/contracts/valid/minimal.json").read_bytes())
    raw["components"].append({**raw["components"][0], "id": "COMP-DUP"})
    raw["components"][0]["namespace"] = "sample.core"
    with pytest.raises(ValueError, match="identify one component package"):
        parse_contract(raw)


@pytest.mark.parametrize("allowed_child", ["sample", "sample.core.nested", "other.core"])
def test_root_layout_requires_each_allowed_child_to_be_immediate(allowed_child: str) -> None:
    raw = json.loads((ROOT / "tests/contracts/valid/minimal.json").read_bytes())
    raw["rules"] = [
        {
            "id": "ROOT-LAYOUT",
            "kind": "root_layout",
            "root": "sample",
            "allowed_children": [allowed_child],
            "rationale": "Probe.",
            "provenance": ["docs/architecture/sample.md"],
            "decided_by": "architect",
        }
    ]
    with pytest.raises(ValueError, match="exactly one immediate child"):
        parse_contract(raw)


def test_root_layout_accepts_a_nested_package_root() -> None:
    raw = json.loads((ROOT / "tests/contracts/valid/minimal.json").read_bytes())
    raw["rules"] = [
        {
            "id": "ROOT-LAYOUT",
            "kind": "root_layout",
            "root": "sample.core",
            "allowed_children": ["sample.core.models"],
            "rationale": "Probe.",
            "provenance": ["docs/architecture/sample.md"],
            "decided_by": "architect",
        }
    ]
    contract = parse_contract(raw)
    assert contract.rules[0].root == "sample.core"


def test_boundary_type_allowance_is_exact_and_round_trips() -> None:
    raw = json.loads((ROOT / "tests/contracts/valid/minimal.json").read_bytes())
    raw["rules"] = [
        {
            "id": "BOUNDARY-TYPES",
            "kind": "boundary_types",
            "source": "sample.core",
            "rationale": "Keep declared boundary types narrow.",
            "provenance": ["docs/architecture/sample.md"],
            "decided_by": "architect",
            "allowed_positions": [
                {
                    "qualified_name": "sample.core.api.run",
                    "position": "return",
                    "field_path": "payload",
                    "annotation": "dict[str, JsonValue]",
                }
            ],
        }
    ]

    contract = parse_contract(raw)
    encoded = json.loads(contract_bytes(contract))
    assert not list(VALIDATOR.iter_errors(encoded))
    assert parse_contract(encoded) == contract

    raw["rules"][0]["allowed_positions"][0]["annotation"] = "dict"
    assert list(VALIDATOR.iter_errors(raw))
    with pytest.raises(ValueError, match="annotation cannot allow bare dict"):
        parse_contract(raw)
    raw["rules"][0]["allowed_positions"][0]["annotation"] = "dict[str, JsonValue]"

    raw["rules"][0]["allowed_positions"][0]["field_path"] = ""
    with pytest.raises(ValueError, match="allowed_positions\\[0\\].field_path must not be empty"):
        parse_contract(raw)

    raw["rules"][0]["allowed_positions"][0]["field_path"] = "payload"
    raw["rules"][0]["allowed_positions"][0]["unexpected"] = True
    with pytest.raises(ValueError, match="fields mismatch"):
        parse_contract(raw)


_PROVENANCE = ["docs/architecture/shop.md"]


def _maximal_contract() -> dict[str, object]:
    """The shop contract with every rule kind and every optional field of every entry filled."""
    raw = json.loads((ROOT / "fixtures/F-architecture/architecture-contract.json").read_text())
    app = next(item for item in raw["components"] if item["id"] == "COMP-APP")
    app["planned"] = ["shop.app.refunds"]
    app["inside"] = "shop/app/architecture-contract.json"
    app["requires"] = [
        {
            "component": "model",
            "rationale": "Use cases build orders.",
            "through": ["shop.model.entities"],
            "decided_by": "architect",
        }
    ]
    rules = {item["id"]: item for item in raw["rules"]}
    rules["DEP-STORE-NO-MONEY"]["allowed_sources"] = ["shop.store.codec"]
    rules["CONSTRUCT-NO-BROAD-EXCEPT"]["allowed_sources"] = ["shop.cli"]
    rules["EXTERNAL-JSON-STORE"]["exact_sources"] = ["shop.store.codec"]
    rules["MODEL-TYPES-IN-ENTITIES"]["allowed_sources"] = ["shop.model"]
    rules["APP-TYPES-NOT-DICT"].update(
        allowed_sources=["shop.app"],
        exact_sources=["shop.app.orders"],
        allowed_positions=[
            {
                "qualified_name": "shop.app.orders.summarize",
                "position": "return",
                "field_path": "items.payload",
                "annotation": "dict[str, str]",
            }
        ],
    )
    raw["rules"] += [
        {
            "id": "MODEL-MODULES-ACYCLIC",
            "kind": "no_component_cycles",
            "level": "module",
            "components": ["model"],
            "rationale": "Modules stay layered.",
            "provenance": _PROVENANCE,
            "decided_by": "architect",
        },
        {
            "id": "REQUIRES-COMPLETE",
            "kind": "complete_requires",
            "include_type_checking": True,
            "rationale": "Every crossing is declared.",
            "provenance": _PROVENANCE,
            "decided_by": "architect",
        },
    ]
    declarations = raw["declarations"]
    declarations["compat"] = [
        {"module": "shop.model.legacy", "target": "shop.model.entities", "lifetime": "migration"}
    ]
    declarations["measurement_budgets"] = [{"name": "cycle_edges", "provenance": _PROVENANCE}]
    declarations["facade_budgets"] = [
        {"component": "model", "max_names": 5, "provenance": _PROVENANCE}
    ]
    declarations["coupling_budgets"] = [
        {"source": "app", "target": "model", "max_names": 3, "provenance": _PROVENANCE}
    ]
    return raw


def _held_types(hint: object) -> list[type]:
    """The dataclasses a field hint holds, through `| None` and `tuple[X, ...]`."""
    if type(hint) is UnionType:
        return [item for arg in get_args(hint) if arg is not NoneType for item in _held_types(arg)]
    if get_origin(hint) is tuple:
        return _held_types(get_args(hint)[0])
    return [hint] if isinstance(hint, type) and is_dataclass(hint) else []


def _unfilled(cls: type, entries: list[dict[str, object]], path: str) -> list[str]:
    """Every field of `cls`, and of the dataclasses it holds, that no entry carries."""
    unfilled = []
    hints = get_type_hints(cls)
    for field in fields(cls):
        key = "$schema" if field.name == "schema" else field.name
        present = [entry[key] for entry in entries if key in entry]
        if not present:
            unfilled.append(f"{path}.{field.name}")
            continue
        values = [
            value for item in present for value in (item if isinstance(item, list) else [item])
        ]
        held = _held_types(hints[field.name])
        for element in held:
            members = [value for value in values if isinstance(value, dict)]
            if len(held) > 1:  # a union, told apart by `kind`: the rule kinds
                kinds = get_args(get_type_hints(element)["kind"])
                members = [value for value in members if value["kind"] in kinds]
            unfilled += _unfilled(element, members, f"{path}.{field.name}.{element.__name__}")
    return unfilled


def _shape(document: dict[str, object], pointer: str) -> str:
    """`pointer` with list indexes as `*`, except a rule's, which is its kind."""
    shape: list[str] = []
    node: object = document
    for part in pointer.split("/")[1:]:
        if isinstance(node, list):
            node = node[int(part)]
            shape.append(node["kind"] if shape == ["rules"] else "*")
        elif isinstance(node, dict):
            node = node[part]
            shape.append(part)
    return "/" + "/".join(shape)


def _string_pointers(node: object, pointer: str = "") -> Iterator[str]:
    if isinstance(node, str):
        yield pointer
    elif isinstance(node, list):
        for index, item in enumerate(node):
            yield from _string_pointers(item, f"{pointer}/{index}")
    elif isinstance(node, dict):
        for key, item in node.items():
            yield from _string_pointers(item, f"{pointer}/{key}")


# Every string field that names no module or symbol: an id, label, kind, enum value, prose, a
# path or a component label. A new string field must join this set or `module_references`.
_NAMES_NO_MODULE = frozenset(
    {
        "/$schema",
        "/schema_version",
        *(
            f"/components/*/{field}"
            for field in (
                "id",
                "label",
                "role",
                "capability_id",
                "inside",
                "decided_by",
                "responsibilities/*",
                "forbidden_responsibilities/*",
                "provenance/*",
                "requires/*/component",
                "requires/*/rationale",
                "requires/*/decided_by",
            )
        ),
        *(
            f"/rules/{kind}/{field}"
            for kind in (
                "allowed_dependency",
                "boundary_types",
                "complete_assignment",
                "complete_external_scope",
                "complete_requires",
                "external_dependency_scope",
                "forbidden_construct",
                "forbidden_dependency",
                "interface_boundary",
                "no_component_cycles",
                "root_layout",
                "sibling_isolation",
                "symbol_placement",
            )
            for field in ("id", "kind", "rationale", "decided_by", "provenance/*")
        ),
        "/rules/forbidden_dependency/target_symbol",
        "/rules/forbidden_construct/constructs/*",
        "/rules/external_dependency_scope/dependency",
        "/rules/no_component_cycles/level",
        "/rules/no_component_cycles/components/*",
        "/rules/symbol_placement/class_kinds/*",
        "/rules/boundary_types/allowed_positions/*/position",
        "/rules/boundary_types/allowed_positions/*/field_path",
        "/rules/boundary_types/allowed_positions/*/annotation",
        *(
            f"/declarations/{field}"
            for field in (
                "capabilities/*/id",
                "capabilities/*/name",
                "capabilities/*/label",
                "capabilities/*/provenance/*",
                "review_scopes/*/id",
                "review_scopes/*/label",
                "review_scopes/*/parent_id",
                "review_scopes/*/provenance/*",
                "public_api_provenance/*",
                "public_commands/*/id",
                "public_commands/*/description",
                "public_commands/*/provenance/*",
                "context_roots_provenance/*",
                "paths/*/id",
                "paths/*/label",
                "paths/*/kind",
                "paths/*/provenance/*",
                "spot_owners/*/id",
                "spot_owners/*/label",
                "spot_owners/*/responsibility",
                "spot_owners/*/provenance/*",
                "compat/*/lifetime",
                "measurement_budgets/*/name",
                "measurement_budgets/*/provenance/*",
                "facade_budgets/*/component",
                "facade_budgets/*/provenance/*",
                "coupling_budgets/*/source",
                "coupling_budgets/*/target",
                "coupling_budgets/*/provenance/*",
            )
        ),
    }
)


def test_the_maximal_contract_fills_every_field() -> None:
    """The completeness test below only sees a field this contract fills."""
    document = json.loads(contract_bytes(parse_contract(_maximal_contract())))

    assert _unfilled(ArchitectureContract, [document], "contract") == []


def test_module_references_point_at_the_names_they_list() -> None:
    contract = parse_contract(_maximal_contract())
    document = json.loads(contract_bytes(contract))

    for item in module_references(contract):
        node: object = document
        for part in item.pointer.split("/")[1:]:
            node = node[int(part)] if isinstance(node, list) else node[part]  # type: ignore[index]
        assert node == item.value, item.pointer


def test_every_contract_string_is_a_module_reference_or_names_no_module() -> None:
    """AD-105: a rename is sound only if `module_references` lists every module-naming field."""
    contract = parse_contract(_maximal_contract())
    document = json.loads(contract_bytes(contract))
    listed = {_shape(document, item.pointer) for item in module_references(contract)}
    strings = {_shape(document, pointer) for pointer in _string_pointers(document)}

    assert listed.isdisjoint(_NAMES_NO_MODULE)
    assert strings == listed | _NAMES_NO_MODULE


def test_validate_holds_the_namespace_to_the_fields_it_held_before() -> None:
    """A command, path step, shim, allowance, layout or construct source is renamed, not held."""
    contract = parse_contract(_maximal_contract())
    document = json.loads(contract_bytes(contract))
    references = module_references(contract)

    assert {_shape(document, item.pointer) for item in references if not item.held} == {
        "/components/*/namespace",
        "/rules/forbidden_construct/allowed_sources/*",
        "/rules/forbidden_construct/exact_sources/*",
        "/rules/root_layout/root",
        "/rules/root_layout/allowed_children/*",
        "/rules/boundary_types/allowed_positions/*/qualified_name",
        "/declarations/public_commands/*/command",
        "/declarations/paths/*/steps/*",
        "/declarations/compat/*/module",
        "/declarations/compat/*/target",
    }

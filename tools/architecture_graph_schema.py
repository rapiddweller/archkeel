# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Generate the shared graph schema from its dataclasses."""

from __future__ import annotations

import argparse
import json
import types
from dataclasses import MISSING, fields, is_dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal, Union, get_args, get_origin, get_type_hints

from archkeel.ir.architecture_graph import (
    ArchitectureGraph,
    ArchitectureReport,
    GraphComparison,
    TargetDefinition,
)
from archkeel.ir.facts import MemberInventory
from archkeel.ir.model import ArchitectureContract


def _schema(root: type, name: str, title: str) -> dict[str, object]:
    definitions: dict[str, object] = {}

    def shape(annotation: object) -> dict[str, object]:
        if annotation is str:
            return {"type": "string"}
        if annotation is bool:
            return {"type": "boolean"}
        if annotation is int:
            return {"type": "integer"}
        if annotation is type(None):
            return {"type": "null"}
        if isinstance(annotation, type) and issubclass(annotation, StrEnum):
            return {"enum": [item.value for item in annotation]}
        origin, arguments = get_origin(annotation), get_args(annotation)
        if origin is Literal:
            return {"enum": list(arguments)}
        if origin in {types.UnionType, Union}:
            return {"anyOf": [shape(argument) for argument in arguments]}
        if origin is tuple and len(arguments) == 2 and arguments[1] is Ellipsis:
            return {"type": "array", "items": shape(arguments[0])}
        if isinstance(annotation, type) and is_dataclass(annotation):
            name = annotation.__name__
            if name not in definitions:
                definitions[name] = {}
                hints = get_type_hints(annotation)
                properties = {field.name: shape(hints[field.name]) for field in fields(annotation)}
                definitions[name] = {
                    "type": "object",
                    "properties": properties,
                    "required": [
                        field.name
                        for field in fields(annotation)
                        if field.default is MISSING
                        and field.default_factory is MISSING
                        or field.name == "schema_version"
                    ],
                    "additionalProperties": False,
                }
            return {"$ref": f"#/$defs/{name}"}
        raise TypeError(f"unsupported schema type: {annotation}")

    reference = shape(root)
    version = get_args(get_type_hints(root)["schema_version"])[0]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"urn:archkeel:{name}:{version}",
        "title": title,
        "$comment": (
            "Generated from archkeel.ir.architecture_graph. "
            "Reference, identity, evidence and containment "
            "checks also require the graph/comparison validators. "
            "This graph does not change the Observation wire format."
        ),
        **reference,
        "$defs": definitions,
    }


def graph_schema() -> dict[str, object]:
    return _schema(ArchitectureGraph, "architecture-graph", "Shared architecture graph")


def target_schema() -> dict[str, object]:
    return _schema(TargetDefinition, "architecture-target", "Independent UML declarations")


def comparison_schema() -> dict[str, object]:
    return _schema(GraphComparison, "architecture-comparison", "Evidence-backed UML comparison")


def report_schema() -> dict[str, object]:
    return _schema(ArchitectureReport, "architecture-report", "Shared architecture report boundary")


def member_inventory_schema() -> dict[str, object]:
    schema = _schema(MemberInventory, "source-member-inventory", "Source member inventory")
    schema["$comment"] = (
        "Generated from archkeel.ir.facts.MemberInventory. "
        "Status/reason, identity and owner checks also require the SourceFacts validators."
    )
    return schema


def _update_contract_schema(path: Path) -> None:
    schema = json.loads(path.read_bytes())
    versions = list(get_args(get_type_hints(ArchitectureContract)["schema_version"]))
    schema["$id"] = f"urn:archkeel:architecture-contract:{versions[-1]}"
    schema["description"] = (
        f"Contract {' / '.join(versions)} structure. Rule semantics are cataloged in docs/rules.md."
    )
    schema["properties"]["schema_version"] = {"enum": versions}
    schema["$defs"]["uml"] = target_schema()
    schema["$defs"]["declarations"]["properties"]["uml"] = {"$ref": "#/$defs/uml"}
    schema["allOf"] = [
        {
            "if": {"properties": {"schema_version": {"const": "2.1.0"}}},
            "then": {"properties": {"declarations": {"not": {"required": ["uml"]}}}},
        }
    ]
    path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")


def _update_source_profile_schema(path: Path) -> None:
    schema = json.loads(path.read_bytes())
    schema.setdefault("$defs", {})["member_inventory"] = member_inventory_schema()
    path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--comparison", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--source-inventory", type=Path)
    parser.add_argument("--source-profile", type=Path)
    args = parser.parse_args()
    output = args.output
    output.write_text(json.dumps(graph_schema(), indent=2) + "\n", encoding="utf-8")
    if args.contract is not None:
        _update_contract_schema(args.contract)
    if args.comparison is not None:
        args.comparison.write_text(
            json.dumps(comparison_schema(), indent=2) + "\n", encoding="utf-8"
        )
    if args.report is not None:
        args.report.write_text(json.dumps(report_schema(), indent=2) + "\n", encoding="utf-8")

    if args.source_inventory is not None:
        args.source_inventory.write_text(
            json.dumps(member_inventory_schema(), indent=2) + "\n", encoding="utf-8"
        )

    if args.source_profile is not None:
        _update_source_profile_schema(args.source_profile)


if __name__ == "__main__":
    main()

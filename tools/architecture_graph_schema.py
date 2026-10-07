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
    ComponentIntent,
    GraphComparison,
    TargetDefinition,
)
from archkeel.ir.architecture_projection import ArchitectureProjection
from archkeel.ir.facts import MemberInventory
from archkeel.ir.model import ArchitectureContract, Coverage, Diagnostic, FilteredViolation, Record
from archkeel.ir.report_projection import ArchitectureCommandEnvelope


def _schema(root: type, name: str, title: str) -> dict[str, object]:
    definitions: dict[str, object] = {}

    def shape(annotation: object) -> dict[str, object]:
        if annotation is Record:
            return {"$ref": "urn:archkeel:architecture-ir:common:1.2.0#/$defs/record"}
        if annotation is Coverage:
            return {"$ref": "urn:archkeel:architecture-ir:common:1.2.0#/$defs/coverage"}
        if annotation is Diagnostic:
            return {"$ref": "urn:archkeel:command-result:6.0.0#/$defs/diagnostic"}
        if annotation is FilteredViolation:
            return {"$ref": "urn:archkeel:command-result:6.0.0#/$defs/filteredViolation"}
        if annotation is float:
            return {"type": "number"}
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
        if origin is dict and len(arguments) == 2 and arguments[0] is str:
            return {"type": "object", "additionalProperties": shape(arguments[1])}
        if origin is tuple and len(arguments) == 2 and arguments[1] is Ellipsis:
            return {"type": "array", "items": shape(arguments[0])}
        if origin is tuple:
            return {
                "type": "array",
                "prefixItems": [shape(item) for item in arguments],
                "minItems": len(arguments),
                "maxItems": len(arguments),
            }
        if isinstance(annotation, type) and is_dataclass(annotation):
            name = annotation.__name__
            if name not in definitions:
                definitions[name] = {}
                hints = get_type_hints(annotation)
                properties = {field.name: shape(hints[field.name]) for field in fields(annotation)}
                if annotation is ComponentIntent:
                    properties["layer"] = {"type": "string", "pattern": "\\S"}
                definition: dict[str, object] = {
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
                if annotation is ArchitectureGraph:
                    definition["allOf"] = [
                        {
                            "if": {"properties": {"schema_version": {"enum": ["1.0.0", "1.1.0"]}}},
                            "then": {
                                "properties": {
                                    "component_intents": {"items": {"not": {"required": ["layer"]}}}
                                }
                            },
                        }
                    ]
                if annotation is ArchitectureReport:
                    definition["allOf"] = [
                        {
                            "if": {"properties": {"schema_version": {"const": "1.0.0"}}},
                            "then": {
                                "properties": {
                                    key: {
                                        "not": {
                                            "type": "object",
                                            "properties": {"schema_version": {"const": "1.2.0"}},
                                            "required": ["schema_version"],
                                        }
                                    }
                                    for key in ("observed", "target")
                                }
                            },
                        }
                    ]
                definitions[name] = definition
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


def projection_schema() -> dict[str, object]:
    schema = _schema(
        ArchitectureProjection, "architecture-projection", "Focused architecture projection"
    )
    schema["$comment"] = (
        "Generated from archkeel.ir.architecture_projection. Source authenticity "
        "and Core verdicts belong to the shared report boundary."
    )
    return schema


def command_schema() -> dict[str, object]:
    schema = _schema(
        ArchitectureCommandEnvelope, "architecture-command", "Focused architecture command"
    )
    schema["$comment"] = (
        "Default fields may be omitted. Selector names starting with dot or colon (or empty) "
        "are relative to selector_prefix, falling back to namespace. Public/planned group "
        "selectors by module, with symbol names or empty for the whole module. Module paths "
        "are relative to component.path; empty means that exact file. Required summaries group "
        "only internal class/method/type relationships by authenticated scope, kind, Core status "
        "and exact reasons; cross-component and interface relationships remain individual. "
        "Permission rule_ids exclude requires IDs already carried by the same component: "
        "allowed pairs restore those IDs by matching requires.target_id. Requires observed_imports "
        "count component-pair sites, not narrower through compliance. Numeric reasons index "
        "reasons. UNKNOWN rows [scopes, count] account for every uncertainty exactly once; "
        "empty scopes are global or unattributed. "
        "Permission rules carry original authenticated Core declarations and assessments. "
        "Allowed is a declared conditional permission, not permission for each import. "
        "Policy context retains ancestor levels/rules and peer ownership/public/planned selectors. "
        "Coverage and Core verdicts remain global under component filters."
    )
    definitions = schema["$defs"]
    if not isinstance(definitions, dict):
        raise TypeError("generated command schema has no definitions")
    component = definitions["ArchitectureComponentView"]
    view = definitions["ArchitectureCommandView"]
    if not isinstance(component, dict) or not isinstance(view, dict):
        raise TypeError("generated command schema has invalid architecture definitions")
    component_properties = component["properties"]
    component_required = component["required"]
    view_required = view["required"]
    permission_group = definitions["PermissionGroup"]
    if not isinstance(component_properties, dict) or not isinstance(component_required, list):
        raise TypeError("generated command schema has invalid component fields")
    if not isinstance(view_required, list):
        raise TypeError("generated command schema has invalid view fields")
    if not isinstance(permission_group, dict) or not isinstance(permission_group["required"], list):
        raise TypeError("generated command schema has invalid permission fields")

    # Compact JSON deliberately omits source detail from nested/filtered rows. Keep
    # the complete dataclass shape mandatory in the explicit --full variant.
    full_component_required = list(component_required)
    full_permission_required = list(permission_group["required"])
    permission_group["required"] = [name for name in full_permission_required if name != "reason"]
    component_properties["finding_count"] = {"type": "integer", "minimum": 0}
    compact_omissions = {"path", "provenance", "packages", "not_responsible_for"}
    component["required"] = [name for name in component_required if name not in compact_omissions]
    view["required"] = [
        name for name in view_required if name not in {"permission_rules", "policy_context"}
    ]

    definitions_envelope = definitions["ArchitectureCommandEnvelope"]
    if not isinstance(definitions_envelope, dict):
        raise TypeError("generated command schema has invalid envelope")
    envelope_properties = definitions_envelope["properties"]
    envelope_required = definitions_envelope["required"]
    if not isinstance(envelope_properties, dict) or not isinstance(envelope_required, list):
        raise TypeError("generated command schema has invalid envelope fields")
    envelope_properties["filtered_violation_count"] = {
        "anyOf": [{"type": "integer", "minimum": 0}, {"type": "null"}]
    }
    envelope_properties["violation_details_included"] = {"type": "boolean"}
    envelope_properties["filtered_violations"] = {
        "anyOf": [
            {
                "type": "array",
                "items": {"$ref": "urn:archkeel:command-result:6.0.0#/$defs/filteredViolation"},
            },
            {"type": "null"},
        ]
    }
    envelope_required[:] = [name for name in envelope_required if name != "filtered_violations"]
    envelope_required.extend(
        name
        for name in ("filtered_violation_count", "violation_details_included")
        if name not in envelope_required
    )
    definitions_envelope["allOf"] = [
        {
            "if": {
                "properties": {
                    "report_filter": {
                        "properties": {"full_architecture": {"const": True}},
                        "required": ["full_architecture"],
                    }
                },
                "required": ["report_filter"],
            },
            "then": {
                "required": ["filtered_violations"],
                "properties": {
                    "architecture_projection": {
                        "required": ["permission_rules", "policy_context"],
                        "properties": {
                            "components": {
                                "items": {
                                    "required": full_component_required,
                                    "properties": {
                                        "permissions": {
                                            "items": {"required": full_permission_required}
                                        }
                                    },
                                    "not": {"required": ["finding_count"]},
                                }
                            }
                        },
                    }
                },
                "allOf": [
                    {
                        "if": {
                            "properties": {"filtered_violations": {"type": "array"}},
                            "required": ["filtered_violations"],
                        },
                        "then": {
                            "properties": {
                                "filtered_violation_count": {"type": "integer"},
                                "violation_details_included": {"const": True},
                            }
                        },
                        "else": {
                            "properties": {
                                "filtered_violation_count": {"type": "null"},
                                "violation_details_included": {"const": False},
                            }
                        },
                    }
                ],
            },
            "else": {
                "not": {"required": ["filtered_violations"]},
                "properties": {"violation_details_included": {"const": False}},
            },
        }
    ]
    return schema


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
    schema["$defs"]["component"]["properties"]["layer"] = {
        "type": "string",
        "pattern": "\\S",
    }
    common = schema["$defs"]["completeRequires"]
    schema["$defs"]["layerOrder"] = {
        "type": "object",
        "additionalProperties": False,
        "required": ["id", "kind", "layers", "rationale", "provenance", "decided_by"],
        "properties": {
            **{
                key: value
                for key, value in common["properties"].items()
                if key != "include_type_checking"
            },
            "kind": {"const": "layer_order"},
            "layers": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": {"type": "string", "pattern": "\\S"},
            },
            "components": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": {"type": "string", "pattern": "\\S"},
            },
        },
    }
    choices = schema["properties"]["rules"]["items"]["oneOf"]
    reference = {"$ref": "#/$defs/layerOrder"}
    if reference not in choices:
        choices.append(reference)
    schema["$defs"]["uml"] = target_schema()
    schema["$defs"]["declarations"]["properties"]["uml"] = {"$ref": "#/$defs/uml"}
    schema["allOf"] = [
        {
            "if": {"properties": {"schema_version": {"const": "2.1.0"}}},
            "then": {"properties": {"declarations": {"not": {"required": ["uml"]}}}},
        }
    ]
    schema["allOf"].append(
        {
            "if": {"properties": {"schema_version": {"enum": ["2.1.0", "2.2.0"]}}},
            "then": {
                "properties": {
                    "components": {"items": {"not": {"required": ["layer"]}}},
                    "rules": {
                        "items": {
                            "not": {
                                "properties": {"kind": {"const": "layer_order"}},
                                "required": ["kind"],
                            }
                        }
                    },
                }
            },
        }
    )
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
    parser.add_argument("--projection", type=Path)
    parser.add_argument("--command", type=Path)
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
    if args.command is not None:
        args.command.write_text(json.dumps(command_schema(), indent=2) + "\n", encoding="utf-8")
    if args.projection is not None:
        args.projection.write_text(
            json.dumps(projection_schema(), indent=2) + "\n", encoding="utf-8"
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

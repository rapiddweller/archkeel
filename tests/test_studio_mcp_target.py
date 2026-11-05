# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-303 models current Workspace intent and the missing component-owner target."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from archkeel.ir.architecture_graph import Entity, EntityKind, PresenceKind, TargetDefinition
from archkeel.ir.target_graph import intent_graph

ROOT = Path(__file__).parents[1]


def test_workspace_session_ports_are_planned_without_claiming_an_mcp_component():
    contract = json.loads((ROOT / "docs/architecture/contracts/studio.json").read_bytes())
    api = next(item for item in contract["components"] if item["id"] == "STUDIO-API")
    workspace = next(item for item in contract["components"] if item["id"] == "STUDIO-WORKSPACE")
    server = next(item for item in contract["components"] if item["id"] == "STUDIO-SERVER")

    assert any("MCP protocol" in item for item in api["forbidden_responsibilities"])
    assert any("MCP" in item for item in server["forbidden_responsibilities"])
    assert workspace["planned"] == [
        "archkeel.studio.workspace:SessionHandle",
        "archkeel.studio.workspace:attach_session",
        "archkeel.studio.workspace:read_snapshot",
        "archkeel.studio.workspace:current_revision",
    ]

    root_contract = json.loads((ROOT / "architecture-contract.json").read_bytes())
    assert all(item["label"] != "mcp" for item in root_contract["components"])


def test_component_owner_without_a_real_package_or_module_is_not_a_valid_target():
    schema = json.loads((ROOT / "schema/architecture-contract.schema.json").read_bytes())
    component_schema = {
        "$schema": schema["$schema"],
        "$defs": schema["$defs"],
        **schema["$defs"]["component"],
    }
    planned_owner = {
        "id": "COMP-MCP",
        "label": "mcp",
        "role": "component",
        "packages": [],
        "exact_modules": [],
        "responsibilities": ["Adapt local MCP requests."],
        "forbidden_responsibilities": [],
        "provenance": [
            "docs/architecture/decisions/ad-303-local-mcp-adapts-shared-read-only-project-operations.md"
        ],
    }

    assert list(Draft202012Validator(component_schema).iter_errors(planned_owner))
    with pytest.raises(ValueError, match="cannot redeclare an existing component owner"):
        intent_graph(
            TargetDefinition(
                entities=(
                    Entity(
                        "MCP-LOCAL-ADAPTER",
                        EntityKind.COMPONENT,
                        "archkeel.mcp",
                        "python",
                        presence=PresenceKind.PLANNED,
                        responsibilities=("Adapt local MCP requests.",),
                    ),
                )
            ),
            owners=(),
        )

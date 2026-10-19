# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Independent UML intent must use the shared types and survive contract round trips."""

import json
from pathlib import Path

from test_architecture_demo import _prepare_repo

from archkeel.check.ports import ScanConfig
from archkeel.ir.architecture_graph import (
    Entity,
    Signature,
    Visibility,
)
from archkeel.ir.codec import (
    contract_bytes,
    parse_contract,
)
from archkeel.ir.graph_codec import graph_bytes, parse_graph
from archkeel.ir.target_graph import declared_graph


def _contract():
    return {
        "schema_version": "2.2.0",
        "components": [
            {
                "id": "core",
                "label": "core",
                "role": "component",
                "packages": ["sample.core"],
                "responsibilities": ["Own the domain."],
                "forbidden_responsibilities": [],
                "provenance": ["docs/target.md"],
                "namespace": "sample.core",
            }
        ],
        "rules": [],
        "declarations": {
            "uml": {
                "schema_version": "1.0.0",
                "entities": [
                    {
                        "id": "service",
                        "kind": "class",
                        "qualified_name": "sample.core.Service",
                        "language": "python",
                        "parent_id": "core",
                        "presence": "planned",
                        "responsibilities": ["Execute a request."],
                        "provenance": ["docs/target.md"],
                    },
                    {
                        "id": "run",
                        "kind": "method",
                        "qualified_name": "sample.core.Service.run",
                        "language": "python",
                        "parent_id": "service",
                        "presence": "planned",
                        "responsibilities": ["Execute one request."],
                        "provenance": ["docs/target.md"],
                        "visibility": {"kind": "public", "basis": "declared"},
                        "signature": {
                            "parameters": [
                                {
                                    "name": "request",
                                    "kind": "positional",
                                    "annotation": "Request",
                                    "default_known": True,
                                }
                            ],
                            "returns": "Result",
                        },
                    },
                    {
                        "id": "interface",
                        "kind": "interface",
                        "qualified_name": "sample.core.Port",
                        "language": "python",
                        "parent_id": "core",
                        "presence": "planned",
                        "responsibilities": ["Define the boundary."],
                        "provenance": ["docs/target.md"],
                    },
                ],
                "relationships": [
                    {
                        "id": "implementation",
                        "kind": "realizes",
                        "source_id": "service",
                        "target_id": "interface",
                        "provenance": ["docs/target.md"],
                    }
                ],
                "scopes": [
                    {
                        "scope_id": "core",
                        "entity_kinds": ["class", "interface", "method"],
                        "mode": "closed",
                        "rationale": "Declare the full boundary.",
                        "provenance": ["docs/target.md"],
                    }
                ],
            }
        },
    }


def test_target_compiles_without_observation_and_uses_shared_entity_types() -> None:
    contract = parse_contract(_contract())
    graph = declared_graph(contract)
    graph.validate()
    assert graph.origin == "declared"
    assert {item.id for item in graph.entities} == {"core", "service", "run", "interface"}
    method = next(item for item in graph.entities if item.id == "run")
    assert type(method) is Entity
    assert isinstance(method.signature, Signature)
    assert method.visibility == Visibility("public", "declared")
    assert method.signature.parameters[0].annotation == "Request"
    assert graph.relationships[0].kind == "realizes"
    assert graph.target_scopes[0].mode == "closed"
    assert parse_graph(json.loads(graph_bytes(graph))) == graph
    assert parse_contract(json.loads(contract_bytes(contract))) == contract


def test_contract_corpus_preserves_version_and_uml_presence() -> None:
    root = Path(__file__).parents[1]
    for path in (root / "tests/contracts/valid").glob("*.json"):
        raw = json.loads(path.read_bytes())
        contract = parse_contract(raw)
        encoded = json.loads(contract_bytes(contract))
        assert encoded["schema_version"] == raw["schema_version"]
        assert parse_contract(encoded) == contract
        assert ("uml" in encoded.get("declarations", {})) == ("uml" in raw.get("declarations", {}))


def _physical_contract():
    raw = _contract()
    raw["declarations"]["modules"] = [
        {"path": "src/sample/core.py", "responsibility": "Own the domain."},
        {"path": "src/sample/future.py", "responsibility": "Hold future intent."},
    ]
    raw["rules"] = [
        {
            "id": "layout",
            "kind": "root_layout",
            "root": "sample",
            "allowed_children": ["sample.core", "sample.future"],
            "rationale": "Keep the immediate package boundary explicit.",
            "provenance": ["docs/target.md"],
            "decided_by": "architect",
        }
    ]
    return raw


def _nested_contracts(root_version="2.2.0"):
    outer = _contract()
    outer["schema_version"] = root_version
    outer.pop("declarations")
    outer["components"][0].update(id="ROOT", inside="inside.json")
    inner = _physical_contract()
    inner["components"][0].update(label="service", inside="leaf.json")
    inner["declarations"]["modules"] = [
        {"path": "sample/core.py", "responsibility": "Own the service."}
    ]
    leaf = _contract()
    leaf["components"][0].update(label="operations", role="foundation")
    leaf["declarations"]["modules"] = []
    return outer, inner, leaf


def _nested_repository(tmp_path, root_version="2.2.0"):
    root, config = _repository(tmp_path)
    outer, inner, leaf = _nested_contracts(root_version)
    for path, raw in ((config.contract, outer), ("inside.json", inner), ("leaf.json", leaf)):
        (root / path).write_text(json.dumps(raw))
    return root, config


def _permission_contract(raw=None):
    raw = _contract() if raw is None else raw
    prefix = raw["components"][0]["namespace"]
    raw["components"][0]["decided_by"] = "architect"
    raw["components"][0]["requires"] = [
        {
            "component": "peer",
            "rationale": "Use the peer boundary.",
            "through": [prefix + ".peer"],
            "decided_by": "agent",
        }
    ]
    raw["components"].append(
        {
            "id": "PEER",
            "label": "peer",
            "role": "interface",
            "packages": [prefix + ".peer"],
            "namespace": prefix + ".peer",
            "responsibilities": ["Own the peer boundary."],
            "forbidden_responsibilities": [],
            "provenance": ["docs/target.md"],
        }
    )
    return raw


def _repository(tmp_path: Path) -> tuple[Path, ScanConfig]:
    root = _prepare_repo(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/core.py": (
                "class Service:\n    def run(self, request):\n        return request\n"
            ),
            "contract.json": json.dumps(_contract()),
            "docs/target.md": "The target is authored independently of source facts.\n",
        },
    )
    return root, ScanConfig(("sample",), "sample", "contract.json", "0" * 64)

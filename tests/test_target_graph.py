# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Independent UML intent must use the shared types and survive contract round trips."""

import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from test_architecture_demo import _prepare_repo

from archkeel.check.ports import ScanConfig
from archkeel.check.uml import assemble_uml
from archkeel.check.validation.references import reference_diagnostics
from archkeel.cli.observe import observe
from archkeel.ir.architecture_graph import (
    ArchitectureGraph,
    ArchitectureReport,
    ComponentIntent,
    ComponentLifecycle,
    ComponentRole,
    Entity,
    EntityKind,
    GraphSchemaVersion,
    OriginKind,
    PresenceKind,
    RelationshipKind,
    ReportSchemaVersion,
    Signature,
    Visibility,
)
from archkeel.ir.codec import (
    contract_bytes,
    load_inside_contract_tree,
    parse_contract,
)
from archkeel.ir.contract_version import ContractVersion
from archkeel.ir.dependency import ModuleSelection
from archkeel.ir.graph_codec import (
    WireComponentSelectorError,
    graph_bytes,
    parse_graph,
    parse_report,
    report_bytes,
)
from archkeel.ir.model import Evidence
from archkeel.ir.target_graph import declared_graph, declared_tree_graph
from archkeel.ir.widening import contract_widenings
from tools.architecture_graph_schema import graph_schema, target_schema


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


@pytest.mark.parametrize(
    "field,value",
    [
        ("component", "core"),
        ("through", ()),
        ("rationale", "Changed intent."),
        ("decided_by", "architect"),
    ],
)
def test_core_authenticates_dependency_permission_contents(tmp_path, field, value):
    root, config = _repository(tmp_path)
    (root / config.contract).write_text(json.dumps(_permission_contract()))
    original = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    owner = next(item for item in original.observation.records("declarations") if item.id == "core")
    permissions = owner.data.get("requires")
    changed = replace(
        permissions[0], entries=tuple({**dict(permissions[0].entries), field: value}.items())
    )
    forged = replace(
        owner,
        data=replace(
            owner.data, entries=tuple({**dict(owner.data.entries), "requires": (changed,)}.items())
        ),
    )
    sections = tuple(
        replace(
            section,
            records=tuple(forged if item.id == owner.id else item for item in section.records),
        )
        for section in original.observation.sections
    )
    result = assemble_uml(
        replace(original, observation=replace(original.observation, sections=sections)),
        root,
        config.contract,
    )
    assert result.diagnostics


def test_uml_cannot_redeclare_component_permissions():
    raw = _permission_contract()
    raw["declarations"]["uml"]["relationships"].append(
        {
            "id": "permission",
            "kind": "requires",
            "source_id": "core",
            "target_id": "PEER",
            "provenance": ["docs/target.md"],
        }
    )
    with pytest.raises(ValueError, match="component requires"):
        parse_contract(raw)


def test_planned_component_fixture_is_target_intent_only() -> None:
    fixture = Path(__file__).parents[1] / "fixtures" / "planned-component"
    raw = json.loads((fixture / "architecture-contract.json").read_text())
    contract = parse_contract(raw)

    graph = declared_graph(
        contract, contract_path="fixtures/planned-component/architecture-contract.json"
    )

    owner = next(item for item in graph.entities if item.id == "mcp")
    assert owner.kind == EntityKind.COMPONENT
    assert owner.presence == PresenceKind.PLANNED
    assert graph.origin == OriginKind.DECLARED
    assert any(item.id == "server" and item.parent_id == owner.id for item in graph.entities)
    assert any(item.kind == RelationshipKind.REALIZES for item in graph.relationships)


def test_planned_component_presence_and_owner_identity_are_validated() -> None:
    fixture = Path(__file__).parents[1] / "fixtures" / "planned-component"
    raw = json.loads((fixture / "architecture-contract.json").read_text())
    target_owner = raw["declarations"]["uml"]["entities"][0]
    for presence in ("referenced", "defined"):
        target_owner["presence"] = presence
        with pytest.raises(ValueError, match="UML component owners need planned intent"):
            parse_contract(raw)

    raw["components"] = [
        {
            "id": "mcp",
            "label": "mcp",
            "role": "component",
            "packages": ["archkeel.mcp"],
            "namespace": "archkeel.mcp",
            "responsibilities": ["Expose ArchKeel target intent to local MCP clients."],
            "forbidden_responsibilities": [],
            "planned": ["archkeel.mcp.server.McpServer"],
            "requires": [{"component": "core", "rationale": "Reuse the existing core."}],
            "provenance": ["README.md"],
        },
        {
            "id": "core",
            "label": "core",
            "role": "component",
            "packages": ["archkeel.core"],
            "responsibilities": ["Own shared analysis operations."],
            "forbidden_responsibilities": [],
            "provenance": ["README.md"],
        },
    ]

    with pytest.raises(ValueError, match="duplicate contract ID"):
        parse_contract(raw)


def test_planned_component_policy_and_promotion_share_one_owner() -> None:
    fixture = Path(__file__).parents[1] / "fixtures" / "planned-component-policy"
    raw = json.loads((fixture / "architecture-contract.json").read_text())
    planned = declared_graph(parse_contract(raw))
    planned_mcp = next(item for item in planned.component_intents if item.component_id == "mcp")
    assert planned_mcp.planned == (
        "archkeel.mcp.server:McpServer",
        "archkeel.mcp.server:Transport",
    )
    assert any(
        item.kind == RelationshipKind.REQUIRES
        and item.source_id == "mcp"
        and item.target_id == "core"
        for item in planned.relationships
    )
    assert planned.schema_version == GraphSchemaVersion.V1_3_0
    assert planned_mcp.lifecycle is ComponentLifecycle.PLANNED
    assert planned_mcp.layer == "adapter"
    assert any(item.id == "server" and item.parent_id == "mcp" for item in planned.entities)

    promoted_raw = json.loads(json.dumps(raw))
    for owner in promoted_raw["components"]:
        if owner.get("lifecycle") == "planned":
            owner.pop("lifecycle")
            owner["packages"] = [f"archkeel.{owner['id']}"]
    promoted = declared_graph(parse_contract(promoted_raw))
    promoted_mcp = next(item for item in promoted.component_intents if item.component_id == "mcp")
    assert promoted_mcp.component_id == planned_mcp.component_id
    assert promoted_mcp.planned == planned_mcp.planned
    assert {
        (item.source_id, item.target_id, item.through)
        for item in promoted.relationships
        if item.kind == RelationshipKind.REQUIRES
    } == {
        (item.source_id, item.target_id, item.through)
        for item in planned.relationships
        if item.kind == RelationshipKind.REQUIRES
    }


@pytest.mark.parametrize(
    ("scope_case", "encodable"),
    [
        ("ancestor", True),
        ("unrelated", True),
        ("sibling-package", False),
        ("sibling-exact", False),
        ("mixed", False),
        ("explicit-ancestor-selector", False),
    ],
)
def test_authenticated_nested_planned_selector_encoders_respect_component_scope(
    tmp_path: Path, scope_case: str, encodable: bool
) -> None:
    root, config = _nested_repository(tmp_path, root_version="2.4.0")
    root_raw, inside_raw, _ = _nested_contracts("2.4.0")
    root_raw["components"][0].update(id="ROOT", inside="inside.json")
    root_raw["components"][0]["packages"] = ["sample"]
    root_raw["components"][0]["namespace"] = "sample"
    inside_raw["components"][0].update(label="service", inside="leaf.json")
    inside_raw["schema_version"] = "2.4.0"
    inside_raw["components"].append(
        {
            "id": "future",
            "label": "future",
            "role": "component",
            "lifecycle": "planned",
            "packages": [],
            "planned": ["sample.future:run"],
            "responsibilities": [],
            "forbidden_responsibilities": [],
            "provenance": ["docs/target.md"],
        }
    )
    if scope_case == "explicit-ancestor-selector":
        root_raw["components"][0]["public"] = ["sample.future:run"]
    if scope_case in {"sibling-package", "mixed"}:
        inside_raw["components"].append(
            {
                "id": "sibling",
                "label": "sibling",
                "role": "component",
                "packages": ["sample.future"],
                "responsibilities": ["Own the sibling package."],
                "forbidden_responsibilities": [],
                "provenance": ["docs/target.md"],
            }
        )
    elif scope_case == "sibling-exact":
        inside_raw["components"].append(
            {
                "id": "sibling",
                "label": "sibling",
                "role": "component",
                "packages": [],
                "exact_modules": ["sample.future"],
                "responsibilities": ["Own the exact sibling module."],
                "forbidden_responsibilities": [],
                "provenance": ["docs/target.md"],
            }
        )
    elif scope_case == "unrelated":
        inside_raw["components"].append(
            {
                "id": "unrelated",
                "label": "unrelated",
                "role": "component",
                "packages": ["other.package"],
                "responsibilities": ["Own an unrelated package."],
                "forbidden_responsibilities": [],
                "provenance": ["docs/target.md"],
            }
        )
    if scope_case == "mixed":
        inside_raw["components"].append(
            {
                "id": "unrelated",
                "label": "unrelated",
                "role": "component",
                "packages": ["other.package"],
                "responsibilities": ["Own an unrelated package."],
                "forbidden_responsibilities": [],
                "provenance": ["docs/target.md"],
            }
        )
    (root / config.contract).write_text(json.dumps(root_raw))
    (root / "inside.json").write_text(json.dumps(inside_raw))

    root_bytes = (root / config.contract).read_bytes()
    tree = load_inside_contract_tree(
        config.contract,
        parse_contract(json.loads(root_bytes)),
        hashlib.sha256(root_bytes).hexdigest(),
        config.contract,
        lambda path: ((root / path).read_bytes(), path),
    )
    assert not tree.issues
    graph = declared_tree_graph(tree, root_path=config.contract)

    if not encodable:
        with pytest.raises(WireComponentSelectorError, match="planned API selector"):
            graph_bytes(graph)
        report = ArchitectureReport(
            None,
            graph,
            unavailable="Source graph was omitted for this nested target probe.",
            schema_version=ReportSchemaVersion.V1_3_0,
        )
        with pytest.raises(WireComponentSelectorError, match="planned API selector"):
            report_bytes(report)
        return

    assert parse_graph(json.loads(graph_bytes(graph))) == graph
    report = ArchitectureReport(
        None,
        graph,
        unavailable="Source graph was omitted for this nested target probe.",
        schema_version=ReportSchemaVersion.V1_3_0,
    )
    assert parse_report(json.loads(report_bytes(report))) == report


def test_planned_component_policy_rejects_duplicate_selector_and_duplicate_uml_owner() -> None:
    fixture = Path(__file__).parents[1] / "fixtures" / "planned-component-policy"
    raw = json.loads((fixture / "architecture-contract.json").read_text())
    mcp_index = next(index for index, owner in enumerate(raw["components"]) if owner["id"] == "mcp")
    core_index = next(
        index for index, owner in enumerate(raw["components"]) if owner["id"] == "core"
    )
    raw["components"][core_index]["planned"] = raw["components"][mcp_index]["planned"]
    contract = parse_contract(raw)
    diagnostics = reference_diagnostics(
        fixture,
        ScanConfig(("src/archkeel",), "archkeel", "architecture-contract.json", "0" * 64),
        contract,
    )
    assert any(
        item.pointer == f"/components/{mcp_index}/planned/0"
        and "claimed by multiple components" in item.unknown_claim
        for item in diagnostics
    )

    raw = json.loads((fixture / "architecture-contract.json").read_text())
    raw["declarations"]["uml"]["entities"].append(
        {
            "id": "mcp",
            "kind": "component",
            "qualified_name": "archkeel.mcp",
            "language": "architecture",
            "presence": "planned",
            "provenance": ["README.md"],
            "responsibilities": ["Duplicate owner."],
        }
    )
    with pytest.raises(ValueError, match="duplicate contract ID"):
        parse_contract(raw)

    raw = json.loads((fixture / "architecture-contract.json").read_text())
    raw["components"][0]["lifecycle"] = None
    with pytest.raises(ValueError, match="lifecycle"):
        parse_contract(raw)

    raw = json.loads((fixture / "architecture-contract.json").read_text())
    raw["schema_version"] = "2.3.0"
    with pytest.raises(ValueError, match="2.4.0"):
        parse_contract(raw)


def test_contract_uml_selector_conflict_remains_a_reference_diagnostic() -> None:
    fixture = Path(__file__).parents[1] / "fixtures" / "planned-component-policy"
    raw = json.loads((fixture / "architecture-contract.json").read_text())
    active = next(owner for owner in raw["components"] if owner["id"] == "fixture-source")
    active["packages"] = ["archkeel"]
    active["exact_modules"] = []
    contract = parse_contract(raw)

    diagnostics = reference_diagnostics(
        fixture,
        ScanConfig(("src/archkeel",), "archkeel", "architecture-contract.json", "0" * 64),
        contract,
    )

    assert any(
        item.pointer == "/components/1/planned/0"
        and "package-backed component" in item.unknown_claim
        for item in diagnostics
    )


def test_package_less_graph_intent_requires_explicit_planned_lifecycle() -> None:
    owner = Entity(
        "owner",
        EntityKind.COMPONENT,
        "owner",
        "architecture",
        presence=PresenceKind.PLANNED,
        provenance=("docs/target.md",),
    )
    graph = ArchitectureGraph(
        OriginKind.DECLARED,
        (owner,),
        schema_version=GraphSchemaVersion.V1_3_0,
        component_intents=(ComponentIntent("owner", ComponentRole.COMPONENT),),
    )
    with pytest.raises(ValueError, match="package-less component intent needs planned lifecycle"):
        graph.validate()
    legacy = replace(graph, schema_version=GraphSchemaVersion.V1_2_0)
    legacy.validate()
    assert legacy.component_intents[0].lifecycle is None


@pytest.mark.parametrize("wire", ["graph", "report"])
@pytest.mark.parametrize("conflict", ["active-package", "planned-owner"])
def test_graph_wire_rejects_ambiguous_planned_api_selector(wire: str, conflict: str) -> None:
    graph = _ambiguous_selector_graph(conflict)
    graph_payload = asdict(graph)
    for intent in graph_payload["component_intents"]:
        if intent["layer"] is None:
            del intent["layer"]
        if intent["lifecycle"] is None:
            del intent["lifecycle"]
    if wire == "report":
        payload = {
            "observed": None,
            "target": graph_payload,
            "unavailable": "Source graph was omitted for this decoder probe.",
            "schema_version": ReportSchemaVersion.V1_3_0.value,
        }
    else:
        payload = graph_payload

    with pytest.raises(WireComponentSelectorError) as error:
        if wire == "graph":
            parse_graph(json.loads(json.dumps(payload)))
        else:
            parse_report(json.loads(json.dumps(payload)))
    expected_reason = (
        "is owned by active package component"
        if conflict == "active-package"
        else "is claimed by multiple components"
    )
    assert f"planned API selector 'pkg:Foo' {expected_reason}" in str(error.value)


@pytest.mark.parametrize("lifecycle", [None, 1, "future"])
def test_graph_wire_rejects_invalid_component_lifecycle(lifecycle: object) -> None:
    payload = asdict(_ambiguous_selector_graph("planned-owner"))
    for intent in payload["component_intents"]:
        if intent["layer"] is None:
            del intent["layer"]
    payload["component_intents"][0]["lifecycle"] = lifecycle

    with pytest.raises(ValueError):
        parse_graph(payload)


def _ambiguous_selector_graph(conflict: str) -> ArchitectureGraph:
    first_intent = (
        ComponentIntent(
            "active",
            ComponentRole.COMPONENT,
            planned=("pkg:Foo",),
            lifecycle=ComponentLifecycle.PLANNED,
        )
        if conflict == "planned-owner"
        else ComponentIntent("active", ComponentRole.COMPONENT, packages=("other",))
    )
    if conflict == "active-package":
        first_intent = ComponentIntent("active", ComponentRole.COMPONENT, packages=("pkg",))
    return ArchitectureGraph(
        OriginKind.DECLARED,
        (
            Entity(
                "active",
                EntityKind.COMPONENT,
                "active",
                "architecture",
                presence=PresenceKind.PLANNED,
                provenance=("docs/target.md",),
            ),
            Entity(
                "future",
                EntityKind.COMPONENT,
                "future",
                "architecture",
                presence=PresenceKind.PLANNED,
                provenance=("docs/target.md",),
            ),
        ),
        schema_version=GraphSchemaVersion.V1_3_0,
        component_intents=(
            first_intent,
            ComponentIntent(
                "future",
                ComponentRole.COMPONENT,
                planned=("pkg:Foo",),
                lifecycle=ComponentLifecycle.PLANNED,
            ),
        ),
    )


@pytest.mark.parametrize("encoder", ["graph", "report"])
@pytest.mark.parametrize("conflict", ["active-package", "planned-owner"])
def test_graph_and_report_encoders_reject_ambiguous_planned_api_selector(
    encoder: str, conflict: str
) -> None:
    graph = _ambiguous_selector_graph(conflict)

    with pytest.raises(ValueError, match="planned API selector"):
        if encoder == "graph":
            graph_bytes(graph)
        else:
            report_bytes(
                ArchitectureReport(
                    None,
                    graph,
                    unavailable="Source graph was omitted for this encoder probe.",
                    schema_version=ReportSchemaVersion.V1_3_0,
                )
            )


@pytest.mark.parametrize("encoder", ["graph", "report"])
def test_graph_and_report_encoders_roundtrip_unambiguous_planned_selector(encoder: str) -> None:
    graph = _ambiguous_selector_graph("none")

    if encoder == "graph":
        payload = json.loads(graph_bytes(graph))
        assert parse_graph(payload) == graph
    else:
        report = ArchitectureReport(
            None,
            graph,
            unavailable="Source graph was omitted for this roundtrip probe.",
            schema_version=ReportSchemaVersion.V1_3_0,
        )
        payload = json.loads(report_bytes(report))
        assert parse_report(payload) == report


@pytest.mark.parametrize("containment", ["missing", "cycle"])
def test_planned_selector_validation_rejects_invalid_component_ancestry(containment: str) -> None:
    graph = _ambiguous_selector_graph("none")
    active, planned = graph.component_intents
    broken = (
        (active, replace(planned, parent_id="missing"))
        if containment == "missing"
        else (
            replace(active, parent_id=planned.component_id),
            replace(planned, parent_id=active.component_id),
        )
    )
    invalid_graph = replace(graph, component_intents=broken)

    with pytest.raises(ValueError, match="invalid component containment"):
        graph_bytes(invalid_graph)
    wire = json.loads(graph_bytes(graph))
    wire["component_intents"][1]["parent_id"] = "missing" if containment == "missing" else "active"
    if containment == "cycle":
        wire["component_intents"][0]["parent_id"] = "future"
    with pytest.raises(ValueError, match="invalid component containment"):
        parse_graph(wire)


@pytest.mark.parametrize(
    ("selector", "packages", "exact_modules", "owned"),
    [
        ("pkg:Foo", ("pkg",), (), True),
        ("pkg.child:Foo", ("pkg",), (), True),
        ("pkg2:Foo", ("pkg",), (), False),
        ("pkg:Foo", (), ("pkg",), True),
        ("pkg.child:Foo", (), ("pkg",), False),
    ],
)
def test_api_selector_ownership_uses_module_package_and_exact_boundaries(
    selector: str,
    packages: tuple[str, ...],
    exact_modules: tuple[str, ...],
    owned: bool,
) -> None:
    assert ModuleSelection(packages, exact_modules).matches_api_selector(selector) is owned


def test_legacy_component_wire_omits_absent_lifecycle() -> None:
    raw = _contract()
    contract = parse_contract(raw)
    graph = declared_graph(contract)

    encoded_contract = json.loads(contract_bytes(contract))
    assert parse_contract(encoded_contract) == contract
    assert all("lifecycle" not in item for item in encoded_contract["components"])
    wire = json.loads(graph_bytes(graph))
    assert wire["schema_version"] == "1.0.0"
    assert all("lifecycle" not in item for item in wire["component_intents"])
    assert parse_graph(wire) == graph


def test_active_component_contract_and_target_payload_match_origin_main_bytes() -> None:
    fixture = Path(__file__).parents[1] / "fixtures" / "H-uml"
    contract_path = "fixtures/H-uml/architecture-contract.json"
    contract = parse_contract(json.loads((fixture / "architecture-contract.json").read_bytes()))
    graph = declared_graph(contract, contract_path=contract_path)
    report = ArchitectureReport(None, graph, unavailable="compatibility probe")
    payloads = (
        contract_bytes(contract),
        graph_bytes(graph),
        report_bytes(report),
    )

    # Baseline hashes were measured on origin/main 49c5640 using this same fixture.
    assert tuple(hashlib.sha256(payload).hexdigest() for payload in payloads) == (
        "e9bdc9337a7dca5a3626ffcb8895d32da951338404632cf5641eeb8d769bcbe1",
        "dbe1f88ad55e12786227012e9486d3aed261a3ee85a2953d2a7b0d4bc061103c",
        "a5372bbc16d1af7cb61f2be0fb901b480efc18b1550c001234021732e18bc632",
    )


@pytest.mark.parametrize(
    "modules", [None, [], [{"path": "src/sample/core.py", "responsibility": "Own the domain."}]]
)
def test_standard_graph_retains_absent_empty_and_populated_module_inventories(modules) -> None:
    raw = _contract()
    if modules is not None:
        raw["declarations"]["modules"] = modules
    graph = declared_graph(parse_contract(raw), contract_path="contract.json")
    if modules is None:
        assert graph.module_inventories == ()
    else:
        assert len(graph.module_inventories) == 1
        inventory = graph.module_inventories[0]
        assert inventory.component_id is None
        assert inventory.provenance == ("contract.json",)
        assert [asdict(item) for item in inventory.modules] == modules
    assert parse_graph(json.loads(graph_bytes(graph))) == graph
    Draft202012Validator(graph_schema()).validate(json.loads(graph_bytes(graph)))


def test_physical_intent_reuses_contract_types_without_inventing_uml() -> None:
    raw = _physical_contract()
    contract = parse_contract(raw)
    graph = declared_graph(contract, contract_path="contract.json")
    assert graph.module_inventories[0].modules == contract.declarations.modules
    assert graph.layout_rules == contract.rules
    assert graph.layout_rules[0].allowed_children == ("sample.core", "sample.future")
    assert {item.id for item in graph.entities} == {"core", "service", "run", "interface"}
    assert {item.kind for item in graph.relationships} == {"realizes"}
    assert graph.target_scopes == declared_graph(parse_contract(_contract())).target_scopes
    assert parse_graph(json.loads(graph_bytes(graph))) == graph


@pytest.mark.parametrize(
    "path", ["../future.py", "/future.py", "C:/future.py", "src//future.py", "src/future.txt"]
)
def test_standard_graph_rejects_unsafe_or_malformed_module_intent(path) -> None:
    wire = json.loads(
        graph_bytes(
            declared_graph(parse_contract(_physical_contract()), contract_path="contract.json")
        )
    )
    wire["module_inventories"][0]["modules"][0]["path"] = path
    with pytest.raises(ValueError, match="repository-relative source path"):
        parse_graph(wire)


@pytest.mark.parametrize(
    "change",
    [
        "duplicate",
        "missing owner",
        "classifier owner",
        "observed",
        "missing provenance",
        "layout child",
        "duplicate layout",
    ],
)
def test_physical_intent_rejects_invalid_scope_and_permission(change) -> None:
    wire = json.loads(
        graph_bytes(
            declared_graph(parse_contract(_physical_contract()), contract_path="contract.json")
        )
    )
    if change == "duplicate":
        wire["module_inventories"].append(wire["module_inventories"][0])
    elif change in {"missing owner", "classifier owner"}:
        wire["module_inventories"][0]["component_id"] = (
            "missing" if change == "missing owner" else "service"
        )
    elif change == "observed":
        wire["entities"] = []
        wire["relationships"] = []
        wire["component_intents"] = []
        wire["target_scopes"] = []
        wire["origin"] = "observed"
    elif change == "missing provenance":
        wire["module_inventories"][0]["provenance"] = []
    elif change == "layout child":
        wire["layout_rules"][0]["allowed_children"] = ["sample.core.nested"]
    else:
        wire["layout_rules"].append(wire["layout_rules"][0])
    with pytest.raises(ValueError):
        parse_graph(wire)


def test_component_intent_retains_role_api_and_ownership_without_inventing_facts() -> None:
    raw = _contract()
    raw["components"][0].update(
        role="foundation",
        public=["sample.core:Service"],
        planned=["sample.core:Future"],
        exact_modules=["sample.types"],
        forbidden_responsibilities=["Read files."],
        decided_by="architect",
    )
    graph = declared_graph(parse_contract(raw))
    owner = next(item for item in graph.entities if item.id == "core")
    boundary = next(item for item in graph.component_intents if item.component_id == owner.id)
    assert boundary.role.value == "foundation"
    assert boundary.packages == ("sample.core",)
    assert boundary.exact_modules == ("sample.types",)
    assert boundary.namespace == "sample.core"
    assert boundary.public == ("sample.core:Service",)
    assert boundary.planned == ("sample.core:Future",)
    assert boundary.forbidden_responsibilities == ("Read files.",)
    assert boundary.decided_by == "architect"
    assert owner.visibility.kind == "unknown"
    assert not any(item.qualified_name.endswith("Future") for item in graph.entities)
    assert not any(item.kind in {"calls", "imports", "publishes"} for item in graph.relationships)
    assert parse_graph(json.loads(graph_bytes(graph))) == graph
    Draft202012Validator(graph_schema()).validate(json.loads(graph_bytes(graph)))


@pytest.mark.parametrize("public", [None, []])
def test_component_intent_preserves_undeclared_and_explicitly_empty_api(public) -> None:
    raw = _contract()
    if public is not None:
        raw["components"][0]["public"] = public
    boundary = declared_graph(parse_contract(raw)).component_intents[0]
    assert boundary.public == (None if public is None else ())


@pytest.mark.parametrize(
    "changes",
    [
        {"role": "invented"},
        {"public": "sample.core"},
        {"planned": True},
        {"public": ["sample.core", "sample.core"]},
        {"namespace": 3},
        {"decided_by": "nobody"},
        {"observed": True},
        {"public": ["sample.core:Service"], "planned": ["sample.core:Service"]},
        {"parent_id": "missing"},
        {"parent_id": "core"},
        {"label": True},
        {"layout_rule_ids": ["missing"]},
    ],
)
def test_component_intent_rejects_malformed_or_conflicting_values(changes) -> None:
    graph = declared_graph(parse_contract(_contract()))
    wire = json.loads(graph_bytes(graph))
    wire["component_intents"][0].update(changes)
    with pytest.raises(ValueError):
        parse_graph(wire)


@pytest.mark.parametrize("origin,kind", [("observed", "component"), ("declared", "class")])
def test_component_intent_cannot_be_a_source_fact_or_classifier_trait(origin, kind) -> None:
    owner = Entity(
        "owner",
        kind,
        "sample.core",
        "architecture",
        provenance=("docs/target.md",),
        evidence_ids=("source",) if origin == "observed" else (),
    )
    with pytest.raises(ValueError, match="component intent needs a declared component"):
        ArchitectureGraph(
            origin,
            (owner,),
            component_intents=(ComponentIntent("owner", ComponentRole.FOUNDATION),),
            evidence=(Evidence("source", "sample/core.py", 1, 1, 0, "component"),)
            if origin == "observed"
            else (),
        ).validate()


def test_component_intent_needs_one_existing_component_identity() -> None:
    graph = declared_graph(parse_contract(_contract()))
    intent = graph.component_intents[0]
    with pytest.raises(ValueError, match="duplicate component intent"):
        replace(graph, component_intents=(intent, intent)).validate()
    with pytest.raises(ValueError, match="component intent needs a declared component"):
        replace(graph, component_intents=(replace(intent, component_id="missing"),)).validate()


def test_component_containment_cannot_be_duplicated_as_lexical_containment() -> None:
    graph = declared_graph(parse_contract(_contract()))
    owner, *inner = graph.entities
    with pytest.raises(ValueError, match="component containment belongs in component intent"):
        replace(graph, entities=(replace(owner, parent_id="service"), *inner)).validate()


def test_component_layout_rules_have_one_owner() -> None:
    raw = _physical_contract()
    raw["components"].append(
        {
            **raw["components"][0],
            "id": "other",
            "label": "other",
            "namespace": "sample.other",
            "packages": ["sample.other"],
        }
    )
    graph = declared_graph(parse_contract(raw))
    intents = tuple(replace(item, layout_rule_ids=("layout",)) for item in graph.component_intents)
    with pytest.raises(ValueError, match="layout reference"):
        replace(graph, component_intents=intents).validate()


@pytest.mark.parametrize(
    "changes",
    [
        {"evidence_ids": ["source"]},
        {"provenance": []},
        {"responsibilities": []},
        {"parent_id": "missing"},
        {"presence": "defined"},
        {"kind": "component"},
        {"record_ids": ["source-record"]},
        {"unexpected": True},
        {"signature": {"parameters": [], "returns": None}},
    ],
)
def test_invalid_or_source_derived_target_entities_are_rejected(changes) -> None:
    raw = _contract()
    raw["declarations"]["uml"]["entities"][0].update(changes)
    with pytest.raises(ValueError):
        parse_contract(raw)


@pytest.mark.parametrize(
    "changes",
    [
        {"resolution": "resolved"},
        {"candidate_ids": ["interface"]},
        {"evidence_ids": ["source"]},
        {"record_ids": ["source-record"]},
        {"candidate_count": True},
        {"target_id": "missing"},
        {"target_id": None},
        {"id": "service"},
    ],
)
def test_target_relationships_do_not_claim_source_resolution(changes) -> None:
    raw = _contract()
    raw["declarations"]["uml"]["relationships"][0].update(changes)
    with pytest.raises(ValueError):
        parse_contract(raw)


@pytest.mark.parametrize("parent", [None, "core", "run"])
def test_planned_attribute_requires_a_lexical_classifier(parent) -> None:
    raw = _contract()
    field = dict(raw["declarations"]["uml"]["entities"][1])
    field.update(id="field", kind="attribute", qualified_name="sample.core.Service.value")
    field.pop("signature")
    field["parent_id"] = parent
    raw["declarations"]["uml"]["entities"].append(field)
    with pytest.raises(ValueError, match="planned attribute without a classifier"):
        parse_contract(raw)


@pytest.mark.parametrize("kind", ["inherits", "realizes"])
@pytest.mark.parametrize(
    "endpoints", [("module", "attribute"), ("module", "class"), ("class", "attribute")]
)
def test_classifier_relations_reject_known_nonclassifier_endpoints(kind, endpoints) -> None:
    raw = _contract()
    target = raw["declarations"]["uml"]
    target.pop("scopes")
    target["entities"] = [
        dict(target["entities"][0], id="source", kind=endpoints[0]),
        dict(
            target["entities"][2],
            id="target",
            kind=endpoints[1],
            parent_id="source",
            presence="referenced",
        ),
    ]
    target["relationships"] = [
        {
            "id": "relation",
            "kind": kind,
            "source_id": "source",
            "target_id": "target",
            "provenance": ["docs/target.md"],
        }
    ]
    with pytest.raises(ValueError, match="classifier relationship needs classifier endpoints"):
        parse_contract(raw)


@pytest.mark.parametrize("different_prose", [False, True])
def test_identical_planned_operation_cannot_borrow_another_identity(different_prose) -> None:
    raw = _contract()
    operation = dict(raw["declarations"]["uml"]["entities"][1])
    operation["id"] = "duplicate-run"
    if different_prose:
        operation.update(responsibilities=["A different reason."], provenance=["docs/other.md"])
    raw["declarations"]["uml"]["entities"].append(operation)
    with pytest.raises(ValueError, match="duplicate planned entity"):
        parse_contract(raw)


@pytest.mark.parametrize("kind", ["positional", "keyword_only", "varargs", "kwargs"])
def test_python_target_signature_rejects_repeated_parameter_names(kind) -> None:
    raw = _contract()
    parameters = raw["declarations"]["uml"]["entities"][1]["signature"]["parameters"]
    parameters.append({"name": "request", "kind": kind})
    with pytest.raises(ValueError, match="duplicate Python parameter name"):
        parse_contract(raw)


def test_distinct_planned_overloads_and_referenced_symbols_keep_their_identities() -> None:
    raw = _contract()
    operation = dict(raw["declarations"]["uml"]["entities"][1])
    operation.update(
        id="run-str",
        signature={
            "parameters": [{"name": "request", "kind": "positional", "annotation": "str"}],
            "returns": "str",
        },
    )
    external = {
        "id": "external",
        "kind": "symbol",
        "qualified_name": "external.Base",
        "language": "python",
        "presence": "referenced",
        "provenance": ["docs/target.md"],
    }
    raw["declarations"]["uml"]["entities"].extend([operation, external])
    graph = declared_graph(parse_contract(raw))
    assert {item.id for item in graph.entities if item.kind == "method"} == {"run", "run-str"}
    assert next(item for item in graph.entities if item.id == "external").parent_id is None


@pytest.mark.parametrize("kind", ["inherits", "realizes"])
def test_classifier_relations_allow_referenced_external_symbols(kind) -> None:
    raw = _contract()
    target = raw["declarations"]["uml"]
    target["entities"].append(
        {
            "id": "external",
            "kind": "symbol",
            "qualified_name": "external.Base",
            "language": "python",
            "presence": "referenced",
            "provenance": ["docs/target.md"],
        }
    )
    target["relationships"].append(
        {
            "id": "external-base",
            "kind": kind,
            "source_id": "service",
            "target_id": "external",
            "provenance": ["docs/target.md"],
        }
    )
    graph = declared_graph(parse_contract(raw))
    assert (
        next(item for item in graph.relationships if item.id == "external-base").target_id
        == "external"
    )


@pytest.mark.parametrize("classifier", ["class", "interface", "enum", "mixin"])
def test_planned_classifier_fields_and_nested_definitions_remain_valid(classifier) -> None:
    raw = _contract()
    target = raw["declarations"]["uml"]
    target["entities"][0]["kind"] = classifier
    field = dict(target["entities"][1])
    field.update(id="field", kind="attribute", qualified_name="sample.core.Service.callback")
    field.pop("signature")
    helper = dict(target["entities"][1])
    helper.update(
        id="helper",
        kind="function",
        qualified_name="sample.core.Service.run.helper",
        parent_id="run",
    )
    local_class = dict(target["entities"][0])
    local_class.update(
        id="local-class",
        kind="class",
        qualified_name="sample.core.Service.run.helper.Local",
        parent_id="helper",
    )
    target["entities"].extend([field, helper, local_class])
    target["relationships"].extend(
        [
            {
                "id": "initialize-callback",
                "kind": "calls",
                "source_id": "service",
                "target_id": "field",
                "provenance": ["docs/target.md"],
            },
            {
                "id": "construct-service",
                "kind": "creates",
                "source_id": "run",
                "target_id": "service",
                "provenance": ["docs/target.md"],
            },
        ]
    )
    graph = declared_graph(parse_contract(raw))
    parents = {item.id: item.parent_id for item in graph.entities}
    assert parents["field"] == "service"
    assert parents["helper"] == "run"
    assert parents["local-class"] == "helper"
    assert {edge.kind for edge in graph.relationships} == {"realizes", "calls", "creates"}


def test_python_target_signature_retains_distinct_variadic_and_keyword_only_parameters() -> None:
    raw = _contract()
    parameters = [
        {"name": "self", "kind": "positional_only"},
        {"name": "request", "kind": "positional"},
        {"name": "args", "kind": "varargs"},
        {"name": "limit", "kind": "keyword_only", "default": "10", "default_known": True},
        {"name": "kwargs", "kind": "kwargs"},
    ]
    raw["declarations"]["uml"]["entities"][1]["signature"]["parameters"] = parameters
    graph = declared_graph(parse_contract(raw))
    operation = next(item for item in graph.entities if item.id == "run")
    assert operation.signature is not None
    assert [parameter.name for parameter in operation.signature.parameters] == [
        "self",
        "request",
        "args",
        "limit",
        "kwargs",
    ]
    assert operation.signature.parameters[3].default == "10"


def test_planned_package_and_initializer_share_a_name_without_sharing_identity() -> None:
    raw = _contract()
    target = raw["declarations"]["uml"]
    package = dict(target["entities"][0])
    package.update(id="package", kind="package", qualified_name="sample.core")
    module = dict(package, id="initializer", kind="module")
    target["entities"].extend([package, module])
    graph = declared_graph(parse_contract(raw))
    assert {
        (item.id, item.kind) for item in graph.entities if item.qualified_name == "sample.core"
    } == {("core", "component"), ("package", "package"), ("initializer", "module")}


def test_old_contract_version_cannot_silently_add_new_uml_semantics() -> None:
    raw = _contract()
    raw["schema_version"] = "2.1.0"
    with pytest.raises(ValueError, match="2.2.0"):
        parse_contract(raw)


@pytest.mark.parametrize(
    "changes",
    [
        {"scope_id": "missing"},
        {"mode": "invented"},
        {"rationale": " "},
        {"provenance": []},
        {"entity_kinds": []},
        {"entity_kinds": ["class", "class"]},
        {"relationship_kinds": ["invented"]},
    ],
)
def test_target_completeness_cannot_be_empty_or_ambiguous(changes) -> None:
    raw = _contract()
    raw["declarations"]["uml"]["scopes"][0].update(changes)
    with pytest.raises(ValueError):
        parse_contract(raw)


def test_target_completeness_kind_cannot_have_two_modes_in_one_scope() -> None:
    raw = _contract()
    scope = raw["declarations"]["uml"]["scopes"][0]
    raw["declarations"]["uml"]["scopes"].append({**scope, "mode": "open"})
    with pytest.raises(ValueError, match="duplicate Target completeness"):
        parse_contract(raw)


@pytest.mark.parametrize("change", ["remove", "open_scope", "signature"])
def test_target_changes_cannot_silently_weaken_an_accepted_contract(change: str) -> None:
    before = parse_contract(_contract())
    raw = _contract()
    if change == "remove":
        del raw["declarations"]["uml"]
    elif change == "open_scope":
        raw["declarations"]["uml"]["scopes"][0]["mode"] = "open"
    else:
        raw["declarations"]["uml"]["entities"][1]["signature"]["returns"] = "object"
    assert contract_widenings(before, parse_contract(raw))


def test_graph_wire_decoder_rejects_unknown_fields_versions_and_wrong_types() -> None:
    payload = asdict(ArchitectureGraph("declared"))
    for invalid in (
        {**payload, "schema_version": "99.0.0"},
        {**payload, "entities": {}},
        {**payload, "invented": True},
        {**payload, "coverage": True},
    ):
        with pytest.raises(ValueError):
            parse_graph(invalid)


def test_uml_contract_schema_is_generated_from_the_shared_dataclasses() -> None:
    schema = json.loads(
        (Path(__file__).parents[1] / "schema/architecture-contract.schema.json").read_bytes()
    )
    assert schema["$defs"]["uml"] == target_schema()
    shared = graph_schema()["$defs"]
    for name in ("Entity", "Relationship", "Signature", "Parameter", "Visibility", "TargetScope"):
        assert schema["$defs"]["uml"]["$defs"][name] == shared[name]
    validator = Draft202012Validator(schema)
    validator.validate(_contract())
    validator.validate(json.loads(contract_bytes(parse_contract(_contract()))))
    old = _contract()
    old["schema_version"] = "2.1.0"
    assert list(validator.iter_errors(old))


@pytest.mark.parametrize(
    ("contract_version", "target_version", "accepted"),
    [("2.3.0", "1.3.0", False), ("2.3.0", "1.2.0", True), ("2.4.0", "1.3.0", True)],
)
def test_uml_target_version_matches_outer_contract_schema(
    contract_version: str, target_version: str, accepted: bool
) -> None:
    raw = _contract()
    raw["schema_version"] = contract_version
    raw["declarations"]["uml"]["schema_version"] = target_version
    schema_names = (
        ("architecture-contract-2.3.schema.json", "architecture-contract.schema.json")
        if contract_version == "2.3.0"
        else ("architecture-contract.schema.json",)
    )
    for schema_name in schema_names:
        schema = json.loads((Path(__file__).parents[1] / "schema" / schema_name).read_bytes())
        schema_errors = list(Draft202012Validator(schema).iter_errors(raw))
        assert bool(schema_errors) is (not accepted), schema_name
    if accepted:
        parsed = parse_contract(raw)
        assert parsed.declarations.uml.schema_version == target_version
    else:
        with pytest.raises(
            ValueError,
            match="UML schema_version 1.3.0 requires contract schema_version 2.4.0",
        ):
            parse_contract(raw)


@pytest.mark.parametrize(("contract_version", "accepted"), [("2.3.0", False), ("2.4.0", True)])
def test_planned_component_lifecycle_matches_contract_schema_version(
    contract_version: str, accepted: bool
) -> None:
    raw = _contract()
    raw["schema_version"] = contract_version
    component = raw["components"][0]
    component["packages"] = []
    component.pop("namespace")
    component["lifecycle"] = "planned"

    schema_names = (
        ("architecture-contract-2.3.schema.json", "architecture-contract.schema.json")
        if contract_version == "2.3.0"
        else ("architecture-contract.schema.json",)
    )
    for schema_name in schema_names:
        schema = json.loads((Path(__file__).parents[1] / "schema" / schema_name).read_bytes())
        schema_errors = list(Draft202012Validator(schema).iter_errors(raw))
        assert bool(schema_errors) is (not accepted), schema_name
    if accepted:
        parsed = parse_contract(raw)
        assert parsed.components[0].lifecycle.value == "planned"
        with pytest.raises(
            ValueError, match="component lifecycle requires contract schema_version 2.4.0"
        ):
            contract_bytes(replace(parsed, schema_version=ContractVersion.V2_3))
    else:
        with pytest.raises(ValueError, match="lifecycle requires contract schema_version 2.4.0"):
            parse_contract(raw)


def test_contract_encoder_rejects_uml_target_version_newer_than_contract() -> None:
    raw = _contract()
    raw["schema_version"] = "2.3.0"
    raw["declarations"]["uml"]["schema_version"] = "1.2.0"
    parsed = parse_contract(raw)
    declarations = replace(
        parsed.declarations,
        uml=replace(parsed.declarations.uml, schema_version=GraphSchemaVersion.V1_3_0),
    )
    with pytest.raises(
        ValueError,
        match="UML schema_version 1.3.0 requires contract schema_version 2.4.0",
    ):
        contract_bytes(replace(parsed, declarations=declarations))


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

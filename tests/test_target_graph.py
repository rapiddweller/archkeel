# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Independent UML intent must use the shared types and survive contract round trips."""

import hashlib
import json
import subprocess
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from test_architecture_demo import _prepare_repo

from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.check.run import observe_revision
from archkeel.check.uml import assemble_uml
from archkeel.check.uml_compare import compare_graphs
from archkeel.check.validation.references import reference_diagnostics
from archkeel.cli.config import load_config
from archkeel.cli.observe import observe
from archkeel.ir.architecture_graph import (
    ArchitectureGraph,
    ArchitectureReport,
    AssessmentStatus,
    CompletenessMode,
    ComponentIntent,
    ComponentLifecycle,
    ComponentRole,
    Entity,
    EntityKind,
    GraphSchemaVersion,
    OriginKind,
    PresenceKind,
    Relationship,
    RelationshipKind,
    ReportFinding,
    ReportSchemaVersion,
    Signature,
    TargetScope,
    Visibility,
)
from archkeel.ir.codec import (
    contract_bytes,
    decode_canonical_model,
    load_inside_contract_tree,
    parse_contract,
    parse_observation,
    value_bytes,
)
from archkeel.ir.contract_version import ContractVersion
from archkeel.ir.dependency import ModuleSelection
from archkeel.ir.graph_codec import (
    WireComponentSelectorError,
    graph_bytes,
    parse_graph,
    parse_report,
    parse_target,
    report_bytes,
    target_payload,
)
from archkeel.ir.model import Evidence
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.target_graph import declared_graph, declared_tree_graph
from archkeel.ir.target_records import recorded_target_graph
from archkeel.ir.widening import contract_widenings
from archkeel.render.html import _html_report_payload, render_architecture_pages
from tools.architecture_graph_schema import (
    graph_schema,
    projection_schema,
    report_schema,
    target_schema,
)


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


@pytest.mark.parametrize("nested", [False, True])
def test_permission_producers_agree_and_preserve_independent_approval(tmp_path, nested):
    import hashlib

    root, config = _nested_repository(tmp_path) if nested else _repository(tmp_path)
    for path in (config.contract, "inside.json", "leaf.json") if nested else (config.contract,):
        raw = _permission_contract(json.loads((root / path).read_bytes()))
        (root / path).write_text(json.dumps(raw))
    data = (root / config.contract).read_bytes()
    tree = load_inside_contract_tree(
        config.contract,
        parse_contract(json.loads(data)),
        hashlib.sha256(data).hexdigest(),
        config.contract,
        lambda path: ((root / path).read_bytes(), path),
    )
    independent = declared_tree_graph(tree, root_path=config.contract)
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and not result.diagnostics
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    declaration = next(item for item in model.records("declarations") if item.kind == "uml_target")
    assert recorded_target_graph(model, declaration) == independent
    permissions = tuple(item for item in independent.relationships if item.kind == "requires")
    assert len(permissions) == (3 if nested else 1)
    assert all(
        item.through == ("sample.core.peer",) and item.decided_by == "agent" for item in permissions
    )
    assert not any(item.expression for item in permissions)
    assert parse_graph(json.loads(graph_bytes(independent))) == independent


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


def test_report_html_marks_ambiguous_target_unavailable(tmp_path: Path) -> None:
    fixture = Path(__file__).parents[1] / "fixtures" / "planned-component-policy"
    raw = json.loads((fixture / "architecture-contract.json").read_text())
    active = next(owner for owner in raw["components"] if owner["id"] == "fixture-source")
    active["packages"] = ["archkeel"]
    active["exact_modules"] = []
    root = _prepare_repo(
        tmp_path,
        {"architecture-contract.json": json.dumps(raw)},
        fixture,
    )
    config = load_config(root, "archkeel.toml")
    result, architecture = run_report(root, config=config, analyzer=observe)

    assert architecture is not None
    pages = render_architecture_pages(
        result,
        architecture,
        repository="fixture",
        architecture_href="architecture.json",
    )
    main = next(payload.decode("utf-8") for name, payload in pages if name.endswith(".report.html"))
    detail = next(
        payload.decode("utf-8") for name, payload in pages if name.endswith(".detail.html")
    )
    embedded = detail.split('<script id="flow-data" type="application/json">', 1)[1]
    report = json.loads(embedded.split("</script>", 1)[0])

    assert report["target"] is None
    assert report["comparison"] is None
    assert "UNKNOWN" in report["unavailable"]
    assert "archkeel.mcp.server:McpServer" in report["unavailable"]
    assert "UNKNOWN" in detail
    assert "archkeel.mcp.server:McpServer" in detail
    assert "UNKNOWN" in main
    assert "archkeel.mcp.server:McpServer" in main
    assert "no rule is declared" not in detail
    assert "Whole-run rules: UNKNOWN" in detail
    assert "no rule is declared" not in main
    report_wire = {
        key: report[key]
        for key in (
            "observed",
            "target",
            "comparison",
            "unavailable",
            "schema_version",
            "findings",
            "memberships",
            "decision_gaps",
        )
    }
    assert parse_report(report_wire).target is None

    observation = parse_observation(decode_canonical_model(json.loads(architecture)))
    source_report = architecture_report(observation)
    assert source_report.observed is not None
    source_finding = ReportFinding(
        "source-finding",
        "unknown",
        "Observed source evidence",
        AssessmentStatus.UNKNOWN,
        (),
        (),
        (source_report.observed.entities[0].id,),
        (),
        (),
    )
    unlinked_finding = replace(
        source_finding,
        id="unlinked-finding",
        graph_subject_ids=(),
    )
    mixed_finding = replace(
        source_finding,
        id="mixed-finding",
        graph_subject_ids=(source_report.observed.entities[0].id, "mcp"),
    )
    safe_report, _, warning = _html_report_payload(
        replace(source_report, findings=(source_finding, unlinked_finding, mixed_finding))
    )
    assert warning is not None and "UNKNOWN" in warning
    assert "findings not attributable only to source graph omitted" in warning
    assert safe_report.findings == (source_finding,)


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


def test_permission_identity_survives_reordering_slices_and_duplicate_entries(tmp_path):
    raw = _permission_contract()
    owner = raw["components"][0]
    narrowed = owner["requires"][0]
    narrowed["through"].append("sample.core.peer:Port")
    inherited = {"component": "peer", "rationale": "Use the published boundary."}
    owner["requires"].extend([dict(narrowed), inherited])
    expected = declared_graph(parse_contract(raw))
    permissions = tuple(item for item in expected.relationships if item.kind == "requires")
    assert len(permissions) == len({item.id for item in permissions}) == 3
    assert {(item.through, item.decided_by) for item in permissions} == {
        (("sample.core.peer", "sample.core.peer:Port"), "agent"),
        ((), "architect"),
    }
    reordered = json.loads(json.dumps(raw))
    reordered["components"][0]["requires"].reverse()
    for entry in reordered["components"][0]["requires"]:
        entry.get("through", []).reverse()
    assert declared_graph(parse_contract(reordered)) == expected
    root, config = _repository(tmp_path)
    (root / config.contract).write_text(json.dumps(reordered))
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and not result.diagnostics
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    declaration = next(item for item in model.records("declarations") if item.kind == "uml_target")
    assert recorded_target_graph(model, declaration) == expected
    component_record = next(
        item
        for item in model.records("declarations")
        if item.kind == "component_responsibility" and item.id == "core"
    )
    assert "lifecycle" not in dict(component_record.data.entries)


@pytest.mark.parametrize("root_version", ["2.1.0", "2.2.0"])
def test_nested_uml_uses_one_authenticated_target_and_the_same_independent_graph(
    tmp_path, root_version
):
    import hashlib

    root, config = _nested_repository(tmp_path, root_version)
    payload = (root / config.contract).read_bytes()
    tree = load_inside_contract_tree(
        config.contract,
        parse_contract(json.loads(payload)),
        hashlib.sha256(payload).hexdigest(),
        config.contract,
        lambda path: ((root / path).read_bytes(), path),
    )
    assert not tree.issues
    independent = declared_tree_graph(tree, root_path=config.contract)
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and not result.diagnostics
    observation = parse_observation(decode_canonical_model(json.loads(encoded)))
    targets = tuple(
        item for item in observation.records("declarations") or () if item.kind == "uml_target"
    )
    assert len(targets) == 1
    graph = recorded_target_graph(observation, targets[0])
    assert graph == independent
    intents = {item.component_id: item for item in graph.component_intents}
    assert intents["ROOT"].parent_id is None
    assert intents["core:core"].parent_id == "ROOT"
    assert intents["core:core"].label == "service"
    assert intents["core:service:core"].parent_id == "core:core"
    assert intents["ROOT"].layout_rule_ids == ("core:layout",)
    assert [(item.component_id, len(item.modules)) for item in graph.module_inventories] == [
        ("ROOT", 1),
        ("core:core", 0),
    ]
    assert {item.id for item in graph.entities if item.kind == "class"} == {
        "core:service",
        "core:service:service",
    }
    assert not any(item.evidence_ids for item in graph.entities)
    assert (
        len(
            tuple(
                item
                for item in observation.records("scope_observations") or ()
                if item.kind == "rule_evaluation" and targets[0].id in item.rule_ids
            )
        )
        == 1
    )
    assert parse_graph(json.loads(graph_bytes(graph))) == graph


@pytest.mark.parametrize(
    "field,value", [("parent_id", "other"), ("role", "projection"), ("public", ())]
)
def test_core_rejects_tampered_inside_owners(tmp_path, field, value):
    root, config = _nested_repository(tmp_path)
    original = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    assert original.observation is not None
    owner = next(
        item
        for item in original.observation.records("declarations") or ()
        if item.kind == "inside_component_responsibility"
    )
    fields = {**dict(owner.data.entries), field: value}
    forged = replace(owner, data=replace(owner.data, entries=tuple(fields.items())))
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


def test_incomplete_nested_target_is_not_a_partial_pass(tmp_path):
    root, config = _nested_repository(tmp_path)
    (root / "leaf.json").unlink()
    result, _ = run_report(root, config=config, analyzer=observe)
    assert result.diagnostics and result.declared_rules == "UNKNOWN"


def test_nested_uml_ids_cannot_collide_with_outer_component_ids(tmp_path):
    root, config = _nested_repository(tmp_path)
    outer = json.loads((root / config.contract).read_bytes())
    outer["components"][0]["id"] = "core:service"
    (root / config.contract).write_text(json.dumps(outer))
    result, _ = run_report(root, config=config, analyzer=observe)
    assert result.diagnostics and result.declared_rules == "UNKNOWN"
    assert "collision" in result.diagnostics[0].unknown_claim


@pytest.mark.parametrize(
    "field,value",
    [
        ("component_id", "missing"),
        ("owner_ids", ()),
        ("module_target_ids", ()),
        ("layout_rule_ids", ()),
    ],
)
def test_core_rejects_altered_nested_target_references(tmp_path, field, value):
    root, config = _nested_repository(tmp_path)
    original = assemble_uml(
        observe(
            root,
            roots=config.roots,
            namespace=config.namespace,
            contract=config.contract,
            git_head="a" * 40,
            dirty=False,
            contract_root=root,
        ),
        root,
        config.contract,
    )
    assert original.observation is not None and not original.diagnostics
    declaration = next(
        item
        for item in original.observation.records("declarations") or ()
        if item.kind == "uml_target"
    )
    levels = declaration.data.get("inside_levels")
    changed = replace(levels[0], entries=tuple({**dict(levels[0].entries), field: value}.items()))
    data = replace(
        declaration.data,
        entries=tuple(
            {**dict(declaration.data.entries), "inside_levels": (changed, *levels[1:])}.items()
        ),
    )
    forged = replace(declaration, data=data)
    sections = tuple(
        replace(
            section,
            records=tuple(forged if item.id == forged.id else item for item in section.records),
        )
        for section in original.observation.sections
    )
    result = assemble_uml(
        replace(original, observation=replace(original.observation, sections=sections)),
        root,
        config.contract,
    )
    assert result.diagnostics


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


def test_core_authenticates_physical_intent_from_the_declaration_revision(tmp_path: Path) -> None:
    root, config = _repository(tmp_path)
    raw = _physical_contract()
    (root / config.contract).write_text(json.dumps(raw))
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert not result.diagnostics and encoded is not None
    observation = parse_observation(decode_canonical_model(json.loads(encoded)))
    declaration = next(
        record
        for record in observation.records("declarations") or ()
        if record.kind == "uml_target"
    )
    assert "module_inventories" not in dict(declaration.data.entries)
    assert "layout_rules" not in dict(declaration.data.entries)
    assert recorded_target_graph(observation, declaration) == declared_graph(
        parse_contract(raw), contract_path=config.contract
    )


@pytest.mark.parametrize("field", ["module_target_ids", "layout_rule_ids"])
def test_core_rejects_tampered_physical_intent_in_a_recorded_target(
    tmp_path: Path, field: str
) -> None:
    root, config = _repository(tmp_path)
    (root / config.contract).write_text(json.dumps(_physical_contract()))
    original = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    assembled = assemble_uml(original, root, config.contract)
    assert assembled.observation is not None and not assembled.diagnostics
    declaration = next(
        record
        for record in assembled.observation.records("declarations") or ()
        if record.kind == "uml_target"
    )
    data = dict(declaration.data.entries)
    data[field] = ()
    forged = replace(declaration, data=replace(declaration.data, entries=tuple(data.items())))
    sections = tuple(
        replace(
            section,
            records=tuple(
                forged if record.id == declaration.id else record for record in section.records
            ),
        )
        for section in assembled.observation.sections
    )
    result = assemble_uml(
        replace(assembled, observation=replace(assembled.observation, sections=sections)),
        root,
        config.contract,
    )
    assert result.diagnostics
    assert "conflicts with recorded content" in result.diagnostics[0].unknown_claim


@pytest.mark.parametrize(
    "kind,changes",
    [
        ("module_target", {"responsibility": "Invent another responsibility."}),
        ("module_target", {"path": "sample/invented.py"}),
        ("root_layout", {"allowed_children": ("sample.invented",)}),
        ("root_layout", {"decided_by": "agent"}),
    ],
)
@pytest.mark.parametrize("explicit_uml", [False, True])
def test_core_rejects_tampered_canonical_physical_declarations(
    tmp_path, kind, changes, explicit_uml
):
    root, config = _repository(tmp_path)
    raw = _physical_contract()
    if not explicit_uml:
        raw["schema_version"] = "2.1.0"
        del raw["declarations"]["uml"]
    (root / config.contract).write_text(json.dumps(raw))
    original = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    assert original.observation is not None
    record = next(
        item for item in original.observation.records("declarations") or () if item.kind == kind
    )
    data = {**dict(record.data.entries), **changes}
    forged = replace(record, data=replace(record.data, entries=tuple(data.items())))
    sections = tuple(
        replace(
            section,
            records=tuple(forged if item.id == record.id else item for item in section.records),
        )
        for section in original.observation.sections
    )
    result = assemble_uml(
        replace(original, observation=replace(original.observation, sections=sections)),
        root,
        config.contract,
    )
    assert result.diagnostics
    assert "physical declaration differs" in result.diagnostics[0].unknown_claim


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
        {"role": "projection"},
        {"public": []},
        {"planned": ["sample.core:Invented"]},
        {"exact_modules": ["sample.other"]},
        {"forbidden_responsibilities": ["Invent policy."]},
        {"decided_by": "agent"},
        {"inside": "invented.json"},
    ],
)
def test_core_rejects_tampered_component_intent(tmp_path: Path, changes) -> None:
    root, config = _repository(tmp_path)
    original = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    assert original.observation is not None
    owner = next(
        record
        for record in original.observation.records("declarations") or ()
        if record.kind == "component_responsibility"
    )
    forged_data = {
        **dict(owner.data.entries),
        **{
            key: tuple(value) if isinstance(value, list) else value
            for key, value in changes.items()
        },
    }
    forged_owner = replace(owner, data=replace(owner.data, entries=tuple(forged_data.items())))
    sections = tuple(
        replace(
            section,
            records=tuple(
                forged_owner if record.id == owner.id else record for record in section.records
            ),
        )
        for section in original.observation.sections
    )
    forged = replace(original, observation=replace(original.observation, sections=sections))
    result = assemble_uml(forged, root, config.contract)
    assert result.diagnostics
    assert "component owner differs" in result.diagnostics[0].unknown_claim


def test_authenticated_component_intent_uses_the_same_producer_values(tmp_path: Path) -> None:
    root, config = _repository(tmp_path)
    raw = _contract()
    raw["components"][0].update(role="foundation", public=[], planned=["sample.core:Future"])
    (root / config.contract).write_text(json.dumps(raw))
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert result.exit_code == 0
    assert encoded is not None
    observation = parse_observation(decode_canonical_model(json.loads(encoded)))
    declaration = next(
        record
        for record in observation.records("declarations") or ()
        if record.kind == "uml_target"
    )
    assert recorded_target_graph(observation, declaration) == declared_graph(parse_contract(raw))


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


def test_uml_contract_schema_preserves_the_frozen_target_1_3_definition() -> None:
    schema = json.loads(
        (Path(__file__).parents[1] / "schema/architecture-contract.schema.json").read_bytes()
    )
    assert schema["$defs"]["uml"]["$id"] == "urn:archkeel:architecture-target:1.3.0"
    assert hashlib.sha256(
        json.dumps(schema["$defs"]["uml"], sort_keys=True).encode()
    ).hexdigest() == ("f57d3653790a83c65a5531e220c6f90380bc43d38827631d372ff9490b1d178b")
    validator = Draft202012Validator(schema)
    validator.validate(_contract())
    validator.validate(json.loads(contract_bytes(parse_contract(_contract()))))
    old = _contract()
    old["schema_version"] = "2.1.0"
    assert list(validator.iter_errors(old))


def test_system_landscape_schema_is_generated_from_the_shared_dataclasses() -> None:
    root = Path(__file__).parents[1]
    schema = json.loads((root / "schema/architecture-contract-3.15.schema.json").read_bytes())
    assert schema["$defs"]["uml"] == target_schema()
    assert schema["$defs"]["uml"]["$id"] == "urn:archkeel:architecture-target:1.4.0"
    shared = graph_schema()["$defs"]
    for name in ("Entity", "Relationship", "Signature", "Parameter", "Visibility", "TargetScope"):
        assert schema["$defs"]["uml"]["$defs"][name] == shared[name]


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


def test_greenfield_system_manifest_round_trips_runtime_communication() -> None:
    root = Path(__file__).parents[1]
    raw = json.loads(
        (root / "fixtures" / "F-system-landscape" / "architecture-contract.json").read_bytes()
    )
    contract = parse_contract(raw)
    schema = json.loads((root / "schema" / "architecture-contract-3.15.schema.json").read_bytes())
    Draft202012Validator(schema).validate(raw)

    assert not contract.components
    assert contract.declarations is not None
    assert contract.declarations.uml is not None
    assert contract.declarations.uml.schema_version.value == "1.4.0"

    graph = declared_graph(contract, contract_path="architecture-contract.json")
    assert graph.origin == OriginKind.DECLARED
    assert not contract.components
    assert {entity.kind.value for entity in graph.entities} == {"runtime_unit", "external_system"}
    assert len(graph.relationships) == 1
    relationship = graph.relationships[0]
    assert relationship.kind.value == "communicates"
    assert relationship.source_id == "runtime-api"
    assert relationship.target_id == "external-ledger"
    assert relationship.protocol == "HTTPS"
    assert not graph.evidence
    assert parse_graph(json.loads(graph_bytes(graph))) == graph
    comparison = compare_graphs(
        ArchitectureGraph(OriginKind.OBSERVED, schema_version=GraphSchemaVersion.V1_4_0), graph
    )
    assert {assessment.status for assessment in comparison.assessments} == {
        AssessmentStatus.UNKNOWN
    }
    assert {assessment.subject_id for assessment in comparison.assessments} == {
        "runtime-api",
        "external-ledger",
        "api-ledger-communication",
    }
    report = ArchitectureReport(
        ArchitectureGraph(OriginKind.OBSERVED, schema_version=GraphSchemaVersion.V1_4_0),
        graph,
        unavailable="No source snapshot was supplied.",
        schema_version=ReportSchemaVersion.V1_4_0,
    )
    report_payload = json.loads(report_bytes(report))
    assert parse_report(report_payload) == report
    Draft202012Validator(report_schema()).validate(report_payload)


def test_system_landscape_wire_schemas_reject_target_only_values_as_observed() -> None:
    root = Path(__file__).parents[1]
    raw = json.loads(
        (root / "fixtures" / "F-system-landscape" / "architecture-contract.json").read_bytes()
    )
    graph = declared_graph(parse_contract(raw), contract_path="architecture-contract.json")
    target_payload = json.loads(graph_bytes(graph))
    graph_validator = Draft202012Validator(graph_schema())
    assert graph_validator.is_valid(target_payload)

    observed_payload = {**target_payload, "origin": OriginKind.OBSERVED.value}
    assert not graph_validator.is_valid(observed_payload)
    with pytest.raises(ValueError):
        parse_graph(observed_payload)

    observed = ArchitectureGraph(OriginKind.OBSERVED, schema_version=GraphSchemaVersion.V1_4_0)
    report = ArchitectureReport(
        observed,
        graph,
        unavailable="No source snapshot was supplied.",
        schema_version=ReportSchemaVersion.V1_4_0,
    )
    report_payload = json.loads(report_bytes(report))
    report_validator = Draft202012Validator(report_schema())
    assert report_validator.is_valid(report_payload)

    report_payload["observed"] = observed_payload
    assert not report_validator.is_valid(report_payload)
    with pytest.raises(ValueError):
        parse_report(report_payload)


def test_system_landscape_never_matches_source_entities_by_qualified_name() -> None:
    root = Path(__file__).parents[1]
    raw = json.loads(
        (root / "fixtures" / "F-system-landscape" / "architecture-contract.json").read_bytes()
    )
    target = declared_graph(parse_contract(raw), contract_path="architecture-contract.json")
    observed = ArchitectureGraph(
        OriginKind.OBSERVED,
        (
            Entity(
                "source-api-class",
                EntityKind.CLASS,
                "system_manifest.api_service",
                "architecture",
                presence=PresenceKind.DEFINED,
                evidence_ids=("source-api-evidence",),
            ),
        ),
        evidence=(Evidence("source-api-evidence", "src/api.py", 1, 1, 0, "class API"),),
        schema_version=GraphSchemaVersion.V1_4_0,
    )

    comparison = compare_graphs(observed, target)

    assert not comparison.correspondences
    assert all(item.status is AssessmentStatus.UNKNOWN for item in comparison.assessments)


def test_target_only_scope_does_not_match_a_source_entity() -> None:
    root = Path(__file__).parents[1]
    raw = json.loads(
        (root / "fixtures" / "F-system-landscape" / "architecture-contract.json").read_bytes()
    )
    target = declared_graph(parse_contract(raw), contract_path="architecture-contract.json")
    target = replace(
        target,
        target_scopes=(
            TargetScope(
                "runtime-api",
                CompletenessMode.OPEN,
                "Describe runtime intent.",
                ("docs/target.md",),
                entity_kinds=(EntityKind.CLASS,),
            ),
        ),
    )
    observed = ArchitectureGraph(
        OriginKind.OBSERVED,
        (
            Entity(
                "source-api-class",
                EntityKind.CLASS,
                "system_manifest.api_service",
                "architecture",
                presence=PresenceKind.DEFINED,
                evidence_ids=("source-api-evidence",),
            ),
        ),
        evidence=(Evidence("source-api-evidence", "src/api.py", 1, 1, 0, "class API"),),
        schema_version=GraphSchemaVersion.V1_4_0,
    )

    comparison = compare_graphs(observed, target)
    scope = next(
        item
        for item in comparison.assessments
        if item.subject_id == "runtime-api" and item.aspect.value == "completeness"
    )

    assert scope.status is AssessmentStatus.UNKNOWN
    assert not scope.observed_ids


def test_non_communication_relationship_does_not_match_target_only_endpoints() -> None:
    root = Path(__file__).parents[1]
    raw = json.loads(
        (root / "fixtures" / "F-system-landscape" / "architecture-contract.json").read_bytes()
    )
    target = declared_graph(parse_contract(raw), contract_path="architecture-contract.json")
    target = replace(
        target,
        relationships=target.relationships
        + (
            Relationship(
                "target-call",
                RelationshipKind.CALLS,
                "runtime-api",
                "external-ledger",
                provenance=("docs/target.md",),
            ),
        ),
    )
    observed = ArchitectureGraph(
        OriginKind.OBSERVED,
        (
            Entity(
                "source-api-class",
                EntityKind.CLASS,
                "system_manifest.api_service",
                "architecture",
                presence=PresenceKind.DEFINED,
                evidence_ids=("source-api-evidence",),
            ),
            Entity(
                "source-ledger-class",
                EntityKind.CLASS,
                "system_manifest.ledger",
                "architecture",
                presence=PresenceKind.DEFINED,
                evidence_ids=("source-ledger-evidence",),
            ),
        ),
        (
            Relationship(
                "source-call",
                RelationshipKind.CALLS,
                "source-api-class",
                "source-ledger-class",
                resolution="resolved",
                evidence_ids=("source-call-evidence",),
            ),
        ),
        evidence=(
            Evidence("source-api-evidence", "src/api.py", 1, 1, 0, "class API"),
            Evidence("source-ledger-evidence", "src/ledger.py", 1, 1, 0, "class Ledger"),
            Evidence("source-call-evidence", "src/api.py", 2, 2, 0, "ledger.send()"),
        ),
        schema_version=GraphSchemaVersion.V1_4_0,
    )

    comparison = compare_graphs(observed, target)
    call = next(item for item in comparison.assessments if item.subject_id == "target-call")

    assert call.status is AssessmentStatus.UNKNOWN
    assert not call.observed_ids


def test_communication_stays_in_report_graph_and_out_of_focused_outputs(tmp_path) -> None:
    root = Path(__file__).parents[1]
    raw = json.loads(
        (root / "fixtures" / "F-system-landscape" / "architecture-contract.json").read_bytes()
    )
    repo = _prepare_repo(
        tmp_path,
        {
            "src/api.py": "class API: pass\n",
            "architecture-contract.json": json.dumps(raw),
            "docs/target.md": "The contract declares the system landscape.\n",
        },
    )
    config = ScanConfig(("src",), "system_manifest", "architecture-contract.json", "0" * 64)
    result, encoded = run_report(
        repo, config=config, analyzer=observe, only_architecture=True, full_architecture=True
    )
    assert encoded is not None
    observation = parse_observation(decode_canonical_model(json.loads(encoded)))
    report = architecture_report(observation)
    assert report.target is not None
    assert any(item.kind is RelationshipKind.COMMUNICATES for item in report.target.relationships)

    projection = result.architecture_projection
    assert projection is not None
    assert not any(
        item.kind is RelationshipKind.COMMUNICATES for item in projection.required_relationships
    )
    projection_payload = json.loads(json.dumps(asdict(projection)))
    Draft202012Validator(projection_schema()).validate(projection_payload)

    from test_result_schema import _validator

    from archkeel.ir.codec import result_payload

    command_payload = result_payload(result)
    command_validator = _validator("command-result-11.0.schema.json").evolve(
        schema={"$ref": "urn:archkeel:architecture-command:2.0.0"}
    )
    command_validator.validate(command_payload)
    assert not any(
        item["kind"] == RelationshipKind.COMMUNICATES.value
        for item in command_payload["architecture_projection"]["required_relationships"]
    )
    report_payload = json.loads(report_bytes(report))
    Draft202012Validator(report_schema()).validate(report_payload)


def test_report_1_4_accepts_legacy_graph_1_3() -> None:
    observed = ArchitectureGraph(OriginKind.OBSERVED, schema_version=GraphSchemaVersion.V1_3_0)
    report = ArchitectureReport(
        observed,
        None,
        unavailable="No target was declared.",
        schema_version=ReportSchemaVersion.V1_4_0,
    )

    payload = json.loads(report_bytes(report))

    assert parse_report(payload) == report
    Draft202012Validator(report_schema()).validate(payload)


def test_system_landscape_contract_enforces_protocol_and_presence_at_each_boundary() -> None:
    root = Path(__file__).parents[1]
    raw = json.loads(
        (root / "fixtures" / "F-system-landscape" / "architecture-contract.json").read_bytes()
    )
    schema = json.loads((root / "schema" / "architecture-contract-3.15.schema.json").read_bytes())
    validator = Draft202012Validator(schema)
    parsed = parse_contract(raw)
    uml = parsed.declarations.uml

    without_protocol = replace(
        uml,
        relationships=tuple(replace(edge, protocol=None) for edge in uml.relationships),
    )
    encoded_without_protocol = json.loads(
        contract_bytes(
            replace(parsed, declarations=replace(parsed.declarations, uml=without_protocol))
        )
    )
    assert "protocol" not in encoded_without_protocol["declarations"]["uml"]["relationships"][0]

    invalid_protocol = json.loads(json.dumps(raw))
    invalid_protocol["declarations"]["uml"]["relationships"][0]["kind"] = "imports"
    assert not validator.is_valid(invalid_protocol)
    with pytest.raises(ValueError):
        parse_contract(invalid_protocol)

    with pytest.raises(ValueError, match="protocol"):
        replace(uml.relationships[0], kind=RelationshipKind.IMPORTS)

    for kind in ("runtime_unit", "external_system"):
        invalid_presence = json.loads(json.dumps(raw))
        entity = next(
            item
            for item in invalid_presence["declarations"]["uml"]["entities"]
            if item["kind"] == kind
        )
        entity["presence"] = "defined"
        assert not validator.is_valid(invalid_presence)
        with pytest.raises(ValueError):
            parse_contract(invalid_presence)

        entity_model = next(item for item in uml.entities if item.kind.value == kind)
        changed_entity = replace(entity_model, presence=PresenceKind.DEFINED)
        invalid_entities = tuple(
            changed_entity if item.id == entity_model.id else item for item in uml.entities
        )
        invalid_uml = replace(uml, entities=invalid_entities)
        invalid_declarations = replace(parsed.declarations, uml=invalid_uml)
        with pytest.raises(ValueError):
            contract_bytes(replace(parsed, declarations=invalid_declarations))


@pytest.mark.parametrize("boundary", ("target", "graph", "report"))
def test_null_protocol_is_not_a_wire_absence(boundary: str) -> None:
    root = Path(__file__).parents[1]
    contract_wire = json.loads(
        (root / "fixtures" / "F-system-landscape" / "architecture-contract.json").read_bytes()
    )
    uml_wire = contract_wire["declarations"]["uml"]
    uml_wire["relationships"][0].pop("protocol")
    target = parse_target(uml_wire)
    target_wire = json.loads(json.dumps(target_payload(target)))
    graph = declared_graph(
        parse_contract(contract_wire), contract_path="architecture-contract.json"
    )
    graph_wire = json.loads(graph_bytes(graph))
    report = ArchitectureReport(
        ArchitectureGraph(OriginKind.OBSERVED, schema_version=GraphSchemaVersion.V1_4_0),
        graph,
        unavailable="No source snapshot was supplied.",
        schema_version=ReportSchemaVersion.V1_4_0,
    )
    report_wire = json.loads(report_bytes(report))
    payload, parser, schema = {
        "target": (target_wire, parse_target, target_schema()),
        "graph": (graph_wire, parse_graph, graph_schema()),
        "report": (report_wire, parse_report, report_schema()),
    }[boundary]

    Draft202012Validator(schema).validate(payload)
    assert parser(payload)

    malformed = json.loads(json.dumps(payload))
    relationships = (
        malformed["relationships"] if boundary != "report" else malformed["target"]["relationships"]
    )
    relationships[0]["protocol"] = None

    assert not Draft202012Validator(schema).is_valid(malformed)
    with pytest.raises(ValueError, match="protocol"):
        parser(malformed)


@pytest.mark.parametrize(
    ("contract_version", "target_version", "accepted"),
    [
        ("2.4.0", "1.4.0", False),
        ("3.14.0", "1.4.0", False),
        ("3.15.0", "1.4.0", True),
        ("2.4.0", "1.3.0", True),
        ("3.14.0", "1.3.0", True),
    ],
)
def test_system_landscape_feature_does_not_change_historical_contracts(
    contract_version: str, target_version: str, accepted: bool
) -> None:
    raw = _contract()
    raw["schema_version"] = contract_version
    raw["declarations"]["uml"]["schema_version"] = target_version
    schema_name = {
        "2.4.0": "architecture-contract.schema.json",
        "3.14.0": "architecture-contract-3.14.schema.json",
        "3.15.0": "architecture-contract-3.15.schema.json",
    }[contract_version]
    if accepted:
        parsed = parse_contract(raw)
        assert parsed.declarations.uml.schema_version.value == target_version
        schema = json.loads((Path(__file__).parents[1] / "schema" / schema_name).read_bytes())
        Draft202012Validator(schema).validate(raw)
    else:
        schema = json.loads((Path(__file__).parents[1] / "schema" / schema_name).read_bytes())
        schema_errors = list(Draft202012Validator(schema).iter_errors(raw))
        assert schema_errors, schema_name
        with pytest.raises(ValueError):
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

    raw["schema_version"] = "3.14.0"
    raw["declarations"]["uml"]["schema_version"] = "1.3.0"
    parsed = parse_contract(raw)
    declarations = replace(
        parsed.declarations,
        uml=replace(parsed.declarations.uml, schema_version=GraphSchemaVersion.V1_4_0),
    )
    with pytest.raises(
        ValueError,
        match="UML schema_version 1.4.0 requires contract schema_version 3.15.0",
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


@pytest.mark.parametrize("version", ["1.0.0", "1.1.0"])
def test_core_records_known_signature_failure_and_unknown_unavailable_uml_facts(
    tmp_path: Path,
    version: str,
) -> None:
    root, config = _repository(tmp_path)
    contract = _contract()
    contract["declarations"]["uml"]["schema_version"] = version
    (root / "contract.json").write_text(json.dumps(contract))
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert result.exit_code == 0
    assert result.observation_complete == "PASS"
    assert result.declared_rules == "FAIL"
    assert encoded is not None
    observation = parse_observation(decode_canonical_model(json.loads(encoded)))
    intent = next(
        item for item in observation.records("declarations") or () if item.kind == "uml_target"
    )
    assert (
        parse_target(json.loads(value_bytes(intent.data.get("target"))))
        == parse_contract(contract).declarations.uml
    )
    assert any(item.kind == "uml_conformance" for item in observation.records("unknowns") or ())
    assert any(item.kind == "uml_conformance" for item in observation.records("violations") or ())


@pytest.mark.parametrize("newest_level", [None, "contract.json", "inside.json", "leaf.json"])
def test_core_uses_the_newest_declared_format_when_combining_inside_targets(tmp_path, newest_level):
    root, config = _nested_repository(tmp_path)
    root_contract = json.loads((root / config.contract).read_bytes())
    root_contract.setdefault("declarations", {})["uml"] = {"schema_version": "1.0.0"}
    (root / config.contract).write_text(json.dumps(root_contract))
    path = root / (newest_level or config.contract)
    contract = json.loads(path.read_bytes())
    contract["declarations"]["uml"]["schema_version"] = "1.1.0" if newest_level else "1.0.0"
    path.write_text(json.dumps(contract))
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert result.exit_code == 0 and encoded is not None
    observation = parse_observation(decode_canonical_model(json.loads(encoded)))
    intent = next(
        item for item in observation.records("declarations") or () if item.kind == "uml_target"
    )
    assert parse_target(json.loads(value_bytes(intent.data.get("target")))).schema_version == (
        "1.1.0" if newest_level else "1.0.0"
    )


def test_snapshot_core_reads_target_from_the_materialized_declaration_revision(
    tmp_path: Path,
) -> None:
    root, config = _repository(tmp_path)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    result = observe_revision(observe, root, revision, config, declared_at=revision)
    assert result.diagnostics == ()
    assert result.observation is not None
    assert any(
        item.kind == "uml_target" for item in result.observation.records("declarations") or ()
    )


def test_core_rejects_changed_target_bytes_after_observation(tmp_path: Path) -> None:
    root, config = _repository(tmp_path)
    original = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    changed = _contract()
    changed["declarations"]["uml"]["entities"][0]["responsibilities"] = ["A changed target."]
    (root / config.contract).write_text(json.dumps(changed))
    result = assemble_uml(original, root, config.contract)
    assert result.diagnostics
    assert "authenticated contract" in result.diagnostics[0].unknown_claim


def test_core_refuses_a_contract_symlink_outside_its_declaration_root(tmp_path: Path) -> None:
    root, config = _repository(tmp_path / "repository")
    original = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    path = root / config.contract
    outside = tmp_path / "outside.json"
    outside.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(outside)
    result = assemble_uml(original, root, config.contract)
    assert result.diagnostics
    assert "escapes its declaration root" in result.diagnostics[0].unknown_claim


def test_core_assembly_does_not_duplicate_its_own_declarations(tmp_path: Path) -> None:
    root, config = _repository(tmp_path)
    original = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    assembled = assemble_uml(original, root, config.contract)
    assert assemble_uml(assembled, root, config.contract) == assembled


@pytest.mark.parametrize("version", ["2.1.0", "2.2.0"])
def test_legacy_target_uses_the_standard_graph_without_adding_a_rule(tmp_path, version):
    from archkeel.ir.decisions import rule_assessments

    raw = _permission_contract()
    raw["schema_version"] = version
    del raw["declarations"]["uml"]
    root, config = _repository(tmp_path)
    (root / config.contract).write_text(json.dumps(raw))
    original = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    assert original.observation is not None and not original.diagnostics
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and not result.diagnostics
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    targets = [
        record for record in model.records("declarations") if record.kind == "architecture_target"
    ]
    assert len(targets) == 1
    assert recorded_target_graph(model, targets[0]) == declared_graph(
        parse_contract(raw), contract_path=config.contract
    )
    assert rule_assessments(model, undecided_by_rule={}) == rule_assessments(
        original.observation, undecided_by_rule={}
    )
    assert model.records("scope_observations") == original.observation.records("scope_observations")
    assert model.records("violations") == original.observation.records("violations")
    assert model.records("unknowns") == original.observation.records("unknowns")
    assert not any(record.kind == "uml_target" for record in model.records("declarations"))
    assembled = assemble_uml(original, root, config.contract)
    assert assemble_uml(assembled, root, config.contract) == assembled


@pytest.mark.parametrize(
    "version,explicit_uml", [("2.1.0", False), ("2.2.0", False), ("2.2.0", True)]
)
def test_global_api_intent_is_independent_and_uses_authenticated_records(
    tmp_path, version, explicit_uml
):
    raw = _contract()
    raw["schema_version"] = version
    if not explicit_uml:
        del raw["declarations"]["uml"]
    raw["declarations"].update(
        public_api=["sample.core:Future", "sample.core:Service"],
        public_api_provenance=["docs/target.md", "docs/other.md"],
    )
    root, config = _repository(tmp_path)
    (root / "docs/other.md").write_text("Independent API intent.\n")
    (root / config.contract).write_text(json.dumps(raw))
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and not result.diagnostics
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    kind = "uml_target" if explicit_uml else "architecture_target"
    declaration = next(record for record in model.records("declarations") if record.kind == kind)
    graph = recorded_target_graph(model, declaration)
    assert graph == declared_graph(parse_contract(raw), contract_path=config.contract)
    assert {entry.selector for entry in graph.public_api} == set(raw["declarations"]["public_api"])
    records = [
        record for record in model.records("declarations") if record.kind == "declared_public_api"
    ]
    assert {entry.id for entry in graph.public_api} == {record.id for record in records}
    assert all(
        entry.provenance == ("docs/other.md", "docs/target.md") for entry in graph.public_api
    )
    assert parse_graph(json.loads(graph_bytes(graph))) == graph
    Draft202012Validator(graph_schema()).validate(json.loads(graph_bytes(graph)))
    altered = replace(
        model,
        sections=tuple(
            replace(
                section,
                records=tuple(
                    replace(
                        record,
                        data=replace(
                            record.data,
                            entries=tuple(
                                (key, ("source-dependent.Type",) if key == "types" else value)
                                for key, value in record.data.entries
                            ),
                        ),
                    )
                    if record.kind == "declared_public_api"
                    else record
                    for record in section.records
                ),
            )
            for section in model.sections
        ),
    )
    assert recorded_target_graph(altered, declaration) == graph
    raw["declarations"]["public_api"].reverse()
    raw["declarations"]["public_api_provenance"].reverse()
    assert declared_graph(parse_contract(raw), contract_path=config.contract) == graph
    if not explicit_uml:
        assert {entity.kind for entity in graph.entities} == {"component"}


@pytest.mark.parametrize("version", ["2.1.0", "2.2.0"])
def test_api_only_contract_publishes_a_graph_without_a_conformance_rule(tmp_path, version):
    raw = {
        "schema_version": version,
        "components": [],
        "rules": [],
        "declarations": {
            "public_api": ["sample.core:Future"],
            "public_api_provenance": ["docs/target.md"],
        },
    }
    root, config = _repository(tmp_path)
    (root / config.contract).write_text(json.dumps(raw))
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and not result.diagnostics
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    declaration = next(
        record for record in model.records("declarations") if record.kind == "architecture_target"
    )
    graph = recorded_target_graph(model, declaration)
    assert graph == declared_graph(parse_contract(raw), contract_path=config.contract)
    assert [entry.selector for entry in graph.public_api] == ["sample.core:Future"]
    assert graph.public_api[0].provenance == ("docs/target.md",)
    assert not graph.entities and not graph.relationships
    assert not any(
        declaration.id in record.rule_ids
        for section in model.sections
        if section.name != "declarations"
        for record in section.records
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("title", "invented"),
        ("subjects", ("sample.core:Invented",)),
        ("provenance", ("docs/invented.md",)),
        ("qualified_name", "sample.core:Invented"),
    ],
)
def test_core_rejects_forged_global_api_intent(tmp_path, field, value):
    raw = _contract()
    raw["declarations"].update(
        public_api=["sample.core:Service"], public_api_provenance=["docs/target.md"]
    )
    root, config = _repository(tmp_path)
    (root / config.contract).write_text(json.dumps(raw))
    original = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    assert original.observation is not None

    def forge(record):
        if record.kind != "declared_public_api":
            return record
        if field == "qualified_name":
            return replace(
                record,
                data=replace(
                    record.data,
                    entries=tuple(
                        (key, value if key == field else current)
                        for key, current in record.data.entries
                    ),
                ),
            )
        return replace(record, **{field: value})

    forged = replace(
        original,
        observation=replace(
            original.observation,
            sections=tuple(
                replace(section, records=tuple(forge(record) for record in section.records))
                for section in original.observation.sections
            ),
        ),
    )
    result = assemble_uml(forged, root, config.contract)
    assert result.diagnostics
    assert "public API" in result.diagnostics[0].unknown_claim


@pytest.mark.parametrize("change", ["missing", "unexpected", "descriptor"])
def test_public_api_declaration_references_cannot_be_removed_or_invented(tmp_path, change):
    raw = _contract()
    raw["declarations"].update(
        public_api=["sample.core:Service"], public_api_provenance=["docs/target.md"]
    )
    root, config = _repository(tmp_path)
    (root / config.contract).write_text(json.dumps(raw))
    original = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    assembled = assemble_uml(original, root, config.contract)
    assert assembled.observation is not None and not assembled.diagnostics
    records = assembled.observation.records("declarations")
    api = next(record for record in records if record.kind == "declared_public_api")
    if change == "missing":
        records = tuple(record for record in records if record.id != api.id)
    elif change == "unexpected":
        records = (*records, replace(api, id="invented-api"))
    else:
        records = tuple(
            replace(
                record,
                data=replace(
                    record.data,
                    entries=tuple(
                        (key, () if key == "public_api_ids" else value)
                        for key, value in record.data.entries
                    ),
                ),
            )
            if record.kind == "uml_target"
            else record
            for record in records
        )
    forged = replace(
        assembled,
        observation=replace(
            assembled.observation,
            sections=tuple(
                replace(section, records=records) if section.name == "declarations" else section
                for section in assembled.observation.sections
            ),
        ),
    )
    assert assemble_uml(forged, root, config.contract).diagnostics


def test_global_api_intent_cannot_borrow_source_provenance(tmp_path):
    raw = _contract()
    raw["declarations"]["public_api"] = ["sample.core:Future"]
    with pytest.raises(ValueError, match="independent provenance"):
        declared_graph(parse_contract(raw))
    root, config = _repository(tmp_path)
    (root / config.contract).write_text(json.dumps(raw))
    result, _ = run_report(root, config=config, analyzer=observe)
    assert result.diagnostics and result.declared_rules == "UNKNOWN"


def test_global_api_intent_is_not_silently_accepted_in_an_inside_contract(tmp_path):
    root, config = _nested_repository(tmp_path)
    path = root / "inside.json"
    raw = json.loads(path.read_bytes())
    raw["declarations"].update(
        public_api=["sample.core:Future"], public_api_provenance=["docs/target.md"]
    )
    path.write_text(json.dumps(raw))
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and result.diagnostics
    assert "public_api" in result.diagnostics[0].unknown_claim
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    assert not any(
        record.kind in {"architecture_target", "uml_target"}
        for record in model.records("declarations")
    )


@pytest.mark.parametrize("explicit_uml", [False, True])
def test_target_producers_preserve_canonical_component_metadata_order(tmp_path, explicit_uml):
    raw = _permission_contract(_physical_contract())
    if not explicit_uml:
        raw["schema_version"] = "2.1.0"
        del raw["declarations"]["uml"]
    owner = raw["components"][0]
    owner.update(
        packages=["sample.extra", "sample.core"],
        responsibilities=["Z: own storage.", "A: own operations."],
        public=["sample.core:Service", "sample.core:Port"],
        planned=["sample.core:Later", "sample.core:Future"],
        forbidden_responsibilities=["Z: parse sources.", "A: write SVG."],
        provenance=["docs/target.md", "docs/other.md"],
    )
    root, config = _repository(tmp_path)
    raw["rules"][0]["provenance"] = list(owner["provenance"])
    raw["rules"][0]["allowed_children"].reverse()
    (root / "docs/other.md").write_text("Independent boundary intent.\n")
    (root / config.contract).write_text(json.dumps(raw))
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and not result.diagnostics
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    kind = "uml_target" if explicit_uml else "architecture_target"
    declaration = next(record for record in model.records("declarations") if record.kind == kind)
    expected = declared_graph(parse_contract(raw), contract_path=config.contract)
    assert recorded_target_graph(model, declaration) == expected
    for key in (
        "packages",
        "responsibilities",
        "public",
        "planned",
        "forbidden_responsibilities",
        "provenance",
    ):
        owner[key].reverse()
    raw["rules"][0]["provenance"].reverse()
    raw["rules"][0]["allowed_children"].reverse()
    assert declared_graph(parse_contract(raw), contract_path=config.contract) == expected


@pytest.mark.parametrize("change", ["responsibilities", "requires", "public", "role"])
def test_core_authenticates_legacy_owner_intent_before_graph_projection(tmp_path, change):
    raw = _permission_contract()
    raw["schema_version"] = "2.1.0"
    del raw["declarations"]["uml"]
    root, config = _repository(tmp_path)
    (root / config.contract).write_text(json.dumps(raw))
    original = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    model = original.observation
    assert model is not None and not original.diagnostics
    values = {
        "responsibilities": ("Invented responsibility.",),
        "requires": (),
        "public": ("sample.core:Invented",),
        "role": "foundation",
    }
    sections = tuple(
        replace(
            section,
            records=tuple(
                replace(
                    record,
                    data=replace(
                        record.data,
                        entries=tuple(
                            (key, value) for key, value in record.data.entries if key != change
                        )
                        + ((change, values[change]),),
                    ),
                )
                if record.id == "core"
                else record
                for record in section.records
            ),
        )
        for section in model.sections
    )
    result = assemble_uml(
        replace(original, observation=replace(model, sections=sections)), root, config.contract
    )
    assert result.diagnostics and "authenticated contract" in result.diagnostics[0].unknown_claim


@pytest.mark.parametrize("version", ["2.1.0", "2.2.0"])
def test_legacy_inside_levels_and_physical_intent_share_one_graph(tmp_path, version):
    import hashlib

    root, config = _nested_repository(tmp_path)
    for path in (config.contract, "inside.json", "leaf.json"):
        raw = json.loads((root / path).read_bytes())
        raw["schema_version"] = version
        raw.get("declarations", {}).pop("uml", None)
        (root / path).write_text(json.dumps(raw))
    payload = (root / config.contract).read_bytes()
    tree = load_inside_contract_tree(
        config.contract,
        parse_contract(json.loads(payload)),
        hashlib.sha256(payload).hexdigest(),
        config.contract,
        lambda path: ((root / path).read_bytes(), path),
    )
    assert not tree.issues
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and not result.diagnostics
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    targets = [
        record for record in model.records("declarations") if record.kind == "architecture_target"
    ]
    assert len(targets) == 1
    graph = recorded_target_graph(model, targets[0])
    assert graph == declared_tree_graph(tree, root_path=config.contract)
    assert len(graph.component_intents) == 3
    assert {item.parent_id for item in graph.component_intents} == {
        None,
        tree.mounts[0].parent.id,
        tree.mounts[1].parent.id,
    }
    assert len(graph.module_inventories) == 2
    assert any(not item.modules for item in graph.module_inventories)
    assert len(graph.layout_rules) == 1
    assert all(item.kind == "component" for item in graph.entities)
    assert not any(record.kind == "uml_conformance" for record in model.records("unknowns") or ())


def test_incomplete_legacy_inside_report_does_not_claim_a_complete_target_graph(tmp_path):
    root, config = _nested_repository(tmp_path, "2.1.0")
    (root / "inside.json").unlink()
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and result.diagnostics and result.exit_code == 2
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    assert any(
        record.kind == "inside_contract_incomplete" for record in model.records("unknowns") or ()
    )
    assert not any(record.kind == "architecture_target" for record in model.records("declarations"))


@pytest.mark.parametrize("change", ["title", "owners", "target", "extra"])
def test_adapter_cannot_forge_a_compiled_legacy_target(tmp_path, change):
    raw = _permission_contract()
    raw["schema_version"] = "2.1.0"
    del raw["declarations"]["uml"]
    root, config = _repository(tmp_path)
    (root / config.contract).write_text(json.dumps(raw))
    original = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    assembled = assemble_uml(original, root, config.contract)
    model = assembled.observation
    assert model is not None and not assembled.diagnostics
    declaration = next(
        record for record in model.records("declarations") if record.kind == "architecture_target"
    )
    changed = replace(declaration, title="Invented") if change == "title" else declaration
    if change in ("owners", "target"):
        field = "owner_ids" if change == "owners" else "target"
        value = () if change == "owners" else None
        changed = replace(
            declaration,
            data=replace(
                declaration.data,
                entries=tuple(
                    (key, value if key == field else entry)
                    for key, entry in declaration.data.entries
                ),
            ),
        )
    sections = tuple(
        replace(
            section,
            records=(
                *tuple(
                    changed if record.id == declaration.id else record for record in section.records
                ),
                *((replace(declaration, id="invented"),) if change == "extra" else ()),
            ),
        )
        if section.name == "declarations"
        else section
        for section in model.sections
    )
    result = assemble_uml(
        replace(assembled, observation=replace(model, sections=sections)), root, config.contract
    )
    assert result.diagnostics


def test_core_rejects_a_conflicting_declaration_in_adapter_output(tmp_path: Path) -> None:
    root, config = _repository(tmp_path)
    original = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    assembled = assemble_uml(original, root, config.contract)
    model = assembled.observation
    assert model is not None
    sections = tuple(
        replace(
            section,
            records=tuple(
                replace(record, title="Tampered") if record.kind == "uml_target" else record
                for record in section.records
            ),
        )
        for section in model.sections
    )
    forged = replace(assembled, observation=replace(model, sections=sections))
    result = assemble_uml(forged, root, config.contract)
    assert result.diagnostics
    assert "conflicts" in result.diagnostics[0].unknown_claim

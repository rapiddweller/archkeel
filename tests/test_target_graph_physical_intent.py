# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Physical modules and component intent preserve declared identity and scope."""

import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from test_target_graph import (
    _contract,
    _physical_contract,
    _repository,
)

from archkeel.check.report import run_report
from archkeel.check.uml import assemble_uml
from archkeel.cli.observe import observe
from archkeel.ir.architecture_graph import (
    ArchitectureGraph,
    ComponentIntent,
    ComponentRole,
    Entity,
)
from archkeel.ir.codec import (
    decode_canonical_model,
    parse_contract,
    parse_observation,
)
from archkeel.ir.graph_codec import graph_bytes, parse_graph
from archkeel.ir.model import Evidence
from archkeel.ir.target_graph import declared_graph
from archkeel.ir.target_records import recorded_target_graph
from tools.architecture_graph_schema import graph_schema


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

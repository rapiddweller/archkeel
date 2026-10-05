# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Independent UML intent must use the shared types and survive contract round trips."""

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
from archkeel.cli.observe import observe
from archkeel.ir.architecture_graph import (
    ArchitectureGraph,
    ComponentIntent,
    ComponentRole,
    Entity,
    Signature,
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
from archkeel.ir.graph_codec import graph_bytes, parse_graph, parse_target
from archkeel.ir.model import Evidence
from archkeel.ir.target_graph import declared_graph, declared_tree_graph
from archkeel.ir.target_records import recorded_target_graph
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


def test_existing_contract_bytes_and_digest_do_not_change() -> None:
    root = Path(__file__).parents[1]
    for path in (root / "tests/contracts/valid").glob("*.json"):
        contract = parse_contract(json.loads(path.read_bytes()))
        assert contract.schema_version == "2.1.0"
        assert parse_contract(json.loads(contract_bytes(contract))) == contract
        assert "uml" not in json.loads(contract_bytes(contract)).get("declarations", {})


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

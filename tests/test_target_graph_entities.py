# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Target entity grammar preserves classifiers, signatures and lexical identity."""

import json
from dataclasses import asdict
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from test_target_graph import (
    _contract,
)

from archkeel.ir.architecture_graph import (
    ArchitectureGraph,
)
from archkeel.ir.codec import (
    contract_bytes,
    parse_contract,
)
from archkeel.ir.graph_codec import parse_graph
from archkeel.ir.target_graph import declared_graph
from archkeel.ir.widening import contract_widenings
from tools.architecture_graph_schema import graph_schema, target_schema


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

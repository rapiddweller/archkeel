# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Assignment sites are static bindings, never live object identities."""

import json
from dataclasses import replace

import pytest
from jsonschema import Draft202012Validator
from test_conditional_definitions import _facts
from test_file_evidence import _ir_schema_errors
from test_uml_classifier_facts import _observation

from archkeel.check.uml_compare import compare_graphs
from archkeel.ir.architecture_graph import ArchitectureGraph, Entity, Relationship
from archkeel.ir.bindings import unread_bindings
from archkeel.ir.codec import canonical_report_bytes, decode_canonical_model
from archkeel.ir.graph_codec import graph_bytes, parse_graph
from archkeel.ir.model import RecordData
from archkeel.ir.source_graph import observed_graph
from tools.architecture_graph_schema import graph_schema


def test_plain_constructor_retains_binding_call_creation_and_instance_evidence(tmp_path):
    observation = _observation(
        tmp_path, "class Service: pass\ndef build():\n value: Service = Service()\n return value\n"
    )
    graph = observed_graph(observation)
    [value] = [item for item in graph.entities if item.qualified_name == "sample.app.build.value"]
    service = next(item for item in graph.entities if item.qualified_name == "sample.app.Service")
    build = next(item for item in graph.entities if item.qualified_name == "sample.app.build")
    assert value.kind == "binding" and value.parent_id == build.id
    assert value.annotation == "Service" and value.initializer == "Service()"
    assert value.visibility.kind == "unknown"
    assert any(
        edge.kind == "references" and edge.target_id == service.id for edge in graph.relationships
    )
    sites = {
        edge.kind: edge for edge in graph.relationships if edge.kind not in {"owns", "references"}
    }
    assert set(sites) == {"calls", "creates", "instance_of"}
    assert sites["creates"].source_id == build.id
    assert sites["instance_of"].source_id == value.id
    assert all(
        edge.target_id == service.id and edge.resolution == "resolved" for edge in sites.values()
    )
    assert (
        sites["calls"].record_ids == sites["creates"].record_ids == sites["instance_of"].record_ids
    )
    assert value.record_ids == sites["calls"].record_ids and value.evidence_ids
    assert parse_graph(json.loads(graph_bytes(graph))) == graph
    Draft202012Validator(graph_schema()).validate(json.loads(graph_bytes(graph)))


def test_chained_assignment_has_two_bindings_and_one_creation_site(tmp_path):
    graph = observed_graph(
        _observation(tmp_path, "class Service: pass\ndef build():\n a = b = Service()\n")
    )
    bindings = [item for item in graph.entities if item.initializer is not None]
    assert {item.qualified_name for item in bindings} == {
        "sample.app.build.a",
        "sample.app.build.b",
    }
    assert len({item.id for item in bindings}) == 2
    assert len([edge for edge in graph.relationships if edge.kind == "creates"]) == 1
    assert len([edge for edge in graph.relationships if edge.kind == "instance_of"]) == 2
    assert bindings[0].record_ids == bindings[1].record_ids


@pytest.mark.parametrize(
    "source",
    [
        "class Service:\n def __new__(cls): return 1\nvalue = Service()\n",
        "class Service:\n def __init__(self): self.__class__ = Other\nvalue = Service()\n",
        "class Base: pass\nclass Service(Base): pass\nvalue = Service()\n",
        "class Service(metaclass=Meta): pass\nvalue = Service()\n",
        "@decorate\nclass Service: pass\nvalue = Service()\n",
        "if flag:\n class Service: pass\nvalue = Service()\n",
        "class Service: pass\nService = factory\nvalue = Service()\n",
        "class Service: pass\nService.__new__ = factory\nvalue = Service()\n",
        "class Service:\n exec('def __new__(cls): return 1')\nvalue = Service()\n",
        "class Service:\n locals()['__new__'] = factory\nvalue = Service()\n",
    ],
)
def test_unproven_constructor_results_never_confirm_an_instance(tmp_path, source):
    graph = observed_graph(_observation(tmp_path, source))
    [value] = [item for item in graph.entities if item.initializer == "Service()"]
    instance_edges = [edge for edge in graph.relationships if edge.kind == "instance_of"]
    assert instance_edges and all(edge.source_id == value.id for edge in instance_edges)
    assert all(edge.target_id is None and edge.resolution == "partial" for edge in instance_edges)
    assert all(edge.candidate_ids and edge.reason for edge in instance_edges)


@pytest.mark.parametrize(
    "body",
    [
        "def build(Service):\n value = Service()\n",
        "def build():\n Service = factory\n value = Service()\n",
        "def build():\n from other import Service\n value = Service()\n",
        "def outer(Service):\n def build():\n  value = Service()\n",
        "def build():\n global Service\n value = Service()\n",
    ],
)
def test_shadowed_constructor_name_cannot_borrow_the_module_class(tmp_path, body):
    graph = observed_graph(_observation(tmp_path, "class Service: pass\n" + body))
    assert any(item.initializer == "Service()" for item in graph.entities)
    assert not any(edge.kind in {"creates", "instance_of"} for edge in graph.relationships)


def test_imported_plain_constructor_and_factory_results_stay_distinct(tmp_path):
    graph = observed_graph(
        _observation(
            tmp_path,
            "from sample.base import Service\ndef factory(): return Service()\n"
            "def build():\n direct = Service()\n indirect = factory()\n",
            {"base.py": "class Service: pass\n"},
        )
    )
    direct = next(
        item for item in graph.entities if item.qualified_name == "sample.app.build.direct"
    )
    indirect = next(
        item for item in graph.entities if item.qualified_name == "sample.app.build.indirect"
    )
    assert any(
        edge.kind == "instance_of" and edge.source_id == direct.id and edge.resolution == "resolved"
        for edge in graph.relationships
    )
    assert not any(
        edge.kind == "instance_of" and edge.source_id == indirect.id for edge in graph.relationships
    )


@pytest.mark.parametrize("mutation", ["", "base.Service.__new__ = lambda cls: 1\n"])
def test_a_qualified_class_call_cannot_hide_a_replaced_constructor(tmp_path, mutation):
    graph = observed_graph(
        _observation(
            tmp_path,
            "import sample.base as base\n" + mutation + "def build():\n value = base.Service()\n",
            {"base.py": "class Service: pass\n"},
        )
    )
    [instance] = [edge for edge in graph.relationships if edge.kind == "instance_of"]
    assert instance.resolution == "partial" and instance.target_id is None
    assert instance.candidate_ids


def test_attribute_storage_and_unpacking_do_not_prove_result_types(tmp_path):
    graph = observed_graph(
        _observation(
            tmp_path,
            "class Service: pass\ndef build(self):\n self.value = Service()\n a, b = Service()\n",
        )
    )
    value = next(item for item in graph.entities if item.initializer == "Service()")
    [edge] = [edge for edge in graph.relationships if edge.kind == "instance_of"]
    assert edge.source_id == value.id and edge.resolution == "partial" and edge.target_id is None
    assert not any(item.qualified_name.endswith((".a", ".b")) for item in graph.entities)


def test_repeated_function_sites_do_not_merge_their_bindings(tmp_path):
    graph = observed_graph(
        _observation(
            tmp_path,
            "class Service: pass\n"
            "def build():\n value = Service()\n"
            "def build():\n value = Service()\n",
        )
    )
    bindings = [item for item in graph.entities if item.initializer]
    functions = [item for item in graph.entities if item.qualified_name == "sample.app.build"]
    assert len(bindings) == len(functions) == 2
    assert {item.parent_id for item in bindings} == {item.id for item in functions}


def test_nested_argument_is_not_the_assigned_value(tmp_path):
    graph = observed_graph(
        _observation(
            tmp_path,
            "class Service: pass\n"
            "def factory(value): pass\ndef build():\n value = factory(Service())\n",
        )
    )
    [binding] = [item for item in graph.entities if item.initializer]
    assert binding.initializer == "factory(Service())"
    assert not any(edge.kind == "instance_of" for edge in graph.relationships)
    assert len([edge for edge in graph.relationships if edge.kind == "creates"]) == 1


def test_static_binding_facts_do_not_expand_the_unread_binding_claim(tmp_path):
    observation = _observation(tmp_path, "class Service: pass\ndef build():\n value = Service()\n")
    assert [(item.owner, item.name) for item in unread_bindings(observation).candidates] == [
        ("sample.app.build", "value")
    ]
    assert all(item.kind.startswith("unused_") for item in observation.records("bindings"))


def test_old_calls_do_not_certify_binding_or_instance_inventory(tmp_path):
    observation = _observation(tmp_path, "class Service: pass\nvalue = Service()\n")
    sections = tuple(
        replace(
            section,
            records=tuple(
                replace(
                    item,
                    data=replace(
                        item.data,
                        entries=tuple(
                            (key, value)
                            for key, value in item.data.entries
                            if key not in {"result_bindings", "construction"}
                        ),
                    ),
                )
                for item in section.records
            ),
        )
        if section.name == "calls"
        else section
        for section in observation.sections
    )
    graph = observed_graph(replace(observation, sections=sections))
    assert not any(item.initializer is not None for item in graph.entities)
    assert not any(edge.kind in {"creates", "instance_of"} for edge in graph.relationships)
    assert all(
        item.status == "unavailable"
        for item in graph.coverage
        if item.entity_kinds == ("binding",)
        or item.relationship_kinds == ("creates", "instance_of")
    )


def test_target_binding_and_instance_intent_is_independent_and_core_owned(tmp_path):
    observed = observed_graph(_observation(tmp_path, "class Service: pass\nvalue = Service()\n"))
    provenance = ("target.md",)
    target = ArchitectureGraph(
        "declared",
        (
            Entity("service", "class", "sample.app.Service", "python", provenance=provenance),
            Entity(
                "value",
                "binding",
                "sample.app.value",
                "python",
                initializer="Service()",
                provenance=provenance,
            ),
        ),
        (Relationship("value-type", "instance_of", "value", "service", provenance=provenance),),
    )
    assert compare_graphs(observed, target).status == "PASS"
    wrong = replace(
        target, entities=(target.entities[0], replace(target.entities[1], initializer="Other()"))
    )
    assert any(
        item.status == "FAIL" and item.aspect == "initializer"
        for item in compare_graphs(observed, wrong).assessments
    )
    old = replace(
        observed, entities=tuple(replace(item, initializer=None) for item in observed.entities)
    )
    assert any(
        item.status == "UNKNOWN" and item.aspect == "initializer"
        for item in compare_graphs(old, target).assessments
    )


def test_initializer_is_only_valid_for_a_binding():
    with pytest.raises(ValueError, match="initializer"):
        ArchitectureGraph(
            "declared",
            (
                Entity(
                    "class",
                    "class",
                    "sample.Service",
                    "python",
                    initializer="Service()",
                    provenance=("target.md",),
                ),
            ),
        ).validate()


def test_call_collector_publishes_result_sites_without_policy():
    _, calls, evidence = _facts("class Service: pass\ndef build():\n value = Service()\n")
    [call] = calls
    [binding] = call["data"]["result_bindings"]
    assert binding["name"] == "value" and binding["target_kind"] == "name"
    assert binding["evidence_ids"] and set(binding["evidence_ids"]) <= evidence.keys()
    assert call["data"]["construction"]["status"] == "resolved"


@pytest.mark.parametrize(
    "field,value",
    [
        ("initializer", 3),
        ("target_kind", "unpack"),
        ("evidence_ids", []),
        ("definition_contexts", [{"kind": 3, "branch": "body", "evidence_ids": ["site"]}]),
        ("invented", True),
    ],
)
def test_published_source_schema_checks_assignment_metadata(tmp_path, field, value):
    observation = _observation(tmp_path, "class Service: pass\nif flag:\n value = Service()\n")
    wire = decode_canonical_model(json.loads(canonical_report_bytes(observation)))
    assert _ir_schema_errors(wire) == []
    [call] = wire["calls"]
    call["data"]["result_bindings"][0][field] = value
    assert _ir_schema_errors(wire)


@pytest.mark.parametrize(
    "field,value",
    [("status", "unknown"), ("targets", []), ("candidates_truncated", 1), ("invented", True)],
)
def test_published_source_schema_checks_construction_metadata(tmp_path, field, value):
    observation = _observation(tmp_path, "class Service: pass\nvalue = Service()\n")
    wire = decode_canonical_model(json.loads(canonical_report_bytes(observation)))
    assert _ir_schema_errors(wire) == []
    [call] = wire["calls"]
    call["data"]["construction"][field] = value
    assert _ir_schema_errors(wire)


@pytest.mark.parametrize("name", ["Value", "dict"])
def test_namespace_binding_and_assignment_site_share_one_identity(tmp_path, name):
    graph = observed_graph(_observation(tmp_path, f"class Service: pass\n{name} = Service()\n"))
    [binding] = [item for item in graph.entities if item.qualified_name == f"sample.app.{name}"]
    assert binding.kind == "binding" and binding.initializer == "Service()"
    assert len(binding.record_ids) == 2
    assert any(
        edge.kind == "instance_of" and edge.source_id == binding.id for edge in graph.relationships
    )


def _result_binding_with_prior_symbol(
    tmp_path,
    *,
    target_kind="name",
    name="value",
    prior_fields=(),
    site_fields=(),
):
    observation = _observation(tmp_path, "class Service: pass\nvalue = Service()\n")
    call = next(
        record for record in observation.records("calls") if record.data.get("result_bindings")
    )
    [site] = call.data.get("result_bindings")
    site_entries = dict(site.entries)
    site_entries.update(dict(site_fields))
    site_entries.update({"target_kind": target_kind, "name": name})
    evidence_ids = site_entries["evidence_ids"]

    def valid_contexts(contexts):
        return tuple(
            replace(
                context,
                entries=tuple(
                    (key, evidence_ids if key == "evidence_ids" else value)
                    for key, value in context.entries
                ),
            )
            for context in contexts
        )

    site_entries["definition_contexts"] = valid_contexts(site_entries["definition_contexts"])
    changed_site = replace(site, entries=tuple(sorted(site_entries.items())))
    changed_call = replace(
        call,
        data=RecordData(
            tuple(
                (key, (changed_site,) if key == "result_bindings" else value)
                for key, value in call.data.entries
            )
        ),
    )
    module = next(
        record
        for record in observation.records("modules")
        if record.id == call.data.get("source_definition_id")
    )
    service = next(
        record
        for record in observation.records("symbols")
        if record.data.get("qualified_name") == "sample.app.Service"
    )
    prior_data = {
        "qualified_name": f"{module.data.get('qualified_name')}.{name}",
        "module": module.data.get("qualified_name"),
        "source_file": "app.py",
        "name": name,
        "lexical_parent_id": call.data.get("source_definition_id"),
        "symbol_category": "dynamic_binding",
    }
    prior_data.update(dict(prior_fields))
    if "definition_contexts" in prior_data:
        prior_data["definition_contexts"] = valid_contexts(prior_data["definition_contexts"])
    prior = replace(
        service,
        id=site_entries["id"],
        kind="binding",
        data=RecordData(tuple(sorted(prior_data.items()))),
    )
    sections = tuple(
        replace(
            section,
            records=(
                tuple(
                    changed_call if record.id == call.id else record for record in section.records
                )
                if section.name == "calls"
                else section.records + (prior,)
            ),
        )
        if section.name in {"calls", "symbols"}
        else section
        for section in observation.sections
    )
    return replace(observation, sections=sections), site_entries


@pytest.mark.parametrize(
    "prior_fields,site_fields",
    [
        ({}, {"annotation": "Service"}),
        ({"annotation": "Prior"}, {"annotation": None}),
    ],
)
def test_result_binding_enriches_missing_metadata_and_preserves_known_metadata(
    tmp_path, prior_fields, site_fields
):
    prior_fields = dict(prior_fields)
    site_fields = dict(site_fields)
    prior_context = RecordData((("kind", "try"), ("branch", "body"), ("evidence_ids", ("source",))))
    site_context = RecordData((("kind", "if"), ("branch", "body"), ("evidence_ids", ("site",))))
    if prior_fields:
        prior_fields["definition_contexts"] = (prior_context,)
        site_fields["definition_contexts"] = ()
        expected_context = (prior_context,)
    else:
        site_fields["definition_contexts"] = (site_context,)
        expected_context = (site_context,)
    observation, site = _result_binding_with_prior_symbol(
        tmp_path,
        prior_fields=prior_fields.items(),
        site_fields=site_fields.items(),
    )

    [binding] = [item for item in observed_graph(observation).entities if item.id == site["id"]]
    assert binding.annotation == prior_fields.get("annotation", site_fields.get("annotation"))
    assert tuple((item.kind, item.branch) for item in binding.definition_contexts) == tuple(
        (item.get("kind"), item.get("branch")) for item in expected_context
    )


@pytest.mark.parametrize(
    "prior_fields,site_fields",
    [
        ({"lexical_parent_id": "wrong-parent"}, {}),
        ({"qualified_name": "sample.app.other"}, {}),
        ({"qualified_name": "other.value"}, {}),
        ({"symbol_category": "class"}, {}),
        ({"initializer": "Service()"}, {}),
        ({"annotation": "Other"}, {"annotation": "Service"}),
        (
            {
                "definition_contexts": (
                    RecordData((("kind", "if"), ("branch", "body"), ("evidence_ids", ("source",)))),
                )
            },
            {
                "definition_contexts": (
                    RecordData(
                        (("kind", "while"), ("branch", "body"), ("evidence_ids", ("site",)))
                    ),
                )
            },
        ),
    ],
)
def test_result_binding_rejects_conflicting_prior_identity_and_metadata(
    tmp_path, prior_fields, site_fields
):
    observation, _ = _result_binding_with_prior_symbol(
        tmp_path,
        prior_fields=prior_fields.items(),
        site_fields=site_fields.items(),
    )
    with pytest.raises(ValueError, match="static result binding identity conflicts"):
        observed_graph(observation)


@pytest.mark.parametrize(
    "target_kind,name",
    [("attribute", "self.value"), ("subscript", "items[0]")],
)
def test_result_binding_keeps_expression_qualified_name_for_non_name_targets(
    tmp_path, target_kind, name
):
    observation, site = _result_binding_with_prior_symbol(
        tmp_path, target_kind=target_kind, name=name
    )
    [binding] = [item for item in observed_graph(observation).entities if item.id == site["id"]]
    assert binding.qualified_name == f"sample.app.{name}"


def test_initializer_codec_rejects_non_text_and_empty_values():
    target = ArchitectureGraph(
        "declared",
        (
            Entity(
                "binding",
                "binding",
                "sample.value",
                "python",
                initializer="Service()",
                provenance=("target.md",),
            ),
        ),
    )
    for bad in (False, 3, {}, ""):
        wire = json.loads(graph_bytes(target))
        wire["entities"][0]["initializer"] = bad
        with pytest.raises(ValueError):
            parse_graph(wire)


def test_lambdas_comprehensions_and_declaration_defaults_add_no_false_creation(tmp_path):
    graph = observed_graph(
        _observation(
            tmp_path,
            "class Service: pass\n"
            "def build(value=Service()):\n callback = lambda Service: Service()\n"
            " values = [Service() for Service in factories]\n",
        )
    )
    assert not any(edge.kind in {"creates", "instance_of"} for edge in graph.relationships)


def test_conditional_assignment_retains_context_and_target_availability_unknown(tmp_path):
    observed = observed_graph(
        _observation(tmp_path, "class Service: pass\nif flag:\n value = Service()\n")
    )
    [binding] = [item for item in observed.entities if item.initializer]
    assert [(item.kind, item.branch) for item in binding.definition_contexts] == [("if", "body")]
    target = ArchitectureGraph(
        "declared",
        (
            Entity(
                "value",
                "binding",
                "sample.app.value",
                "python",
                initializer="Service()",
                provenance=("target.md",),
            ),
        ),
    )
    assert compare_graphs(observed, target).status == "UNKNOWN"


@pytest.mark.parametrize(
    "bad", ["missing_evidence", "foreign_target", "resolved_partial_call", "invented_field"]
)
def test_malformed_call_result_facts_are_rejected(tmp_path, bad):
    observation = _observation(tmp_path, "class Service: pass\nvalue = Service()\n")
    [call] = observation.records("calls")
    changed = []
    for key, value in call.data.entries:
        if bad == "missing_evidence" and key == "result_bindings":
            [binding] = value
            value = (
                replace(
                    binding,
                    entries=tuple(
                        (name, () if name == "evidence_ids" else entry)
                        for name, entry in binding.entries
                    ),
                ),
            )
        elif bad in {"foreign_target", "invented_field"} and key == "construction":
            entries = tuple(
                (
                    name,
                    ("other.Unknown",) if name == "targets" and bad == "foreign_target" else entry,
                )
                for name, entry in value.entries
            )
            value = replace(
                value,
                entries=entries + (("invented", True),) if bad == "invented_field" else entries,
            )
        elif bad == "resolved_partial_call" and key == "status":
            value = "partially_resolved"
        changed.append((key, value))
    altered = replace(call, data=RecordData(tuple(changed)))
    sections = tuple(
        replace(section, records=(altered,)) if section.name == "calls" else section
        for section in observation.sections
    )
    with pytest.raises(ValueError):
        observed_graph(replace(observation, sections=sections))

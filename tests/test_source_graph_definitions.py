# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Calls, references and members retain their exact lexical declaration ownership."""

from dataclasses import replace
from pathlib import Path

import pytest
from test_source_graph import _graph, _source_observation
from test_source_graph import observation as observation

from archkeel.ir.model import RecordData, Section


@pytest.mark.parametrize("operation", ["def", "async def"])
def test_operation_annotations_have_declaration_ownership_and_lexical_binding(
    tmp_path: Path, operation: str
) -> None:
    observation = _source_observation(
        tmp_path,
        "class Payload: pass\n"
        "class Service:\n"
        " class Payload: pass\n"
        f" {operation} run(self, value: Payload) -> Payload: return value\n",
    )
    references = observation.records("references")
    annotations = [item for item in references if item.data.get("expression") == "Payload"]
    assert len(annotations) == 2
    operation_record = next(
        item
        for item in observation.records("symbols")
        if item.data.get("qualified_name") == "sample.app.Service.run"
    )
    for item in annotations:
        assert item.data.get("source_scope") == "sample.app.Service"
        assert item.data.get("declaration_scope") == "sample.app.Service.run"
        assert item.data.get("declaration_definition_id") == operation_record.id
    graph = _graph(observation)
    edges = [edge for edge in graph.relationships if edge.id in {item.id for item in annotations}]
    assert len(edges) == 2
    assert {edge.source_id for edge in edges} == {operation_record.id}
    # A class binding shadows the module type while evaluating the header.
    assert all(
        graph_entity.qualified_name == "sample.app.Service.Payload"
        for edge in edges
        for graph_entity in graph.entities
        if graph_entity.id == edge.target_id
    )


def test_header_defaults_keep_evaluation_ownership(tmp_path: Path) -> None:
    observation = _source_observation(
        tmp_path,
        "class Payload: pass\ndef work(value: Payload = Payload) -> Payload: return Payload\n",
    )
    references = observation.records("references")
    headers = [item for item in references if item.data.get("source_scope") == "sample.app"]
    assert len(headers) == 3
    assert sum(item.data.get("declaration_scope") == "sample.app.work" for item in headers) == 2
    default = next(item for item in headers if item.data.get("declaration_scope") is None)
    graph = _graph(observation)
    entity_names = {entity.id: entity.qualified_name for entity in graph.entities}
    assert (
        entity_names[next(edge.source_id for edge in graph.relationships if edge.id == default.id)]
        == "sample.app"
    )


def test_unresolved_construction_remains_an_unresolved_typed_site(observation) -> None:
    calls = observation.records("calls") or ()
    call = calls[0]
    unresolved = replace(
        call,
        data=RecordData(
            tuple((key, value) for key, value in call.data.entries if key != "construction")
            + (
                (
                    "construction",
                    RecordData(
                        (
                            ("status", "unresolved"),
                            ("targets", ()),
                            ("candidates_truncated", False),
                            ("reason", "constructor is outside the recorded source graph"),
                        )
                    ),
                ),
            )
        ),
    )
    changed = replace(
        observation,
        sections=tuple(
            Section(section.name, (unresolved, *calls[1:])) if section.name == "calls" else section
            for section in observation.sections
        ),
    )

    constructions = [
        edge
        for edge in _graph(changed).relationships
        if edge.kind == "creates" and call.id in edge.record_ids
    ]
    assert len(constructions) == 1
    assert constructions[0].resolution == "unresolved"
    assert constructions[0].target_id is None
    assert constructions[0].reason == "constructor is outside the recorded source graph"


@pytest.mark.parametrize(
    "details",
    [
        {"declaration_scope": "sample.app.work"},
        {"declaration_scope": "sample.app.work", "declaration_definition_id": "missing"},
        {"declaration_scope": "sample.app.work", "declaration_definition_id": False},
        {"declaration_scope": False, "declaration_definition_id": "missing"},
    ],
)
def test_malformed_reference_declaration_is_rejected(tmp_path: Path, details) -> None:
    observation = _source_observation(tmp_path, "class Payload: pass\ndef work(): return Payload\n")
    references = tuple(
        replace(item, data=RecordData(tuple({**dict(item.data.entries), **details}.items())))
        for item in observation.records("references")
    )
    malformed = replace(
        observation,
        sections=tuple(
            Section(section.name, references) if section.name == "references" else section
            for section in observation.sections
        ),
    )
    with pytest.raises(ValueError, match="reference declaration|expected text"):
        _graph(malformed)


def test_repeated_operation_headers_keep_definition_site_ownership(tmp_path: Path) -> None:
    observation = _source_observation(
        tmp_path,
        "class Payload: pass\n"
        "class Service:\n"
        " def run(self, value: Payload) -> Payload: return value\n"
        " def run(self, value: Payload) -> Payload: return value\n",
    )
    graph = _graph(observation)
    methods = [
        entity for entity in graph.entities if entity.qualified_name == "sample.app.Service.run"
    ]
    annotations = [edge for edge in graph.relationships if edge.kind == "references"]
    assert len(methods) == 2
    assert len(annotations) == 4
    assert {edge.source_id for edge in annotations} == {entity.id for entity in methods}


def test_legacy_reference_without_declaration_keeps_lexical_ownership(tmp_path: Path) -> None:
    observation = _source_observation(
        tmp_path, "class Payload: pass\ndef work(value: Payload) -> Payload: return value\n"
    )
    references = tuple(
        replace(
            item,
            data=RecordData(
                tuple(
                    (key, value)
                    for key, value in item.data.entries
                    if key not in {"declaration_scope", "declaration_definition_id"}
                )
            ),
        )
        for item in observation.records("references")
    )
    legacy = replace(
        observation,
        sections=tuple(
            Section(section.name, references) if section.name == "references" else section
            for section in observation.sections
        ),
    )
    graph = _graph(legacy)
    module = next(entity for entity in graph.entities if entity.qualified_name == "sample.app")
    assert {edge.source_id for edge in graph.relationships if edge.kind == "references"} == {
        module.id
    }


def test_redefined_functions_keep_their_own_call_and_reference_sources(tmp_path: Path) -> None:
    observation = _source_observation(
        tmp_path,
        "def helper(): pass\n"
        "def work():\n helper()\n return helper\n"
        "def work():\n helper()\n return helper\n",
    )
    graph = _graph(observation)
    work = [entity for entity in graph.entities if entity.qualified_name == "sample.app.work"]
    assert len(work) == 2
    sources = {edge.source_id for edge in graph.relationships if edge.kind == "calls"}
    assert sources == {entity.id for entity in work}
    assert {edge.source_id for edge in graph.relationships if edge.kind == "references"} == sources
    evidence = {item.id: item for item in graph.evidence}
    for edge in graph.relationships:
        if edge.kind in {"calls", "references"}:
            owner = next(entity for entity in work if entity.id == edge.source_id)
            definition = evidence[owner.evidence_ids[0]]
            site = evidence[edge.evidence_ids[0]]
            assert definition.line <= site.line <= definition.end_line


def test_redefined_classes_do_not_steal_each_others_methods(tmp_path: Path) -> None:
    graph = _graph(
        _source_observation(
            tmp_path, "class Service:\n def run(self): pass\nclass Service:\n def run(self): pass\n"
        )
    )
    owners = {item.id: item for item in graph.entities if item.kind == "class"}
    methods = [item for item in graph.entities if item.kind == "method"]
    assert len(owners) == len(methods) == 2
    assert {method.parent_id for method in methods} == set(owners)
    evidence = {item.id: item for item in graph.evidence}
    for method in methods:
        owner = owners[method.parent_id]
        assert evidence[owner.evidence_ids[0]].line + 1 == evidence[method.evidence_ids[0]].line


def test_protocol_implementation_is_not_rendered_as_an_interface(tmp_path: Path) -> None:
    graph = _graph(
        _source_observation(
            tmp_path,
            "from typing import Protocol\n"
            "class Port(Protocol): pass\n"
            "class Client(Port): pass\n"
            "class Extended(Port, Protocol): pass\n"
            "class Port: pass\n",
        )
    )
    by_name: dict[str, set[str]] = {}
    for entity in graph.entities:
        by_name.setdefault(entity.qualified_name, set()).add(entity.kind)
    assert by_name["sample.app.Port"] == {"interface", "class"}
    assert by_name["sample.app.Client"] == {"class"}
    assert by_name["sample.app.Extended"] == {"interface"}


def test_nested_functions_and_local_classes_keep_their_lexical_parents(tmp_path: Path) -> None:
    graph = _graph(
        _source_observation(
            tmp_path,
            "def outer():\n"
            " def inner(): return str(1)\n"
            " class Local:\n"
            "  def run(self):\n"
            "   def callback(): return int('1')\n"
            "   return callback()\n"
            " return inner\n",
        )
    )
    by_name = {entity.qualified_name: entity for entity in graph.entities}
    for child, parent, kind in (
        ("outer.inner", "outer", "function"),
        ("outer.Local", "outer", "class"),
        ("outer.Local.run", "outer.Local", "method"),
        ("outer.Local.run.callback", "outer.Local.run", "function"),
    ):
        entity = by_name[f"sample.app.{child}"]
        assert entity.kind == kind
        assert entity.parent_id == by_name[f"sample.app.{parent}"].id
    calls = [edge for edge in graph.relationships if edge.kind == "calls"]
    assert {edge.source_id for edge in calls if edge.expression in {"str", "int"}} == {
        by_name[f"sample.app.{name}"].id for name in ("outer.inner", "outer.Local.run.callback")
    }


def test_repeated_attribute_annotations_keep_each_site_and_its_evidence(tmp_path: Path) -> None:
    graph = _graph(_source_observation(tmp_path, "class Service:\n value: int\n value: str\n"))
    attributes = [entity for entity in graph.entities if entity.kind == "attribute"]
    assert len(attributes) == 2
    assert len({entity.id for entity in attributes}) == 2
    assert {entity.annotation for entity in attributes} == {"int", "str"}
    evidence = {item.id: item for item in graph.evidence}
    assert {evidence[entity.evidence_ids[0]].line for entity in attributes} == {2, 3}


def test_overload_candidates_are_not_a_confirmed_definition(tmp_path: Path) -> None:
    graph = _graph(
        _source_observation(
            tmp_path,
            "from typing import overload\n"
            "@overload\ndef parse(value: int) -> int: ...\n"
            "@overload\ndef parse(value: str) -> str: ...\n"
            "def parse(value): return value\n"
            "def work(): return parse(1)\n",
        )
    )
    definitions = {
        entity.id for entity in graph.entities if entity.qualified_name == "sample.app.parse"
    }
    call = next(edge for edge in graph.relationships if edge.expression == "parse")
    assert len(definitions) == 3
    assert call.resolution == "partial"
    assert call.target_id is None
    assert set(call.candidate_ids) == definitions
    assert call.candidate_count == 3
    assert not call.candidates_truncated


def test_partial_call_without_listed_candidates_stays_partial(observation) -> None:
    calls = tuple(
        replace(
            item,
            data=RecordData(
                tuple(
                    (key, value)
                    for key, value in item.data.entries
                    if key not in {"status", "targets", "candidate_count", "candidates_truncated"}
                )
                + (
                    ("status", "partially_resolved"),
                    ("targets", ()),
                    ("candidate_count", 7),
                    ("candidates_truncated", True),
                )
            ),
        )
        if item.data.get("expression") == "value.unknown"
        else item
        for item in observation.records("calls")
    )
    partial = replace(
        observation,
        sections=tuple(
            Section(s.name, calls) if s.name == "calls" else s for s in observation.sections
        ),
    )
    edge = next(
        item for item in _graph(partial).relationships if item.expression == "value.unknown"
    )
    assert edge.resolution == "partial"
    assert edge.candidate_ids == ()
    assert edge.candidates_truncated
    # Omitted qualified names do not tell us how many definition sites they represent.
    assert edge.candidate_count is None


@pytest.mark.parametrize(
    "key, value",
    [
        ("candidate_count", -1),
        ("candidate_count", True),
        ("candidates_truncated", "yes"),
        ("source_definition_id", "unknown-definition"),
        ("status", "guess"),
    ],
)
def test_malformed_source_resolution_is_rejected(observation, key: str, value: object) -> None:
    calls = tuple(
        replace(item, data=RecordData(tuple({**dict(item.data.entries), key: value}.items())))
        for item in observation.records("calls")
    )
    malformed = replace(
        observation,
        sections=tuple(
            Section(s.name, calls) if s.name == "calls" else s for s in observation.sections
        ),
    )
    with pytest.raises(ValueError):
        _graph(malformed)


def test_lexical_child_does_not_become_a_runtime_function_attribute(tmp_path: Path) -> None:
    observation = _source_observation(
        tmp_path,
        "def outer():\n def inner(): pass\n return inner\ndef work(): return outer.inner()\n",
    )
    raw = next(
        item
        for item in observation.records("calls")
        if item.data.get("expression") == "outer.inner"
    )
    assert raw.data.get("status") != "resolved"
    graph = _graph(observation)
    edge = next(item for item in graph.relationships if item.expression == "outer.inner")
    assert edge.resolution != "resolved"
    assert edge.target_id is None
    from archkeel.ir.references import unreferenced_symbols

    assert "sample.app.outer.inner" not in {
        candidate.name for candidate in unreferenced_symbols(observation).candidates
    }


def test_conditional_caller_keeps_its_definition_site_and_context(
    tmp_path: Path,
) -> None:
    graph = _graph(
        _source_observation(
            tmp_path,
            "def work(): pass\nif condition:\n def work(): return str(1)\n",
        )
    )
    call = next(edge for edge in graph.relationships if edge.expression == "str")
    caller = next(entity for entity in graph.entities if entity.id == call.source_id)
    assert caller.qualified_name == "sample.app.work"
    assert caller.presence == "defined"
    assert caller.kind == "function"
    assert caller.definition_contexts


def test_field_binding_certainty_does_not_change_uml_static_modifiers(tmp_path: Path) -> None:
    graph = _graph(_source_observation(tmp_path, "class Dto:\n kind: str\n mode = 'test'\n"))
    by_name = {entity.qualified_name: entity for entity in graph.entities}
    assert by_name["sample.app.Dto.kind"].modifiers == ()
    assert by_name["sample.app.Dto.mode"].modifiers == ("static",)

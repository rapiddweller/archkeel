# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Project actual analyzer evidence into the shared semantic graph."""

from dataclasses import replace
from pathlib import Path

import pytest
from test_analyzer import _observe

from archkeel.ir.architecture_graph import ArchitectureGraph
from archkeel.ir.model import RecordData, Section
from archkeel.ir.profiles import DART_ANALYZER


@pytest.fixture
def observation(tmp_path: Path):
    package = tmp_path / "sample"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "service.py").write_text(
        "from typing import Protocol\n"
        "class Port(Protocol):\n def run(self, x: int) -> str: ...\n"
        "class Client:\n _token: str\n count: int = 1\n"
        " def __init__(self): pass\n"
        " async def run(self, value: int, /, *, limit=10) -> str: return helper()\n"
        "def helper() -> str: return 'ok'\n"
    )
    (package / "app.py").write_text(
        "from sample.service import helper, Client\n"
        "def work(value):\n callback = helper\n helper()\n value.unknown()\n return Client()\n"
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    assert result.observation.records("symbols")
    return result.observation


def _graph(observation) -> ArchitectureGraph:
    from archkeel.ir.source_graph import observed_graph

    graph = observed_graph(observation)
    graph.validate()
    return graph


@pytest.mark.parametrize("name,kind", [("Public", "public"), ("_Private", "private")])
def test_type_alias_visibility_retains_its_python_convention(tmp_path, name, kind):
    from test_member_inventory import _observation

    observation = _observation(tmp_path, f"from typing import TypeAlias\n{name}: TypeAlias = int\n")
    record = next(
        r
        for r in observation.records("symbols")
        if r.data.get("qualified_name") == f"sample.model.{name}"
    )
    entity = next(e for e in _graph(observation).entities if e.id == record.id)
    assert entity.kind == "type_alias"
    assert entity.visibility.kind == kind
    assert entity.visibility.basis == "convention"
    assert entity.visibility.spelling == name
    assert entity.evidence_ids == record.evidence_ids


def test_source_graph_keeps_classifiers_private_attributes_and_operations(observation) -> None:
    graph = _graph(observation)
    by_name = {entity.qualified_name: entity for entity in graph.entities}
    owner = by_name["sample.service.Client"]
    assert by_name["sample.service.Port"].kind == "interface"
    assert owner.kind == "class"
    assert by_name["sample.service.Client._token"].visibility.kind == "private"
    assert by_name["sample.service.Client.__init__"].visibility.kind == "public"
    operation = by_name["sample.service.Client.run"]
    assert operation.kind == "method"
    assert operation.parent_id == owner.id
    assert operation.modifiers == ("async",)
    assert operation.signature is not None
    assert [(p.name, p.kind, p.default) for p in operation.signature.parameters] == [
        ("self", "positional_only", None),
        ("value", "positional_only", None),
        ("limit", "keyword_only", "10"),
    ]
    assert operation.signature.returns == "str"
    raw_method = next(
        item
        for item in observation.records("symbols")
        if item.data.get("qualified_name") == operation.qualified_name
    )
    assert operation.id == raw_method.id
    assert operation.evidence_ids == raw_method.evidence_ids


def test_cross_module_calls_and_references_keep_each_site_and_kind(observation) -> None:
    graph = _graph(observation)
    entities = {entity.id: entity for entity in graph.entities}
    helper_sites = [
        edge
        for edge in graph.relationships
        if edge.target_id is not None
        and entities[edge.target_id].qualified_name == "sample.service.helper"
    ]
    assert {edge.kind for edge in helper_sites} == {"calls", "references"}
    assert any(
        entities[edge.source_id].qualified_name == "sample.app.work" for edge in helper_sites
    )
    expected = {
        record.id for section in ("calls", "references") for record in observation.records(section)
    }
    projected = {edge.id for edge in graph.relationships if edge.kind in {"calls", "references"}}
    assert projected == expected
    assert all(edge.evidence_ids for edge in helper_sites)


def test_unresolved_call_keeps_expression_source_and_evidence(observation) -> None:
    graph = _graph(observation)
    edge = next(item for item in graph.relationships if item.expression == "value.unknown")
    assert edge.kind == "calls"
    assert edge.resolution == "unresolved"
    assert edge.target_id is None
    assert edge.candidate_ids == ()
    assert edge.reason
    raw = next(item for item in observation.records("calls") if item.id == edge.id)
    assert edge.evidence_ids == raw.evidence_ids


def test_static_instances_never_claim_an_empty_complete_inventory(
    observation,
) -> None:
    graph = _graph(observation)
    coverage = [item for item in graph.coverage if "binding" in item.entity_kinds]
    assert coverage
    assert all(item.status in {"partial", "unavailable"} and item.reason for item in coverage)
    assert any(item.status == "partial" for item in coverage)


def test_legacy_signatures_keep_unknown_parameter_details(observation) -> None:
    symbols = tuple(
        replace(
            record,
            data=RecordData(
                tuple(
                    (
                        key,
                        tuple(
                            RecordData(
                                tuple(
                                    (name, value)
                                    for name, value in parameter.entries
                                    if name in {"name", "annotation"}
                                )
                            )
                            for parameter in parameters
                        ),
                    )
                    if key == "parameters"
                    else (key, parameters)
                    for key, parameters in record.data.entries
                )
            ),
        )
        for record in observation.records("symbols")
    )
    legacy = replace(
        observation,
        sections=tuple(
            Section(s.name, symbols) if s.name == "symbols" else s for s in observation.sections
        ),
    )
    operation = next(
        entity
        for entity in _graph(legacy).entities
        if entity.qualified_name == "sample.service.Client.run"
    )
    assert operation.signature is not None
    assert all(
        parameter.kind == "unknown" and not parameter.default_known
        for parameter in operation.signature.parameters
    )


def test_dart_inner_profile_keeps_missing_symbols_unknown_and_calls_partial(observation) -> None:
    dart = replace(
        observation,
        analyzer=replace(observation.analyzer, name=DART_ANALYZER),
        sections=tuple(
            s for s in observation.sections if s.name not in {"symbols", "calls", "references"}
        )
        + (Section("calls", ()),),
    )
    graph = _graph(dart)
    calls = [item for item in graph.coverage if "calls" in item.relationship_kinds]
    symbols = [item for item in graph.coverage if "class" in item.entity_kinds]
    assert calls and all(item.status == "partial" and item.reason for item in calls)
    assert symbols and all(item.status == "unavailable" and item.reason for item in symbols)


def test_typescript_recorded_calls_have_partial_coverage(observation) -> None:
    typescript = replace(
        observation,
        analyzer=replace(observation.analyzer, name="archkeel-typescript-imports"),
    )

    calls = [item for item in _graph(typescript).coverage if "calls" in item.relationship_kinds]

    assert calls and all(item.status == "partial" for item in calls)


def test_typescript_enum_member_receipt_can_prove_exact_literal_inventory(tmp_path: Path) -> None:
    observation = _source_observation(
        tmp_path,
        "from enum import Enum\nclass State(Enum):\n READY = 1\n STOPPED = 2\n",
    )
    state = next(
        item for item in observation.records("symbols") or () if item.data.get("name") == "State"
    )
    python_inventory = [
        item
        for item in _graph(observation).coverage
        if item.scope_id == state.id and "enum_literal" in item.entity_kinds
    ]
    inventories = state.data.get("member_inventories")
    assert isinstance(inventories, tuple)
    complete_inventory = tuple(
        RecordData(
            tuple(
                (
                    key,
                    "complete" if key == "status" else None if key == "reason" else value,
                )
                for key, value in item.entries
            )
        )
        if isinstance(item, RecordData) and item.get("kind") == "attribute"
        else item
        for item in inventories
    )
    complete_state = replace(
        state,
        data=RecordData(
            tuple(
                (key, complete_inventory if key == "member_inventories" else value)
                for key, value in state.data.entries
            )
        ),
    )
    complete_observation = replace(
        observation,
        sections=tuple(
            Section(
                section.name,
                tuple(
                    complete_state if record.id == state.id else record
                    for record in section.records
                ),
            )
            if section.name == "symbols"
            else section
            for section in observation.sections
        ),
    )
    typescript = replace(
        complete_observation,
        analyzer=replace(complete_observation.analyzer, name="archkeel-typescript-imports"),
    )

    inventory = [
        item
        for item in _graph(typescript).coverage
        if item.scope_id == state.id and "enum_literal" in item.entity_kinds
    ]

    assert python_inventory and all(item.status == "partial" for item in python_inventory)
    assert inventory and all(item.status == "complete" for item in inventory)


def test_incomplete_observation_does_not_claim_complete_graph_coverage(observation) -> None:
    partial = replace(observation, coverage=replace(observation.coverage, status="FAIL"))
    graph = _graph(partial)
    supported = [item for item in graph.coverage if "calls" in item.relationship_kinds]
    assert supported
    assert all(item.status == "partial" and item.reason for item in supported)


def test_legacy_symbol_and_reference_sections_do_not_certify_exhaustive_inventory(
    observation,
) -> None:
    graph = _graph(observation)
    limited = [
        item
        for item in graph.coverage
        if "class" in item.entity_kinds or "references" in item.relationship_kinds
    ]
    assert limited
    assert all(item.status == "partial" and item.reason for item in limited)


def test_packages_cite_the_module_evidence_they_aggregate(observation) -> None:
    graph = _graph(observation)
    assert all(
        item.evidence_ids and item.record_ids for item in graph.entities if item.kind == "package"
    )


def test_recorded_namespace_groups_do_not_become_false_lexical_parents(observation) -> None:
    graph = _graph(observation)
    by_id = {entity.id: entity for entity in graph.entities}
    for module in (entity for entity in graph.entities if entity.kind == "module"):
        record = next(item for item in observation.records("modules") if item.id == module.id)
        if module.parent_id is not None:
            expected = (
                module.qualified_name
                if str(record.data.get("file")).endswith("__init__.py")
                else module.qualified_name.rpartition(".")[0]
            )
            assert by_id[module.parent_id].qualified_name == expected
    groups = observation.records("packages")
    assert groups
    expected_membership = {(group.id, module) for group in groups for module in group.fact_ids}
    assert {
        (edge.source_id, edge.target_id) for edge in graph.relationships if edge.kind == "owns"
    } == expected_membership


def test_legacy_public_attributes_survive_without_claiming_private_attribute_coverage(
    observation,
) -> None:
    legacy = replace(
        observation,
        sections=tuple(
            Section(
                s.name,
                tuple(
                    replace(
                        record,
                        data=RecordData(
                            tuple(
                                (key, value)
                                for key, value in record.data.entries
                                if key not in {"attribute_declarations", "member_inventories"}
                            )
                        ),
                    )
                    for record in s.records
                ),
            )
            if s.name == "symbols"
            else s
            for s in observation.sections
        ),
    )
    graph = _graph(legacy)
    field = next(
        item for item in graph.entities if item.qualified_name == "sample.service.Client.count"
    )
    assert field.annotation == "int"
    assert field.visibility.kind == "unknown"
    assert all(
        item.status == "partial" for item in graph.coverage if "attribute" in item.entity_kinds
    )


def _source_observation(tmp_path: Path, source: str):
    package = tmp_path / "sample"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "app.py").write_text(source)
    result = _observe(tmp_path)
    assert result.observation is not None
    return result.observation


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

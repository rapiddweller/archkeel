# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Legacy and language-profile evidence retain explicit source-graph coverage limits."""

from dataclasses import replace
from pathlib import Path

from test_source_graph import _graph, _source_observation
from test_source_graph import observation as observation

from archkeel.ir.model import RecordData, Section
from archkeel.ir.profiles import DART_ANALYZER


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

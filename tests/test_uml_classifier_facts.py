# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Explicit classifier bases retain identity, direction and uncertainty."""

from dataclasses import replace
from pathlib import Path

import pytest
from test_analyzer import _observe

from archkeel.ir.architecture_graph import ArchitectureGraph, Entity, Relationship
from archkeel.ir.model import RecordData, Section
from archkeel.ir.source_graph import observed_graph


def _observation(tmp_path: Path, source: str, extra: dict[str, str] | None = None):
    package = tmp_path / "sample"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "app.py").write_text(source)
    for name, content in (extra or {}).items():
        (package / name).write_text(content)
    result = _observe(tmp_path)
    assert result.observation is not None
    return result.observation


def _bases(graph: ArchitectureGraph) -> list[Relationship]:
    return [edge for edge in graph.relationships if edge.kind in {"inherits", "realizes"}]


def test_explicit_bases_distinguish_generalization_and_protocol_realization(tmp_path: Path) -> None:
    observation = _observation(
        tmp_path,
        "from typing import Protocol\n"
        "class Port(Protocol): pass\n"
        "class Base: pass\n"
        "class Client(Base, Port): pass\n"
        "class Extended(Port, Protocol): pass\n",
    )
    graph = observed_graph(observation)
    entities = {entity.id: entity for entity in graph.entities}
    assert {
        (
            entities[edge.source_id].qualified_name,
            edge.kind,
            entities[edge.target_id].qualified_name,
        )
        for edge in _bases(graph)
        if edge.target_id is not None
    } == {
        ("sample.app.Port", "inherits", "typing.Protocol"),
        ("sample.app.Client", "inherits", "sample.app.Base"),
        ("sample.app.Client", "realizes", "sample.app.Port"),
        ("sample.app.Extended", "inherits", "sample.app.Port"),
        ("sample.app.Extended", "inherits", "typing.Protocol"),
    }
    assert all(edge.resolution == "resolved" for edge in _bases(graph))
    evidence = {item.id: item for item in graph.evidence}
    client_edges = [
        edge
        for edge in _bases(graph)
        if entities[edge.source_id].qualified_name.endswith(".Client")
    ]
    assert len({edge.id for edge in client_edges}) == 2
    assert len({evidence[edge.evidence_ids[0]].column for edge in client_edges}) == 2
    symbols = {item.id for item in observation.records("symbols")}
    assert all(set(edge.record_ids) <= symbols for edge in _bases(graph))


def test_imported_internal_classifier_keeps_its_definition_site(tmp_path: Path) -> None:
    observation = _observation(
        tmp_path,
        "from sample.base import Base as Parent\nclass Child(Parent): pass\n",
        {"base.py": "class Base: pass\n"},
    )
    graph = observed_graph(observation)
    by_name = {entity.qualified_name: entity for entity in graph.entities}
    [edge] = _bases(graph)
    assert edge.source_id == by_name["sample.app.Child"].id
    assert edge.target_id == by_name["sample.base.Base"].id
    assert edge.expression == "Parent"
    assert edge.resolution == "resolved"


def test_dynamic_base_retains_expression_without_a_fabricated_target(tmp_path: Path) -> None:
    graph = observed_graph(_observation(tmp_path, "class Child(never_execute()): pass\n"))
    [edge] = _bases(graph)
    assert edge.expression == "never_execute()"
    assert edge.target_id is None
    assert edge.candidate_ids == ()
    assert edge.resolution == "unresolved"
    assert edge.reason and edge.evidence_ids


@pytest.mark.parametrize(
    "source",
    [
        "class Base: pass\nBase = factory()\nclass Child(Base): pass\n",
        "from external import Base\nBase = factory()\nclass Child(Base): pass\n",
        "if condition:\n from external import Base\nclass Child(Base): pass\n",
        "class Base: pass\nclass Outer:\n Base = factory()\n class Child(Base): pass\n",
        "from external import library\nlibrary.Base = factory()\nclass Child(library.Base): pass\n",
        "class Outer:\n class Base: pass\n Base = factory()\nclass Child(Outer.Base): pass\n",
        "@replace_class\nclass Base: pass\nclass Child(Base): pass\n",
    ],
)
def test_unproven_base_binding_never_becomes_a_confirmed_edge(tmp_path: Path, source: str) -> None:
    graph = observed_graph(_observation(tmp_path, source))
    [edge] = _bases(graph)
    assert edge.target_id is None
    assert edge.resolution in {"partial", "unresolved"}
    assert edge.reason


@pytest.mark.parametrize(
    "imported, inherited", [(False, False), (True, False), (False, True), (True, True)]
)
def test_custom_metaclass_ancestry_never_confirms_classifier_identity(
    tmp_path: Path, imported: bool, inherited: bool
) -> None:
    from archkeel.check.uml_compare import compare_graphs

    source = (
        "class Meta(type):\n"
        " def __new__(cls, name, bases, namespace):\n"
        "  if name == 'Base': return int\n"
        "  return super().__new__(cls, name, bases, namespace)\n"
        + (
            "class Parent(metaclass=Meta): pass\nclass Base(Parent): pass\n"
            if inherited
            else "class Base(metaclass=Meta): pass\n"
        )
    )
    observation = _observation(
        tmp_path,
        ("from sample.core import Base\n" if imported else source) + "class Child(Base): pass\n",
        {"core.py": source} if imported else None,
    )
    graph = observed_graph(observation)
    base_name = "sample.core.Base" if imported else "sample.app.Base"
    base = next(
        item
        for item in observation.records("symbols")
        if item.data.get("qualified_name") == base_name
    )
    assert base.data.get("class_header_static") is inherited
    entities = {item.id: item for item in graph.entities}
    [edge] = [
        item
        for item in _bases(graph)
        if entities[item.source_id].qualified_name == "sample.app.Child"
    ]
    assert edge.target_id is None
    assert edge.resolution == "partial"
    assert edge.reason and edge.evidence_ids
    target = ArchitectureGraph(
        "declared",
        (
            Entity(
                "base",
                "class",
                base_name,
                "python",
                presence="planned",
                responsibilities=("Base",),
                provenance=("spec",),
            ),
            Entity(
                "child",
                "class",
                "sample.app.Child",
                "python",
                presence="planned",
                responsibilities=("Child",),
                provenance=("spec",),
            ),
        ),
        (Relationship("extends", "inherits", "child", "base", provenance=("spec",)),),
    )
    comparison = compare_graphs(graph, target)
    assert (
        next(item for item in comparison.assessments if item.subject_id == "extends").status
        == "UNKNOWN"
    )


@pytest.mark.parametrize(
    "source, count",
    [
        ("class Parent: pass\nclass Base(Parent): pass\nclass Child(Base): pass\n", 2),
        (
            "class Parent: pass\nclass Left(Parent): pass\n"
            "class Right(Parent): pass\nclass Child(Left, Right): pass\n",
            4,
        ),
    ],
)
def test_ordinary_local_classifier_ancestry_keeps_confirmed_identity(
    tmp_path: Path, source: str, count: int
) -> None:
    graph = observed_graph(_observation(tmp_path, source))
    assert len(_bases(graph)) == count
    assert all(
        edge.resolution == "resolved" and edge.target_id is not None for edge in _bases(graph)
    )


@pytest.mark.parametrize(
    "source, extra",
    [
        ("class Base(factory()): pass\nclass Child(Base): pass\n", None),
        (
            "class Parent: pass\nParent = factory()\n"
            "class Base(Parent): pass\nclass Child(Base): pass\n",
            None,
        ),
        (
            "from sample.core import Base\nclass Parent(Base): pass\nclass Child(Parent): pass\n",
            {"core.py": "from sample.app import Parent\nclass Base(Parent): pass\n"},
        ),
    ],
)
def test_uncertain_classifier_ancestry_cannot_confirm_descendants(
    tmp_path: Path, source: str, extra: dict[str, str] | None
) -> None:
    graph = observed_graph(_observation(tmp_path, source, extra))
    entities = {item.id: item for item in graph.entities}
    [edge] = [
        item
        for item in _bases(graph)
        if entities[item.source_id].qualified_name == "sample.app.Child"
    ]
    assert edge.target_id is None
    assert edge.resolution == "partial"
    assert edge.reason and edge.evidence_ids


def test_redefined_base_keeps_every_candidate_site(tmp_path: Path) -> None:
    graph = observed_graph(
        _observation(tmp_path, "class Base: pass\nclass Base: pass\nclass Child(Base): pass\n")
    )
    definitions = {item.id for item in graph.entities if item.qualified_name == "sample.app.Base"}
    [edge] = _bases(graph)
    assert len(definitions) == 2
    assert edge.target_id is None
    assert edge.resolution == "partial"
    assert set(edge.candidate_ids) == definitions
    assert edge.candidate_count == 2


def test_generic_base_keeps_expression_and_classifier_endpoint(tmp_path: Path) -> None:
    graph = observed_graph(
        _observation(tmp_path, "from external import Base\nclass Child(Base[int]): pass\n")
    )
    entities = {item.id: item for item in graph.entities}
    [edge] = _bases(graph)
    assert edge.expression == "Base[int]"
    assert edge.resolution == "partial"
    assert edge.target_id is None
    [candidate] = edge.candidate_ids
    assert entities[candidate].qualified_name == "external.Base"
    assert entities[candidate].presence == "referenced"
    assert edge.reason


def test_legacy_base_names_do_not_certify_typed_relationship_coverage(tmp_path: Path) -> None:
    observation = _observation(tmp_path, "class Base: pass\nclass Child(Base): pass\n")
    legacy = replace(
        observation,
        sections=tuple(
            Section(
                section.name,
                tuple(
                    replace(
                        record,
                        data=RecordData(
                            tuple(
                                (key, value)
                                for key, value in record.data.entries
                                if key != "base_declarations"
                            )
                        ),
                    )
                    for record in section.records
                ),
            )
            if section.name == "symbols"
            else section
            for section in observation.sections
        ),
    )
    graph = observed_graph(legacy)
    assert not _bases(graph)
    relevant = [receipt for receipt in graph.coverage if "inherits" in receipt.relationship_kinds]
    assert relevant and all(receipt.status == "unavailable" for receipt in relevant)


def test_core_can_verify_an_independent_classifier_relationship_target(tmp_path: Path) -> None:
    from archkeel.check.uml_compare import compare_graphs

    observed = observed_graph(_observation(tmp_path, "class Base: pass\nclass Child(Base): pass\n"))
    target = ArchitectureGraph(
        "declared",
        (
            Entity(
                "base",
                "class",
                "sample.app.Base",
                "python",
                presence="planned",
                responsibilities=("Shared base",),
                provenance=("independent spec",),
            ),
            Entity(
                "child",
                "class",
                "sample.app.Child",
                "python",
                presence="planned",
                responsibilities=("Concrete child",),
                provenance=("independent spec",),
            ),
        ),
        (Relationship("extends", "inherits", "child", "base", provenance=("independent spec",)),),
    )
    comparison = compare_graphs(observed, target)
    assert comparison.status == "PASS"
    edge = next(item for item in comparison.assessments if item.subject_id == "extends")
    assert edge.fact_ids and edge.evidence_ids


@pytest.mark.parametrize("base, expected", [("", "FAIL"), ("(factory())", "UNKNOWN")])
def test_known_base_inventory_distinguishes_absence_from_unresolved_bases(
    tmp_path: Path, base: str, expected: str
) -> None:
    from archkeel.check.uml_compare import compare_graphs

    observed = observed_graph(
        _observation(tmp_path, f"class Base: pass\nclass Child{base}: pass\n")
    )
    target = ArchitectureGraph(
        "declared",
        (
            Entity(
                "base",
                "class",
                "sample.app.Base",
                "python",
                presence="planned",
                responsibilities=("Base",),
                provenance=("spec",),
            ),
            Entity(
                "child",
                "class",
                "sample.app.Child",
                "python",
                presence="planned",
                responsibilities=("Child",),
                provenance=("spec",),
            ),
        ),
        (Relationship("extends", "inherits", "child", "base", provenance=("spec",)),),
    )
    comparison = compare_graphs(observed, target)
    edge = next(item for item in comparison.assessments if item.subject_id == "extends")
    assert edge.status == expected


@pytest.mark.parametrize(
    "key, value",
    [
        ("relationship_kind", None),
        ("relationship_kind", "calls"),
        ("id", ""),
        ("evidence_ids", ()),
        ("status", "guess"),
    ],
)
def test_malformed_typed_base_facts_are_rejected(tmp_path: Path, key: str, value: object) -> None:
    observation = _observation(tmp_path, "class Base: pass\nclass Child(Base): pass\n")
    symbols = []
    for record in observation.records("symbols"):
        if record.data.get("qualified_name") == "sample.app.Child":
            [base] = record.data.get("base_declarations")
            record = replace(
                record,
                data=RecordData(
                    tuple(
                        (
                            name,
                            (RecordData(tuple({**dict(base.entries), key: value}.items())),)
                            if name == "base_declarations"
                            else content,
                        )
                        for name, content in record.data.entries
                    )
                ),
            )
        symbols.append(record)
    malformed = replace(
        observation,
        sections=tuple(
            Section(section.name, tuple(symbols)) if section.name == "symbols" else section
            for section in observation.sections
        ),
    )
    with pytest.raises(ValueError):
        observed_graph(malformed)


def test_external_classifier_kind_is_not_guessed_from_an_import(tmp_path: Path) -> None:
    graph = observed_graph(
        _observation(tmp_path, "from external import Port\nclass Client(Port): pass\n")
    )
    [edge] = _bases(graph)
    assert edge.resolution == "partial" and edge.target_id is None
    assert len(edge.candidate_ids) == 1
    assert all(
        receipt.status != "complete"
        for receipt in graph.coverage
        if receipt.scope_id == edge.source_id and "realizes" in receipt.relationship_kinds
    )


def test_stable_nested_class_namespace_can_identify_a_base(tmp_path: Path) -> None:
    graph = observed_graph(
        _observation(tmp_path, "class Outer:\n class Base: pass\nclass Child(Outer.Base): pass\n")
    )
    [edge] = _bases(graph)
    base = next(
        entity for entity in graph.entities if entity.qualified_name == "sample.app.Outer.Base"
    )
    assert edge.target_id == base.id and edge.resolution == "resolved"


@pytest.mark.parametrize("base, expected", [("(Port)", "PASS"), ("", "FAIL")])
def test_core_requires_explicit_protocol_realization_not_just_matching_methods(
    tmp_path: Path, base: str, expected: str
) -> None:
    from archkeel.check.uml_compare import compare_graphs

    observed = observed_graph(
        _observation(
            tmp_path,
            "from typing import Protocol\nclass Port(Protocol):\n def run(self): ...\n"
            + f"class Client{base}:\n def run(self): pass\n",
        )
    )
    target = ArchitectureGraph(
        "declared",
        (
            Entity(
                "port",
                "interface",
                "sample.app.Port",
                "python",
                presence="planned",
                responsibilities=("Port",),
                provenance=("spec",),
            ),
            Entity(
                "client",
                "class",
                "sample.app.Client",
                "python",
                presence="planned",
                responsibilities=("Client",),
                provenance=("spec",),
            ),
        ),
        (Relationship("implements", "realizes", "client", "port", provenance=("spec",)),),
    )
    comparison = compare_graphs(observed, target)
    assert comparison.status == expected

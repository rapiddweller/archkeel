# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Definition inventory must not invent runtime name bindings."""

import json
from dataclasses import replace

import pytest
from jsonschema import Draft202012Validator
from test_analyzer import _observe, _parsed_module
from test_uml_classifier_facts import _observation

from archkeel.analyzer.python.calls import collect_calls
from archkeel.analyzer.python.imports import collect_imports
from archkeel.analyzer.python.resolve import build_symbol_index
from archkeel.analyzer.python.symbols import collect_symbols
from archkeel.check.onboarding import public_top_level_names
from archkeel.check.uml_compare import compare_graphs
from archkeel.ir.architecture_graph import ArchitectureGraph, Entity
from archkeel.ir.graph_codec import graph_bytes, parse_graph
from archkeel.ir.interfaces import _public_symbol_names
from archkeel.ir.references import unreferenced_symbols
from archkeel.ir.source_graph import observed_graph
from tools.architecture_graph_schema import graph_schema


def _facts(source):
    module = _parsed_module(source)
    evidence = {}
    collect_imports([module], {module.module}, evidence, namespace="sample")
    symbols, _, _ = collect_symbols([module], evidence)
    calls = collect_calls([module], build_symbol_index(symbols), evidence)
    return symbols, calls, evidence


@pytest.mark.parametrize(
    ("source", "kind", "branch"),
    [
        ("if flag:\n def run(): pass\n", "if", "body"),
        ("if flag: pass\nelse:\n def run(): pass\n", "if", "else"),
        ("for item in items:\n def run(): pass\n", "for", "body"),
        ("for item in items: pass\nelse:\n def run(): pass\n", "for", "else"),
        ("while flag:\n def run(): pass\n", "while", "body"),
        ("while flag: pass\nelse:\n def run(): pass\n", "while", "else"),
        ("try:\n def run(): pass\nexcept Exception: pass\n", "try", "body"),
        ("try: pass\nexcept Exception:\n def run(): pass\n", "try", "handler"),
        ("try: pass\nexcept Exception: pass\nelse:\n def run(): pass\n", "try", "else"),
        ("try: pass\nfinally:\n def run(): pass\n", "try", "finally"),
        ("try: pass\nexcept* Exception:\n def run(): pass\n", "try_star", "handler"),
        ("with resource:\n def run(): pass\n", "with", "body"),
        ("match value:\n case 1:\n  def run(): pass\n", "match", "case"),
        ("async def outer():\n async for item in items:\n  def run(): pass\n", "async_for", "body"),
        ("async def outer():\n async with resource:\n  def run(): pass\n", "async_with", "body"),
    ],
)
def test_every_statement_branch_retains_a_definition_and_its_context(source, kind, branch):
    symbols, _, evidence = _facts(source)
    [run] = [item for item in symbols if item["data"]["name"] == "run"]
    [context] = run["data"]["definition_contexts"]
    assert (context["kind"], context["branch"]) == (kind, branch)
    assert context["evidence_ids"] and set(context["evidence_ids"]) <= evidence.keys()


def test_repeated_conditional_classes_keep_exact_parents_and_callers(tmp_path):
    observation = _observation(
        tmp_path,
        "def sink(): pass\n"
        "if flag:\n"
        " class Service:\n"
        "  def run(self): sink()\n"
        "else:\n"
        " class Service:\n"
        "  def run(self): sink()\n",
    )
    graph = observed_graph(observation)
    classes = [item for item in graph.entities if item.qualified_name == "sample.app.Service"]
    methods = [item for item in graph.entities if item.qualified_name == "sample.app.Service.run"]
    assert len(classes) == len(methods) == 2
    assert {item.parent_id for item in methods} == {item.id for item in classes}
    by_id = {item.id: item for item in classes}
    assert all(
        item.definition_contexts == by_id[item.parent_id].definition_contexts for item in methods
    )
    assert {edge.source_id for edge in graph.relationships if edge.kind == "calls"} == {
        item.id for item in methods
    }
    assert all(item.presence == "defined" for item in (*classes, *methods))
    assert not any(
        item.presence == "referenced" and item.id in {m.id for m in methods}
        for item in graph.entities
    )
    assert parse_graph(json.loads(graph_bytes(graph))) == graph
    Draft202012Validator(graph_schema()).validate(json.loads(graph_bytes(graph)))


def test_nested_contexts_are_ordered_without_executing_conditions():
    symbols, _, _ = _facts(
        "if never_execute():\n class Service:\n  try:\n   def run(self): pass\n  finally: pass\n"
    )
    [run] = [item for item in symbols if item["data"]["name"] == "run"]
    assert [(c["kind"], c["branch"]) for c in run["data"]["definition_contexts"]] == [
        ("if", "body"),
        ("try", "body"),
    ]


def test_handler_contexts_keep_their_own_source_locations():
    symbols, _, evidence = _facts(
        "try: pass\nexcept ValueError:\n class Service: pass\n"
        "except TypeError:\n class Service: pass\n"
    )
    classes = [item for item in symbols if item["kind"] == "class"]
    assert len(classes) == 2
    sites = [
        evidence[item["data"]["definition_contexts"][0]["evidence_ids"][0]] for item in classes
    ]
    assert {site["line"] for site in sites} == {2, 4}


@pytest.mark.parametrize(
    "source",
    [
        "if flag:\n def run(): pass\nrun()\n",
        "def run(): pass\nif flag:\n def run(): pass\nrun()\n",
        "class Service:\n if flag:\n  def run(self): pass\n def use(self): self.run()\n",
    ],
)
def test_conditional_bindings_are_candidates_never_confirmed_callees(source):
    symbols, calls, _ = _facts(source)
    [call] = calls
    assert call["data"]["status"] == "partially_resolved"
    assert call["data"]["targets"]
    assert "conditional" in call["data"]["reason"]
    assert any(item["data"].get("definition_contexts") for item in symbols)


def test_import_of_conditional_classifier_stays_partial(tmp_path):
    observation = _observation(
        tmp_path,
        "from sample.base import Base\nclass Child(Base): pass\nBase()\n",
        {"base.py": "if flag:\n class Base: pass\n"},
    )
    graph = observed_graph(observation)
    base = next(item for item in graph.entities if item.qualified_name == "sample.base.Base")
    relationships = [edge for edge in graph.relationships if edge.kind in {"calls", "inherits"}]
    assert len(relationships) == 2
    assert all(edge.target_id is None and edge.resolution == "partial" for edge in relationships)
    assert all(base.id in edge.candidate_ids for edge in relationships)


@pytest.mark.parametrize("kind", ["class", "enum", "interface"])
def test_conditional_inventory_does_not_settle_target_binding_or_classifier_kind(tmp_path, kind):
    graph = observed_graph(_observation(tmp_path, "if flag:\n class Service: pass\n"))
    target = ArchitectureGraph(
        "declared",
        (Entity("service", kind, "sample.app.Service", "python", provenance=("target.md",)),),
    )
    comparison = compare_graphs(graph, target)
    assert comparison.status == "UNKNOWN"
    assert all(item.status == "UNKNOWN" for item in comparison.assessments)
    assert any("control flow" in item.reason for item in comparison.assessments)


def test_conditional_definition_does_not_prove_a_public_api_name(tmp_path):
    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/__init__.py").write_text("")
    (tmp_path / "sample/app.py").write_text("if flag:\n def run(value: int) -> str: pass\n")
    (tmp_path / "contract.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [],
                "rules": [],
                "declarations": {"public_api": ["sample.app:run"]},
            }
        )
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    observation = result.observation
    assert any(item.kind == "api_surface_limit" for item in observation.records("unknowns"))
    assert public_top_level_names(observation.records("symbols")) == {}
    assert _public_symbol_names(observation) == {}
    assert not unreferenced_symbols(observation).candidates


@pytest.mark.parametrize("definition", ["class dict: pass", "def dict(): pass"])
def test_conditional_builtin_shadow_keeps_one_real_definition(tmp_path, definition):
    observation = _observation(tmp_path, f"if flag:\n {definition}\n")
    graph = observed_graph(observation)
    symbols = observation.records("symbols")
    assert len({item.id for item in symbols}) == len(symbols)
    [shadow] = [item for item in graph.entities if item.qualified_name == "sample.app.dict"]
    assert shadow.kind in {"class", "function"}
    assert shadow.definition_contexts and shadow.presence == "defined"
    [module] = [
        item
        for item in observation.records("modules")
        if item.data.get("qualified_name") == "sample.app"
    ]
    assert module.data.get("symbol_count") == 1


@pytest.mark.parametrize(
    "change",
    [
        {"kind": "invented"},
        {"branch": "invented"},
        {"branch": "finally"},
        {"evidence_ids": ()},
        {"evidence_ids": ("missing",)},
    ],
)
def test_malformed_context_cannot_become_an_authenticated_graph(tmp_path, change):
    graph = observed_graph(_observation(tmp_path, "if flag:\n class Service: pass\n"))
    service = next(item for item in graph.entities if item.kind == "class")
    [context] = service.definition_contexts
    with pytest.raises(ValueError):
        invalid = replace(service, definition_contexts=(replace(context, **change),))
        replace(
            graph,
            entities=tuple(invalid if item.id == service.id else item for item in graph.entities),
        ).validate()


def test_legacy_snapshots_remain_partial_without_context_capabilities(tmp_path):
    graph = observed_graph(_observation(tmp_path, "if flag:\n class Service: pass\n"))
    wire = json.loads(graph_bytes(graph))
    for entity in wire["entities"]:
        entity.pop("definition_contexts", None)
    old = parse_graph(wire)
    assert all(not entity.definition_contexts for entity in old.entities)
    assert all(
        item.status == "partial"
        for item in old.coverage
        if item.entity_kinds
        == ("class", "interface", "enum", "mixin", "method", "function", "type_alias", "constant")
    )


def test_independent_target_cannot_assert_source_definition_contexts(tmp_path):
    graph = observed_graph(_observation(tmp_path, "if flag:\n class Service: pass\n"))
    service = next(item for item in graph.entities if item.kind == "class")
    with pytest.raises(ValueError, match="observed source declarations"):
        ArchitectureGraph(
            "declared",
            (replace(service, parent_id=None, evidence_ids=(), provenance=("target.md",)),),
        ).validate()

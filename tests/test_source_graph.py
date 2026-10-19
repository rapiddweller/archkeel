# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Project actual analyzer evidence into the shared semantic graph."""

from dataclasses import replace
from pathlib import Path

import pytest
from test_analyzer import _observe

from archkeel.ir.architecture_graph import ArchitectureGraph


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


@pytest.mark.parametrize("change", ["missing", "owner", "kind"])
def test_inventory_projection_rejects_lost_or_misplaced_members(observation, change):
    from archkeel.ir.source_graph import _member_inventory_coverage

    entities = list(_graph(observation).entities)
    member = next(item for item in entities if item.qualified_name == "sample.service.Client.count")
    assert _member_inventory_coverage(observation, entities)
    entities.remove(member)
    if change == "owner":
        entities.append(replace(member, parent_id="different-owner"))
    elif change == "kind":
        entities.append(replace(member, kind="function"))
    with pytest.raises(ValueError, match="member inventory identities disagree"):
        _member_inventory_coverage(observation, entities)


def _graph_from_source_facts(facts, roots: tuple[str, ...]) -> ArchitectureGraph:
    from archkeel.ir.model import (
        AnalyzerInfo,
        ContractInfo,
        Coverage,
        Observation,
        Section,
        SourceInfo,
    )

    return _graph(
        Observation(
            schema_version="2.1.0",
            analyzer=AnalyzerInfo(
                facts.adapter.name, facts.adapter.version, facts.adapter.code_digest
            ),
            source=SourceInfo(
                facts.source.git_head,
                facts.source.dirty,
                facts.source.source_digest,
                roots,
            ),
            contract=ContractInfo("2.1.0", "0" * 64, "contract.json"),
            coverage=Coverage(
                "PASS" if facts.coverage.full_scope else "UNKNOWN",
                len(facts.files),
                facts.coverage.files_read,
                facts.coverage.files_parsed,
                None,
                None,
                None,
                None,
                100.0 if facts.coverage.full_scope else 0.0,
                None,
                (),
            ),
            sections=tuple(Section(section.name, section.records) for section in facts.sections),
            evidence=facts.evidence,
        )
    )


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
    assert by_name["sample.service.Client._token"].modifiers == ()
    assert by_name["sample.service.Client.count"].modifiers == ()
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


def test_script_global_dependency_is_a_reference_not_a_lexical_import(observation) -> None:
    dependency = next(
        item
        for item in observation.records("imports")
        if item.data.get("source_module") == "sample.app"
    )
    observation = replace(
        observation,
        sections=tuple(
            replace(
                section,
                records=tuple(
                    replace(item, kind="script_global") if item.id == dependency.id else item
                    for item in section.records
                ),
            )
            if section.name == "imports"
            else section
            for section in observation.sections
        ),
    )
    graph = _graph(observation)
    edge = next(item for item in graph.relationships if item.id == dependency.id)
    assert edge.kind == "references"
    assert edge.resolution == "resolved"
    assert edge.evidence_ids == dependency.evidence_ids
    assert edge.record_ids == (dependency.id,)
    assert all(
        item.status != "complete"
        for item in graph.coverage
        if item.scope_id == edge.source_id and "references" in item.relationship_kinds
    )


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


@pytest.mark.parametrize("language", ["python", "typescript"])
def test_call_result_bindings_keep_identity_initializer_and_creation(language, tmp_path):
    if language == "python":
        observation = _source_observation(
            tmp_path,
            "class Client: pass\ndef build():\n client = Client()\n return client\n",
        )
        graph = _graph(observation)
    else:
        from test_typescript_collect import _facts as collect_typescript

        facts = collect_typescript(
            tmp_path,
            {
                "src/main.ts": (
                    "class Client {}\n"
                    "export function build() {\n"
                    "  const client = new Client();\n"
                    "  return client;\n"
                    "}\n"
                )
            },
        )
        observation = facts
        graph = _graph_from_source_facts(facts, ("src",))

    calls = (
        observation.records("calls")
        if language == "python"
        else next(section.records for section in observation.sections if section.name == "calls")
    )
    call = next(
        record
        for record in calls
        if record.data.get("construction") is not None and record.data.get("result_bindings")
    )
    result_binding = call.data.get("result_bindings")[0]
    bindings = [item for item in graph.entities if item.id == result_binding.get("id")]
    assert len(bindings) == 1
    binding = bindings[0]
    assert binding.kind == "binding"
    assert binding.initializer == ("Client()" if language == "python" else "new Client()")
    construction = next(
        item
        for item in graph.relationships
        if item.kind == "creates" and call.id in item.record_ids
    )
    assert construction.resolution == "resolved"
    assert construction.target_id is not None
    entities = {item.id: item for item in graph.entities}
    assert entities[construction.target_id].qualified_name.endswith("Client")


def test_typescript_lexical_async_reaches_shared_uml_without_promise_inference(tmp_path):
    from test_typescript_collect import _facts as collect_typescript

    facts = collect_typescript(
        tmp_path,
        {
            "src/main.ts": (
                "export class Service {\n"
                "  async run(): Promise<void> {}\n"
                "  promiseOnly(): Promise<void> {}\n"
                "  async(): void {}\n"
                "}\n"
                "export async function load(): Promise<void> {}\n"
            )
        },
    )
    graph = _graph_from_source_facts(facts, ("src",))
    operations = {
        item.qualified_name.rsplit(".", 1)[-1]: item
        for item in graph.entities
        if item.kind in {"method", "function"}
    }
    assert operations["run"].modifiers == ("async",)
    assert operations["load"].modifiers == ("async",)
    assert operations["promiseOnly"].modifiers == ()
    assert operations["async"].modifiers == ()


def _source_observation(tmp_path: Path, source: str):
    package = tmp_path / "sample"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "app.py").write_text(source)
    result = _observe(tmp_path)
    assert result.observation is not None
    return result.observation

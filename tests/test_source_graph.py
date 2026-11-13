# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Project native TypeScript evidence into the shared semantic graph."""

from archkeel.ir.architecture_graph import ArchitectureGraph


def _graph_from_source_facts(facts, roots: tuple[str, ...]) -> ArchitectureGraph:
    from archkeel.ir.model import (
        AnalyzerInfo,
        ContractInfo,
        Coverage,
        Observation,
        Section,
        SourceInfo,
    )
    from archkeel.ir.source_graph import observed_graph

    graph = observed_graph(
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
    graph.validate()
    return graph


def test_call_result_bindings_keep_identity_initializer_and_creation(tmp_path):
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
    graph = _graph_from_source_facts(facts, ("src",))
    calls = next(section.records for section in facts.sections if section.name == "calls")
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
    assert binding.initializer == "new Client()"
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

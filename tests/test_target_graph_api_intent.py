# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Global public API intent remains independent and authenticated."""

import json
from dataclasses import replace

import pytest
from jsonschema import Draft202012Validator
from test_target_graph import (
    _contract,
    _nested_repository,
    _repository,
)

from archkeel.check.report import run_report
from archkeel.check.uml import assemble_uml
from archkeel.cli.observe import observe
from archkeel.ir.codec import (
    decode_canonical_model,
    parse_contract,
    parse_observation,
)
from archkeel.ir.graph_codec import graph_bytes, parse_graph
from archkeel.ir.target_graph import declared_graph
from archkeel.ir.target_records import recorded_target_graph
from tools.architecture_graph_schema import graph_schema


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

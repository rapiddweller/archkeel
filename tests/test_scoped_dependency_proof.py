# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Localized source gaps preserve only authenticated, complete dependency scopes."""

from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from test_result_schema import current_validator as current_validator
from test_typescript_partial_uml import _TypeScriptCollector

from archkeel.check.observe import Observer
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report, run_saved_report
from archkeel.ir.codec import decode_canonical_model, parse_observation, result_payload
from archkeel.ir.decisions import rule_assessments, rule_uncertainty_evidence
from archkeel.ir.model import Evidence, EvidenceClass, Record, RecordData, Section
from archkeel.ir.module_explore import module_exploration


def _component(label: str, modules: list[str], **extra) -> dict:
    return {
        "id": label,
        "label": label,
        "role": "component",
        "packages": [],
        "exact_modules": [f"demo.src.{name}_x2e_ts" for name in modules],
        "requires": [],
        "responsibilities": [f"Own {label}."],
        "forbidden_responsibilities": [],
        "provenance": ["docs/target.md"],
        "decided_by": "architect",
        **extra,
    }


RULE = {
    "id": "requires",
    "kind": "complete_requires",
    "rationale": "Permit only declared component dependencies.",
    "provenance": ["docs/target.md"],
    "decided_by": "architect",
}


def _project(root: Path, *, dynamic_a: bool = False, forbidden: bool = False):
    (root / "src").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "docs/target.md").write_text("Two independently owned nested scopes.\n")
    for name in ("a1", "a2", "b1", "b2"):
        text = "export {};\n"
        if name == "b1" or (name == "a1" and dynamic_a):
            text += "export const load = (id: string) => import(id);\n"
        if name == "a1":
            text += "import './a2';\n"
        (root / f"src/{name}.ts").write_text(text)
    (root / "tsconfig.json").write_text(
        json.dumps({"compilerOptions": {"module": "commonjs"}, "include": ["src"]})
    )
    for filename, components in (
        (
            "architecture-contract.json",
            [
                _component("a", ["a1", "a2"], inside="a.json"),
                _component("b", ["b1", "b2"], inside="b.json"),
            ],
        ),
        (
            "a.json",
            [
                _component(
                    "a1",
                    ["a1"],
                    requires=[]
                    if forbidden
                    else [
                        {
                            "component": "a2",
                            "rationale": "Use the sibling API.",
                            "decided_by": "architect",
                        }
                    ],
                ),
                _component("a2", ["a2"]),
            ],
        ),
        ("b.json", [_component("b1", ["b1"]), _component("b2", ["b2"])]),
    ):
        (root / filename).write_text(
            json.dumps({"schema_version": "2.2.0", "components": components, "rules": [RULE]})
        )
    for command in (
        ("git", "init", "-q", "-b", "main"),
        ("git", "config", "user.email", "test@example.invalid"),
        ("git", "config", "user.name", "Test"),
        ("git", "add", "-A"),
        ("git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture"),
    ):
        subprocess.run(command, cwd=root, check=True, capture_output=True)
    return ScanConfig(
        ("src",), "demo", "architecture-contract.json", "unused", language="typescript"
    )


def _report(root: Path, **options):
    config = _project(root, **options)
    result, encoded = run_report(root, config=config, analyzer=Observer(_TypeScriptCollector()))
    assert encoded is not None
    return result, encoded, parse_observation(decode_canonical_model(json.loads(encoded)))


def _rows(model):
    return {row.id: row for row in rule_assessments(model, undecided_by_rule={}, complete=False)}


@pytest.fixture
def dependency_binding_inputs():
    def record(identifier: str, kind: str) -> Record:
        return Record(
            identifier,
            EvidenceClass.FACT,
            "structure",
            kind,
            identifier,
            (),
            (),
            (),
            (),
            (),
            RecordData((("value", identifier),)),
        )

    sections = (
        Section("modules", (record("MODULE-2", "module"), record("MODULE-1", "module"))),
        Section("imports", (record("IMPORT", "import"),)),
        Section("symbols", (record("SYMBOL", "function"),)),
        Section(
            "declarations",
            (
                record("COMPONENT", "component_responsibility"),
                record("INSIDE", "inside_component_responsibility"),
                record("REQUIRES", "complete_requires"),
                record("OTHER-RULE", "forbidden_dependency"),
            ),
        ),
        Section("calls", (record("CALL", "call"),)),
        Section("unknowns", (record("UNRELATED", "complete_requires"),)),
    )
    failures = (record("GAP-2", "source_resolution_gap"), record("GAP-1", "source_resolution_gap"))
    evidence = (
        Evidence("EVIDENCE-2", "src/b.ts", 2, 2, 1, "export {};"),
        Evidence("EVIDENCE-1", "src/a.ts", 1, 1, 1, "import './b';"),
    )
    return sections, failures, evidence


def test_dependency_binding_preserves_recorded_ids_and_input_order(dependency_binding_inputs):
    from archkeel.ir.decisions import dependency_binding_id

    sections, failures, evidence = dependency_binding_inputs
    expected = "DEPENDENCY-PROOF-ed404729928d4d64"
    assert dependency_binding_id(sections, failures, evidence) == expected
    reordered = tuple(
        replace(section, records=tuple(reversed(section.records))) for section in reversed(sections)
    )
    assert (
        dependency_binding_id(iter(reordered), reversed(failures), reversed(evidence)) == expected
    )
    assert dependency_binding_id((*sections, sections[0]), failures, evidence) == (
        "DEPENDENCY-PROOF-f6f238c546f4d253"
    )


@pytest.mark.parametrize(
    "change",
    [
        "module",
        "import",
        "function",
        "component_responsibility",
        "inside_component_responsibility",
        "complete_requires",
        "failure",
        "evidence",
    ],
)
def test_dependency_binding_invalidates_changed_bound_content(
    dependency_binding_inputs, change: str
):
    from archkeel.ir.decisions import dependency_binding_id

    sections, failures, evidence = dependency_binding_inputs
    original = dependency_binding_id(sections, failures, evidence)
    if change == "failure":
        failures = (replace(failures[0], title="Changed failure"), *failures[1:])
    elif change == "evidence":
        evidence = (replace(evidence[0], excerpt="Changed evidence"), *evidence[1:])
    else:
        sections = tuple(
            replace(
                section,
                records=tuple(
                    replace(record, title="Changed record") if record.kind == change else record
                    for record in section.records
                ),
            )
            for section in sections
        )
    assert dependency_binding_id(sections, failures, evidence) != original


def test_dependency_binding_excludes_unrelated_sections_and_declarations(dependency_binding_inputs):
    from archkeel.ir.decisions import dependency_binding_id

    sections, failures, evidence = dependency_binding_inputs
    changed = tuple(
        replace(
            section,
            records=tuple(
                replace(record, title="Unrelated change")
                if section.name in {"calls", "unknowns"} or record.kind == "forbidden_dependency"
                else record
                for record in section.records
            ),
        )
        for section in sections
    )
    assert dependency_binding_id(changed, failures, evidence) == dependency_binding_id(
        sections, failures, evidence
    )


def test_dependency_binding_matches_core_issued_proof(tmp_path: Path):
    from archkeel.ir.decisions import dependency_binding_id

    _, _, model = _report(tmp_path / "project")
    receipt = next(
        record
        for record in model.records("scope_observations")
        if record.data.get("dependency_scope_proof")
    )
    assert receipt.data.get("dependency_scope_proof").get("binding_id") == (
        "DEPENDENCY-PROOF-e7455e745c3a5c89"
    )
    assert dependency_binding_id(model.sections, model.coverage.failures, model.evidence) == (
        "DEPENDENCY-PROOF-e7455e745c3a5c89"
    )


def test_unaffected_nested_requires_passes_with_partial_global_coverage(tmp_path: Path):
    result, encoded, model = _report(tmp_path / "project")
    rows = _rows(model)
    assert {key: row.status for key, row in rows.items()} == {
        "requires": "UNKNOWN",
        "a:requires": "PASS",
        "b:requires": "UNKNOWN",
    }
    assert rows["a:requires"].evaluation_proven
    assert model.coverage.status == "FAIL" and result.exit_code == 2
    assert (
        model.coverage.files_discovered
        == model.coverage.files_read
        == model.coverage.files_parsed
        == 4
    )
    assert "a:requires" not in rule_uncertainty_evidence(model)
    levels = module_exploration(model)
    assert any(
        cell.status == "PASS" for level in levels if level.parent_id == "a" for cell in level.cells
    )
    saved_path = tmp_path / "saved.json"
    saved_path.write_bytes(encoded)
    saved = run_saved_report(saved_path)
    assert {row.id: row.status for row in saved.rule_assessments or ()} == {
        key: row.status for key, row in rows.items()
    }
    _, repeated = run_report(
        tmp_path / "project",
        config=ScanConfig(
            ("src",), "demo", "architecture-contract.json", "unused", language="typescript"
        ),
        analyzer=Observer(_TypeScriptCollector()),
    )
    assert repeated == encoded


def test_target_authentication_failure_revokes_scoped_proof(tmp_path: Path):
    from archkeel.check.uml import assemble_uml

    root = tmp_path / "project"
    config = _project(root)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    result = Observer(_TypeScriptCollector())(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head=commit,
        dirty=False,
        contract_root=root,
        language="typescript",
    )
    assert _rows(result.observation)["a:requires"].status == "PASS"
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_bytes())
    contract["rules"][0]["rationale"] = "Different authenticated policy."
    path.write_text(json.dumps(contract))
    changed = assemble_uml(result, root, config.contract)
    assert changed.diagnostics
    assert _rows(changed.observation)["a:requires"].status == "UNKNOWN"


def test_real_nest_dynamic_import_blocks_account_but_not_sibling_rules():
    from dataclasses import replace as variant_replace

    from fixtures.architecture_demo import materialized_fixture
    from fixtures.demo_catalog_nest_realworld import VARIANTS

    baseline = VARIANTS[0]
    relative = "src/user/user.service.ts"
    changed = variant_replace(
        baseline,
        files={
            relative: (baseline.fixture / relative).read_text()
            + "\nexport const loader = (id: string) => import(id);\n"
        },
    )
    with materialized_fixture(changed) as root:
        result, encoded = run_report(
            root,
            config=ScanConfig(
                ("src",),
                "nestjs.realworld",
                "architecture-contract.json",
                "unused",
                language="typescript",
                tsconfig="tsconfig.build.json",
            ),
            analyzer=Observer(_TypeScriptCollector(), tsconfig="tsconfig.build.json"),
        )
    assert encoded is not None and result.exit_code == 2
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    rows = _rows(model)
    assert rows["Account and authentication:REQUIRES-COMPLETE"].status == "UNKNOWN"
    assert rows["REQUIRES-COMPLETE"].status == "UNKNOWN"
    assert rows["API composition:REQUIRES-COMPLETE"].status == "PASS"
    assert rows["Article and comment publishing:REQUIRES-COMPLETE"].status == "PASS"
    assert model.coverage.files_read == model.coverage.files_parsed == 41
    assert len(model.coverage.failures) == 2


def test_dynamic_import_blocks_its_nested_scope_and_ancestors(tmp_path: Path):
    _, _, model = _report(tmp_path / "project", dynamic_a=True)
    assert {row.status for row in _rows(model).values()} == {"UNKNOWN"}


def test_static_violation_wins_over_unrelated_source_gap(tmp_path: Path, current_validator):
    result, _, model = _report(tmp_path / "project", forbidden=True)
    assert _rows(model)["a:requires"].status == "FAIL"
    assert result.declared_rules == "FAIL"
    assert result.exit_code == 2 and model.coverage.status == "FAIL"
    assert not list(current_validator.iter_errors(result_payload(result)))
    path = tmp_path / "saved.json"
    _, encoded = run_report(
        tmp_path / "project",
        config=ScanConfig(
            ("src",), "demo", "architecture-contract.json", "unused", language="typescript"
        ),
        analyzer=Observer(_TypeScriptCollector()),
    )
    path.write_bytes(encoded)
    for facet in (
        {"only_violations": True},
        {"only_architecture": True, "full_architecture": True},
    ):
        fresh, _ = run_report(
            tmp_path / "project",
            config=ScanConfig(
                ("src",), "demo", "architecture-contract.json", "unused", language="typescript"
            ),
            analyzer=Observer(_TypeScriptCollector()),
            **facet,
        )
        saved = run_saved_report(path, **facet)
        assert fresh.declared_rules == saved.declared_rules == "FAIL"
        assert not list(current_validator.iter_errors(result_payload(fresh)))
        assert not list(current_validator.iter_errors(result_payload(saved)))
        assert fresh.filtered_violations and saved.filtered_violations
        assert [row.record.id for row in fresh.filtered_violations] == [
            row.record.id for row in saved.filtered_violations
        ]


def test_command8_retains_legacy_unknown_and_requires_a_partial_fail_row(
    tmp_path: Path, current_validator
):
    import copy

    from test_result_schema import _validator

    result, _, _ = _report(tmp_path / "project", forbidden=True)
    payload = result_payload(result)
    legacy = _validator("command-result-7.0.schema.json")
    assert current_validator.is_valid(payload)
    assert not legacy.is_valid(payload)
    unknown = copy.deepcopy(payload)
    unknown["declared_rules"] = "UNKNOWN"
    assert legacy.is_valid(unknown) and current_validator.is_valid(unknown)
    for field, value in (
        ("declared_rules", "PASS"),
        ("command", "check"),
        ("command", "validate"),
        ("coverage", None),
    ):
        invalid = copy.deepcopy(payload)
        invalid[field] = value
        assert not current_validator.is_valid(invalid)
    invalid = copy.deepcopy(payload)
    for row in invalid["rule_assessments"]:
        row["status"] = "UNKNOWN"
    assert not current_validator.is_valid(invalid)


def _changed_gap(facts, *, kind=None, signature=False):
    from archkeel.ir.facts_codec import parse_record, raw_record

    old = facts.coverage.gaps[0]
    raw = raw_record(old)
    if kind:
        raw["kind"] = kind
        raw["data"].pop("resolution_dimension")
    if signature:
        method = next(r for s in facts.sections for r in s.records if r.kind == "method")
        raw["data"]["resolution_dimension"] = "signature"
        raw["fact_ids"] = [method.id]
    changed = parse_record(raw)
    return replace(
        facts,
        coverage=replace(facts.coverage, gaps=(changed,)),
        sections=tuple(
            replace(s, records=tuple(changed if r.id == old.id else r for r in s.records))
            for s in facts.sections
        ),
    )


@pytest.mark.parametrize("signature", [False, True])
def test_collector_cannot_relabel_unknown_import_impact(tmp_path: Path, signature: bool):
    root = tmp_path / "project"
    config = _project(root)
    if signature:
        (root / "src/b1.ts").write_text(
            "export class Loader { load(id: string = './other') { return import(id); } }\n"
        )

    def transform(facts):
        return _changed_gap(
            facts, signature=signature, kind=None if signature else "UnsupportedDeclaration"
        )

    result, _ = run_report(
        root, config=config, analyzer=Observer(_TypeScriptCollector(transform=transform))
    )
    assert all(row.status != "PASS" for row in result.rule_assessments or ())


def test_saved_proof_binds_import_and_declaration_contents(tmp_path: Path):
    from archkeel.ir.codec import canonical_report_bytes
    from archkeel.ir.facts_codec import parse_record, raw_record

    _, _, model = _report(tmp_path / "project")
    a2 = next(
        r for r in model.records("modules") if r.data.get("qualified_name") == "demo.src.a2_x2e_ts"
    )
    for change in ("import", "permission"):
        sections = []
        for section in model.sections:
            records = []
            for record in section.records:
                raw = raw_record(record)
                if change == "import" and record.kind == "import":
                    raw["data"]["source_module"] = "demo.src.a2_x2e_ts"
                    raw["data"]["target_module"] = "demo.src.a1_x2e_ts"
                    raw["subjects"] = ["demo.src.a2_x2e_ts", "demo.src.a1_x2e_ts"]
                    raw["evidence_ids"] = list(a2.evidence_ids)
                if change == "permission" and record.id == "a:a1":
                    raw["data"]["requires"] = []
                records.append(parse_record(raw))
            sections.append(replace(section, records=tuple(records)))
        changed = replace(model, sections=tuple(sections))
        assert _rows(changed)["a:requires"].status == "UNKNOWN"
        path = tmp_path / f"{change}.json"
        path.write_bytes(canonical_report_bytes(changed))
        assert (
            next(r for r in run_saved_report(path).rule_assessments if r.id == "a:requires").status
            == "UNKNOWN"
        )


@pytest.mark.parametrize("change", ["module", "subjects"])
def test_gap_origin_cannot_contradict_other_attribution(tmp_path: Path, change: str):
    from archkeel.ir.facts_codec import parse_record, raw_record

    def transform(facts):
        gap = facts.coverage.gaps[0]
        raw = raw_record(gap)
        raw["data"]["source_module"] = "demo.src.b1_x2e_ts"
        if change == "module":
            raw["data"]["module"] = "demo.src.a1_x2e_ts"
        else:
            raw["subjects"].append("demo.src.a1_x2e_ts")
        changed = parse_record(raw)
        return replace(
            facts,
            coverage=replace(facts.coverage, gaps=(changed,)),
            sections=tuple(
                replace(s, records=tuple(changed if r.id == gap.id else r for r in s.records))
                for s in facts.sections
            ),
        )

    root = tmp_path / "project"
    result, _ = run_report(
        root,
        config=_project(root),
        analyzer=Observer(_TypeScriptCollector(transform=transform)),
    )
    assert all(row.status != "PASS" for row in result.rule_assessments or ())


def test_invalid_matching_runtime_proof_and_late_diagnostic_are_blocked(tmp_path: Path):
    from test_typescript_partial_uml import _runtime_blocker

    from archkeel.ir.codec import canonical_report_bytes
    from archkeel.ir.facts_codec import parse_record, raw_record

    _, _, model = _report(tmp_path / "project")
    sections = []
    for section in model.sections:
        records = []
        for record in section.records:
            raw = raw_record(record)
            if raw["data"].get("dependency_scope_proof"):
                raw["data"]["dependency_scope_proof"]["runtime"]["version"] = "0.0.0"
            records.append(parse_record(raw))
        sections.append(replace(section, records=tuple(records)))
    changed = replace(
        model, runtime=replace(model.runtime, version="0.0.0"), sections=tuple(sections)
    )
    assert _rows(changed)["a:requires"].status == "UNKNOWN"
    path = tmp_path / "runtime.json"
    path.write_bytes(canonical_report_bytes(changed))
    assert (
        next(r for r in run_saved_report(path).rule_assessments if r.id == "a:requires").status
        == "UNKNOWN"
    )

    def late(*args, **kwargs):
        result = Observer(_TypeScriptCollector())(*args, **kwargs)
        return replace(result, diagnostics=(*result.diagnostics, _runtime_blocker()))

    result, encoded = run_report(
        tmp_path / "project",
        config=ScanConfig(
            ("src",), "demo", "architecture-contract.json", "unused", language="typescript"
        ),
        analyzer=late,
    )
    assert all(row.status != "PASS" for row in result.rule_assessments or ())
    assert encoded is not None
    path.write_bytes(encoded)
    saved = run_saved_report(path)
    assert all(row.status != "PASS" for row in saved.rule_assessments or ())


def test_unicode_numeric_runtime_cannot_authenticate_scope(tmp_path: Path):
    from archkeel.ir.facts_codec import parse_record, raw_record

    _, _, model = _report(tmp_path / "project")
    version = "٣.١١.١٢"
    sections = []
    for section in model.sections:
        records = []
        for record in section.records:
            raw = raw_record(record)
            if raw["data"].get("dependency_scope_proof"):
                raw["data"]["dependency_scope_proof"]["runtime"]["version"] = version
            records.append(parse_record(raw))
        sections.append(replace(section, records=tuple(records)))
    changed = replace(
        model, runtime=replace(model.runtime, version=version), sections=tuple(sections)
    )
    assert _rows(changed)["a:requires"].status == "UNKNOWN"


def test_known_violation_lenses_survive_when_every_scope_is_uncertain(
    tmp_path: Path, current_validator
):
    result, encoded, _ = _report(tmp_path / "project", forbidden=True, dynamic_a=True)
    assert not any(row.evaluation_proven for row in result.rule_assessments)
    path = tmp_path / "all-uncertain.json"
    path.write_bytes(encoded)
    config = ScanConfig(
        ("src",), "demo", "architecture-contract.json", "unused", language="typescript"
    )
    for facet in (
        {"only_violations": True},
        {"only_architecture": True, "full_architecture": True},
        {"rule": "b:requires"},
        {"component": "b"},
    ):
        fresh, _ = run_report(
            tmp_path / "project", config=config, analyzer=Observer(_TypeScriptCollector()), **facet
        )
        saved = run_saved_report(path, **facet)
        assert fresh.declared_rules == saved.declared_rules == "FAIL"
        if "rule" not in facet and "component" not in facet:
            assert fresh.filtered_violations and saved.filtered_violations
        assert current_validator.is_valid(result_payload(fresh))
        assert current_validator.is_valid(result_payload(saved))


def test_unresolved_dart_super_signature_does_not_block_dependencies(tmp_path: Path):
    from test_dart_partial_uml import _DartCollector
    from test_dart_partial_uml import _project as dart_project

    root, config = dart_project(
        tmp_path / "dart", "class Child extends MissingParent { Child({super.key}); }\n"
    )
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_bytes())
    contract["rules"] = [RULE]
    path.write_text(json.dumps(contract))
    result, encoded = run_report(root, config=config, analyzer=Observer(_DartCollector()))
    assert encoded is not None
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    assert _rows(model)["requires"].status == "PASS"
    assert model.coverage.status == "FAIL" and result.exit_code == 2
    gap = model.coverage.failures[0]
    assert gap.data.get("resolution_dimension") == "signature"
    assert gap.fact_ids
    method = next(r for r in model.records("symbols") if r.id in gap.fact_ids)
    assert method.data.get("signature_complete") is False


@pytest.mark.parametrize(
    "change",
    [
        "runtime",
        "reads",
        "parses",
        "contract",
        "gap-module",
        "gap-impact",
        "gap-evidence",
        "old-receipt",
        "imports",
        "ownership",
    ],
)
def test_scoped_receipt_cannot_survive_changed_or_unbound_evidence(tmp_path: Path, change: str):
    _, _, model = _report(tmp_path / "project")
    assert _rows(model)["a:requires"].status == "PASS"
    if change == "runtime":
        model = replace(model, runtime=replace(model.runtime, version="0.0.0"))
    elif change in {"reads", "parses"}:
        field = "files_read" if change == "reads" else "files_parsed"
        model = replace(model, coverage=replace(model.coverage, **{field: 3}))
    elif change == "contract":
        model = replace(model, contract=replace(model.contract, digest="0" * 64))
    elif change.startswith("gap-"):
        gap = model.coverage.failures[0]
        data = dict(gap.data.entries)
        if change == "gap-module":
            data["module"] = "demo.src.a1_x2e_ts"
        if change == "gap-impact":
            data["resolution_dimension"] = "signature"
        from archkeel.ir.facts_codec import parse_record, raw_record

        raw = raw_record(gap)
        raw["data"] = data
        if change == "gap-evidence":
            raw["evidence_ids"] = []
        changed = parse_record(raw)
        model = replace(model, coverage=replace(model.coverage, failures=(changed,)))
    elif change == "imports":
        model = replace(
            model,
            sections=tuple(
                replace(section, records=()) if section.name == "imports" else section
                for section in model.sections
            ),
        )
    else:
        from archkeel.ir.facts_codec import parse_record, raw_record

        sections = []
        for section in model.sections:
            records = []
            for record in section.records:
                if record.kind == "rule_evaluation" and change == "old-receipt":
                    raw = raw_record(record)
                    raw["data"] = {"scope": record.data.get("scope")}
                    record = parse_record(raw)
                if record.id == "a:a2" and change == "ownership":
                    raw = raw_record(record)
                    raw["data"]["exact_modules"] = []
                    record = parse_record(raw)
                records.append(record)
            sections.append(replace(section, records=tuple(records)))
        model = replace(model, sections=tuple(sections))
    assert _rows(model)["a:requires"].status == "UNKNOWN"


@pytest.mark.parametrize("wire", ["role", "rule", "decorated-string"])
def test_open_record_strings_are_canonical_primitives_before_json(wire, dependency_binding_inputs):
    from archkeel.ir.architecture_graph import ArchitectureRuleKind, DecisionMaker
    from archkeel.ir.facts_codec import parse_record, record_payload

    class DecoratedString(str):
        def __str__(self):
            return "presentation-only"

    member = {
        "role": DecisionMaker.AGENT,
        "rule": ArchitectureRuleKind.COMPLETE_REQUIRES,
        "decorated-string": DecoratedString("actual wire text"),
    }[wire]
    sections, _, _ = dependency_binding_inputs
    raw = record_payload(sections[0].records[0])
    raw["kind"] = member
    raw["data"] = {"value": member, "nested": [{"value": member}]}
    initial = parse_record(raw)
    replay = parse_record(json.loads(json.dumps(raw)))
    assert type(initial.kind) is str
    assert type(initial.data.get("value")) is str
    assert type(initial.data.get("nested")[0].get("value")) is str
    assert type(initial.evidence_class) is EvidenceClass
    assert repr(initial) == repr(replay)
    assert json.dumps(record_payload(initial), sort_keys=True) == json.dumps(raw, sort_keys=True)


def _dependency_model_from_core(root):
    config = _project(root)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    result = Observer(_TypeScriptCollector())(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head=commit,
        dirty=False,
        contract_root=root,
        language=config.language,
    )
    assert result.observation is not None
    return result.observation


def test_dependency_binding_is_identical_before_and_after_the_real_json_boundary(tmp_path):
    from archkeel.ir.codec import observation_payload
    from archkeel.ir.decisions import dependency_binding_id

    initial = _dependency_model_from_core(tmp_path / "project")
    replay = parse_observation(json.loads(json.dumps(observation_payload(initial))))
    initial_id = dependency_binding_id(
        initial.sections, initial.coverage.failures, initial.evidence
    )
    replay_id = dependency_binding_id(replay.sections, replay.coverage.failures, replay.evidence)
    receipt = next(
        row
        for row in initial.records("scope_observations")
        if row.data.get("dependency_scope_proof")
    )
    issued_id = receipt.data.get("dependency_scope_proof").get("binding_id")
    assert issued_id == initial_id == replay_id == "DEPENDENCY-PROOF-e7455e745c3a5c89"

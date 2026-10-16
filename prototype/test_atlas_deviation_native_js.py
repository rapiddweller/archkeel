"""Actual JS deviation source supplies a trace-valid positive witness, never absence."""

import json
import sys
from pathlib import Path

sys.path.insert(0, "tests")
from test_typescript_collect import _facts

from archkeel.check.observation import assemble_observation
from archkeel.ir.decisions import rule_assessments, unknown_positions_by_rule
from archkeel.ir.facts import ConstructSupport, ForbiddenConstructKind, Language, SourceSectionName
from archkeel.ir.trace import trace_valid_violations

GUARD = "ATLAS-DEVIATION-NATIVE-CONTROL"


def test_actual_deviation_source_mutation_has_trace_valid_failure(tmp_path):
    source = Path("src/archkeel/render/assets/report-atlas-deviations.js").read_text()
    before = "?.kind === G.AtlasDeviationKind.UNDECLARED"
    assert source.count(before) == 1
    contract = {
        "schema_version": "2.1.0", "components": [],
        "rules": [{
            "id": GUARD, "kind": "forbidden_construct", "source": "app",
            "constructs": ["string_literal_compare"], "rationale": "Use the owned kind.",
            "provenance": ["architecture.md"], "decided_by": "architect",
        }],
    }
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(contract))
    (tmp_path / "architecture.md").write_text("The actual consumer uses nominal deviation kinds.\n")
    intent = path.read_bytes()

    def observed(content):
        facts = _facts(tmp_path, {"src/main.js": content}, options={
            "module": "CommonJS", "moduleResolution": "Node", "allowJs": True, "checkJs": True,
        })
        support = next(item.status for item in facts.capabilities.constructs
                       if item.name is ForbiddenConstructKind.STRING_LITERAL_COMPARE)
        assert support is ConstructSupport.PARTIAL
        model, _ = assemble_observation(facts, contract_root=tmp_path, contract_path=path,
            roots=("src",), namespace="app", language=Language.TYPESCRIPT)
        rule = next(row for row in rule_assessments(model,
            undecided_by_rule=unknown_positions_by_rule(model), complete=model.coverage.status=="PASS")
            if row.id==GUARD)
        records = tuple(row for section in facts.sections
                        if section.name is SourceSectionName.CONSTRUCTS for row in section.records)
        assert path.read_bytes() == intent
        return facts, model, rule, records, support

    _, clean, original_rule, original_records, _ = observed(source)
    assert original_rule.status == "UNKNOWN"
    assert not original_records
    assert not any(GUARD in row.rule_ids for row in trace_valid_violations(clean))
    facts, changed, rule, records, support = observed(
        source.replace(before, '?.kind === "undeclared"', 1))
    assert rule.status == "FAIL" and len(records) == 1
    violations = tuple(row for row in trace_valid_violations(changed) if GUARD in row.rule_ids)
    assert len(violations) == 1 and violations[0].fact_ids == (records[0].id,)
    evidence = {row.id: row for row in facts.evidence}
    assert any(evidence[key].excerpt == '"undeclared"' for key in records[0].evidence_ids)
    assert path.read_bytes() == intent
    print("ATLAS_NATIVE_JS=" + json.dumps({
        "original_status": original_rule.status, "mutated_status": rule.status,
        "trace_valid": True, "capability": support.value,
        "actual_construct_count": len(records), "absence_pass_claimed": False,
    }))

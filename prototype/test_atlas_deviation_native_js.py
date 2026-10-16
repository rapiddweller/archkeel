"""Native observation proves the actual deviation consumer mutation without absence claims."""

import json
from pathlib import Path

from test_architecture_demo import _prepare_repo
from test_uml_evaluation import _model

from archkeel.check.ports import ScanConfig
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.facts import ConstructSupport, Language
from archkeel.ir.model import ForbiddenConstructKind
from archkeel.ir.trace import trace_valid_violations

GUARD = "ATLAS-DEVIATION-NATIVE-CONTROL"


def test_actual_deviation_source_mutation_has_trace_valid_failure(tmp_path):
    source = Path("src/archkeel/render/assets/report-atlas-deviations.js").read_text()
    before = "?.kind === G.AtlasDeviationKind.UNDECLARED"
    assert source.count(before) == 1
    contract = {
        "schema_version": "2.2.0",
        "components": [{
            "id": "deviation", "label": "deviation", "role": "component",
            "packages": ["browser.deviations"], "public": [],
            "responsibilities": ["Classify recorded Atlas deviation pairs."],
            "forbidden_responsibilities": [], "provenance": ["docs/intent.md"],
        }],
        "rules": [{
            "id": GUARD, "kind": "forbidden_construct", "source": "browser.deviations",
            "constructs": ["string_literal_compare"], "rationale": "Use the owned kind.",
            "provenance": ["docs/intent.md"], "decided_by": "architect",
        }],
    }
    root = _prepare_repo(tmp_path, {
        "src/deviations.js": source, "contract.json": json.dumps(contract),
        "docs/intent.md": "The actual consumer uses nominal deviation kinds.\n",
        "tsconfig.json": json.dumps({"compilerOptions": {"allowJs": True, "checkJs": True},
                                     "files": ["src/deviations.js"]}),
    })
    config = ScanConfig(("src",), "browser", "contract.json", "0" * 64,
                        language=Language.TYPESCRIPT, tsconfig="tsconfig.json")
    intent = (root / "contract.json").read_bytes()
    original = _model(root, config)
    original_rule = next(row for row in rule_assessments(original, undecided_by_rule={})
                         if row.id == GUARD)
    assert original_rule.status == "UNKNOWN" and not original_rule.evaluation_proven
    assert not any(GUARD in row.rule_ids for row in trace_valid_violations(original))
    (root / "src/deviations.js").write_text(source.replace(before, '?.kind === "undeclared"', 1))
    mutated = _model(root, config)
    rule = next(row for row in rule_assessments(mutated, undecided_by_rule={}) if row.id == GUARD)
    assert rule.status == "FAIL" and rule.evaluation_proven
    assert any(GUARD in row.rule_ids for row in trace_valid_violations(mutated))
    assert (root / "contract.json").read_bytes() == intent
    print("ATLAS_NATIVE_JS=" + json.dumps({
        "original_status": original_rule.status, "mutated_status": rule.status,
        "trace_valid": True, "capability": ConstructSupport.PARTIAL.value,
        "construct": ForbiddenConstructKind.STRING_LITERAL_COMPARE.value,
        "absence_pass_claimed": False,
    }))

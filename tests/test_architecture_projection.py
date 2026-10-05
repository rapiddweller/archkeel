# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The focused architecture view retains ownership, decisions and global evidence."""

import ast
import json
import subprocess
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from test_result_schema import validator as validator
from test_target_graph import _nested_repository

from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.cli import main
from archkeel.cli.observe import observe
from archkeel.ir.architecture_graph import RuleAssessment as GraphRuleAssessment
from archkeel.ir.architecture_graph import RuleAssessmentStatus as GraphRuleAssessmentStatus
from archkeel.ir.codec import decode_canonical_model, parse_observation, parse_record, result_bytes
from archkeel.ir.model import RuleAssessment, RuleAssessmentStatus
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.report_projection import (
    architecture_command_envelope,
    architecture_projection,
    short_selector,
    unknown_groups,
)
from archkeel.render.summary import report_summary


def test_native_reexported_assessment_requires_its_physical_public_owner(tmp_path):
    root, config = _repository(tmp_path)
    (root / "sample/core.py").write_text(
        "from .other import RuleAssessment\n\n"
        "def run(value: RuleAssessment) -> RuleAssessment:\n    return value\n"
    )
    (root / "sample/other.py").write_text(
        'from .store import RuleAssessment as RuleAssessment\n__all__ = ["RuleAssessment"]\n'
    )
    source = Path(__file__).resolve().parents[1] / "src/archkeel/ir/architecture_graph.py"
    shared = source.read_text()
    definition = next(
        item
        for item in ast.parse(shared).body
        if isinstance(item, ast.ClassDef) and item.name == "RuleAssessment"
    )
    first_line = min(definition.lineno, *(item.lineno for item in definition.decorator_list))
    declaration = "\n".join(shared.splitlines()[first_line - 1 : definition.end_lineno])
    (root / "sample/store.py").write_text(
        "from dataclasses import dataclass\nfrom typing import Literal, TypeAlias\n"
        'RuleAssessmentStatus: TypeAlias = Literal["PASS", "FAIL", "UNKNOWN", "DECLARATION"]\n'
        + declaration
        + "\n"
    )
    path = root / config.contract
    contract = json.loads(path.read_bytes())
    contract["components"][1]["public"] = []
    contract["rules"] = [
        {
            "id": "TYPES",
            "kind": "boundary_types",
            "source": "sample.core",
            "rationale": "Declare the shared assessment's physical owner.",
            "provenance": ["docs/target.md"],
            "decided_by": "architect",
        }
    ]
    for public, expected in (([], "FAIL"), (["sample.store:RuleAssessment"], "PASS")):
        contract["components"][1]["public"] = public
        path.write_text(json.dumps(contract))
        result, _ = run_report(root, config=config, analyzer=observe, only_architecture=True)
        (assessment,) = result.rule_assessments
        assert assessment.status == expected
        assert assessment.evaluation_proven


def test_public_rule_assessment_import_preserves_identity_constructor_and_fields():
    assert RuleAssessment is GraphRuleAssessment
    assert RuleAssessmentStatus is GraphRuleAssessmentStatus
    values = (
        "RULE",
        "complete_requires",
        "UNKNOWN",
        False,
        0,
        2,
        "architect",
        "Own boundaries.",
        ("docs/target.md",),
        "missing receipt",
        "core",
        ("CORE",),
    )
    assessment = RuleAssessment(*values)

    assert assessment == GraphRuleAssessment(*values)
    assert asdict(assessment) == {
        "id": "RULE",
        "kind": "complete_requires",
        "status": "UNKNOWN",
        "evaluation_proven": False,
        "count": 0,
        "undecided": 2,
        "decided_by": "architect",
        "rationale": "Own boundaries.",
        "provenance": ("docs/target.md",),
        "reason": "missing receipt",
        "scope": "core",
        "components": ("CORE",),
    }


def _repository(tmp_path, *, closed=True):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "sample").mkdir()
    for name, source in {
        "__init__": "",
        "core": "import sample.store\nimport sample.other\n",
        "store": "",
        "other": "",
        "idle": "",
    }.items():
        (root / "sample" / f"{name}.py").write_text(source)
    components = [
        {
            "id": name.upper(),
            "label": name,
            "role": "component",
            "packages": [f"sample.{name}"],
            "namespace": f"sample.{name}",
            "responsibilities": [f"Own {name}."],
            "forbidden_responsibilities": ["Own another boundary."],
            "public": [f"sample.{name}"],
            "provenance": ["docs/target.md"],
            "decided_by": "architect",
            "requires": [],
        }
        for name in ("core", "store", "other", "idle")
    ]
    components[0]["requires"] = [
        {
            "component": "store",
            "rationale": "Persist through the store boundary.",
            "decided_by": "architect",
        }
    ]
    components[2]["requires"] = [
        {
            "component": "idle",
            "rationale": "Keep the unused boundary permission explicit.",
            "decided_by": "agent",
        }
    ]
    rules = [
        {
            "id": "NO-OTHER",
            "kind": "forbidden_dependency",
            "source": "sample.core",
            "target": "sample.other",
            "include_type_checking": True,
            "rationale": "Other owns an independent boundary.",
            "provenance": ["docs/target.md"],
            "decided_by": "architect",
        }
    ]
    if closed:
        rules.append(
            {
                "id": "COMPLETE",
                "kind": "complete_requires",
                "rationale": "Only named permissions may cross.",
                "provenance": ["docs/target.md"],
                "decided_by": "architect",
            }
        )
    (root / "architecture-contract.json").write_text(
        json.dumps({"schema_version": "2.1.0", "components": components, "rules": rules})
    )
    (root / "archkeel.toml").write_text(
        '[scan]\nroots=["sample"]\nnamespace="sample"\ncontract="architecture-contract.json"\n'
    )
    (root / "pyproject.toml").write_text(
        '[project]\nname="projection-test"\nversion="0.0.0"\nrequires-python=">=3.11,<3.12"\n'
    )
    (root / "docs").mkdir()
    (root / "docs/target.md").write_text("Own explicit boundaries.\n")
    for args in (
        ("init", "-q", "-b", "main"),
        ("config", "user.email", "demo@example.invalid"),
        ("config", "user.name", "Demo"),
        ("add", "-A"),
        ("-c", "commit.gpgsign=false", "commit", "-qm", "projection fixture"),
    ):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    return root, ScanConfig(("sample",), "sample", "architecture-contract.json", "0" * 64)


def test_real_cli_answers_intent_permission_ownership_and_finding(tmp_path, capsys, validator):
    root, _ = _repository(tmp_path)
    assert (
        main(
            [
                "report",
                "--root",
                str(root),
                "--only",
                "architecture",
                "--output",
                str(tmp_path / "output.json"),
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "1.0.0"
    view = payload["architecture_projection"]
    core = next(item for item in view["components"] if item["id"] == "CORE")
    assert core["path"] == "sample/core.py"
    assert core["provenance"] == ["docs/target.md"]
    assert core["responsibilities"] == ["Own core."]
    assert core["not_responsible_for"] == ["Own another boundary."]
    assert core["namespace"] + next(iter(core["public"])) == "sample.core"
    assert core["public"] == {"": [""]}
    assert core["decided_by"] == "architect"
    assert core["modules"] == {"": ""}
    (requirement,) = core["requires"]
    assert requirement["target_id"] == "STORE" and requirement["observed_imports"] == 1
    assert requirement["rationale"] == "Persist through the store boundary."
    permissions = {
        target: item["status"] for item in core["permissions"] for target in item["target_ids"]
    }
    assert permissions == {"IDLE": "forbidden", "OTHER": "forbidden", "STORE": "allowed"}
    assert view["levels"][0]["declared"] == 2
    assert view["levels"][0]["used"] == 2
    assert view["levels"][0]["unused"] == 1
    assert view["levels"][0]["undeclared"] == 1
    assert "sample" in view["levels"][0]["unowned_modules"]
    assert (
        view["source"]["git_head"]
        == subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    )
    assert view["source"]["source_digest"] and view["contract_digest"]
    violation = next(
        item for item in payload["filtered_violations"] if item["rule_ids"] == ["NO-OTHER"]
    )
    assert violation["locations"] == [{"path": "sample/core.py", "line": 2}]
    assert view["violation_remedy"] == "Change the code or amend the contract with owner approval."
    assert payload["declared_rules"] == "FAIL"
    assert not list(validator.iter_errors(payload))


def test_open_permission_does_not_become_allowed_from_observed_use(tmp_path):
    root, config = _repository(tmp_path, closed=False)
    result, _ = run_report(root, config=config, analyzer=observe, only_architecture=True)
    core = next(item for item in result.architecture_projection.components if item.id == "CORE")
    permissions = {item.target_id: item.status for item in core.permissions}
    assert permissions == {"IDLE": "undecided", "OTHER": "forbidden", "STORE": "allowed"}
    assert core.status == "UNKNOWN" and core.reason
    assert result.architecture_projection.unknowns


def test_component_slice_preserves_global_verdict_coverage_digests_and_unknowns(tmp_path):
    root, config = _repository(tmp_path)
    full, architecture = run_report(root, config=config, analyzer=observe, only_architecture=True)
    sliced, encoded = run_report(
        root, config=config, analyzer=observe, only_architecture=True, component="store"
    )
    assert encoded == architecture
    assert sliced.declared_rules == full.declared_rules == "FAIL"
    assert sliced.coverage == full.coverage
    assert sliced.rule_assessments == full.rule_assessments
    assert sliced.measurements == full.measurements
    assert sliced.architecture_projection.source == full.architecture_projection.source
    assert (
        sliced.architecture_projection.contract_digest
        == full.architecture_projection.contract_digest
    )
    assert sliced.architecture_projection.unknowns == full.architecture_projection.unknowns
    assert [item.id for item in sliced.architecture_projection.components] == ["STORE"]
    assert "Filtered (only architecture):" in report_summary(full).sentence
    assert "Filtered (only architecture, component store):" in report_summary(sliced).sentence


def test_deepest_ownership_and_repeated_nested_labels_are_scope_qualified(tmp_path):
    root, config = _nested_repository(tmp_path)
    result, _ = run_report(root, config=config, analyzer=observe, only_architecture=True)
    view = result.architecture_projection
    assert view is not None, result.diagnostics
    components = {item.id: item for item in view.components}
    assert components["core:service:core"].modules
    assert not components["ROOT"].modules
    assert not components["core:core"].modules
    selected, _ = run_report(
        root,
        config=config,
        analyzer=observe,
        only_architecture=True,
        component="core:service:operations",
    )
    assert [item.id for item in selected.architecture_projection.components] == [
        "core:service:core"
    ]
    leaf_path = root / "leaf.json"
    raw = json.loads(leaf_path.read_bytes())
    raw["components"].append({**raw["components"][0], "id": "tie", "label": "parallel"})
    for owner in raw["components"]:
        owner.pop("namespace", None)
    leaf_path.write_text(json.dumps(raw))
    tied, _ = run_report(root, config=config, analyzer=observe, only_architecture=True)
    gap = next(
        item for item in tied.architecture_projection.ownership_gaps if item.module == "sample.core"
    )
    assert gap.candidate_ids == ("core:service:core", "core:service:tie")
    assert not any(item.modules for item in tied.architecture_projection.components)
    assert gap.reason and tied.architecture_projection.status == "UNKNOWN"


def test_missing_target_and_partial_coverage_never_project_pass(tmp_path):
    root, config = _repository(tmp_path)
    _, encoded = run_report(root, config=config, analyzer=observe)
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    sections = tuple(
        replace(
            section,
            records=tuple(
                item
                for item in section.records
                if item.kind not in {"architecture_target", "uml_target"}
            ),
        )
        for section in model.sections
    )
    incomplete = replace(model, sections=sections)
    view = architecture_projection(
        incomplete, architecture_report(incomplete), (), violation_remedy="existing remedy"
    )
    assert not view.components and view.status == "UNKNOWN" and view.unknowns
    (root / "sample/broken.py").write_text("def broken(:\n")
    partial, _ = run_report(root, config=config, analyzer=observe, only_architecture=True)
    assert partial.exit_code == 2
    assert partial.architecture_projection is not None
    assert partial.architecture_projection.status == "UNKNOWN"
    assert all(item.status != "PASS" for item in partial.architecture_projection.components)
    assert partial.architecture_projection.levels[0].used is None


def test_two_same_commit_cli_results_are_identical_including_whole_envelope(tmp_path, capsys):
    root, _ = _repository(tmp_path)
    outputs = []
    for name in ("first", "second"):
        assert (
            main(
                [
                    "report",
                    "--root",
                    str(root),
                    "--only",
                    "architecture",
                    "--output",
                    str(tmp_path / f"{name}.json"),
                    "--json",
                ]
            )
            == 0
        )
        outputs.append(capsys.readouterr().out.encode())
    assert outputs[0] == outputs[1]
    assert len(outputs[0]) < 50_000


def test_unknown_architecture_component_is_a_named_diagnostic(tmp_path):
    root, config = _repository(tmp_path)
    result, _ = run_report(
        root, config=config, analyzer=observe, only_architecture=True, component="missing"
    )
    assert result.exit_code == 2 and result.diagnostics[0].kind == "filter_unknown"
    assert result.diagnostics[0].subject == "--component missing"


@pytest.mark.parametrize(
    "field,value",
    [
        ("source", "sample.store"),
        ("target", "sample.store"),
        ("rationale", "Forged reason."),
        ("decided_by", "agent"),
        ("include_type_checking", False),
    ],
)
def test_permission_metadata_cannot_disagree_with_authenticated_contract(tmp_path, field, value):
    root, config = _repository(tmp_path)

    def forged_analyzer(*args, **kwargs):
        original = observe(*args, **kwargs)
        model = original.observation
        sections = tuple(
            replace(
                section,
                records=tuple(
                    replace(
                        record,
                        data=replace(
                            record.data,
                            entries=tuple({**dict(record.data.entries), field: value}.items()),
                        ),
                    )
                    if record.id == "NO-OTHER"
                    else record
                    for record in section.records
                ),
            )
            for section in model.sections
        )
        return replace(original, observation=replace(model, sections=sections))

    result, _ = run_report(root, config=config, analyzer=forged_analyzer, only_architecture=True)
    assert result.exit_code == 2 and result.diagnostics
    assert (
        result.architecture_projection is None
        or not result.architecture_projection.permission_rules
    )


def test_partial_graph_import_coverage_has_no_zero_count_pass(tmp_path):
    root, config = _repository(tmp_path)
    result, encoded = run_report(root, config=config, analyzer=observe)
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    report = architecture_report(model)
    partial = replace(
        report,
        observed=replace(
            report.observed,
            coverage=tuple(
                item
                for item in report.observed.coverage
                if "imports" not in item.relationship_kinds
            ),
        ),
    )
    view = architecture_projection(
        model, partial, result.rule_assessments, violation_remedy="existing remedy"
    )
    assert view.status == "UNKNOWN"
    assert view.levels[0].used is None and view.levels[0].unused is None
    assert all(item.status != "PASS" for item in view.components)


def test_repeated_inner_labels_require_a_scope_or_stable_id(tmp_path):
    root, config = _repository(tmp_path)
    path = root / config.contract
    raw = json.loads(path.read_bytes())
    for component in raw["components"]:
        if component["label"] not in {"other", "store"}:
            continue
        inside = component["label"] + ".json"
        component["inside"] = inside
        child = {**component, "id": "SHARED", "label": "shared"}
        child.pop("inside")
        child["requires"] = []
        (root / inside).write_text(
            json.dumps(
                {
                    "schema_version": "2.1.0",
                    "components": [child],
                    "rules": [
                        {
                            "id": "INNER-COMPLETE",
                            "kind": "complete_requires",
                            "rationale": "No sibling crossing is permitted.",
                            "provenance": ["docs/target.md"],
                            "decided_by": "architect",
                        }
                    ],
                }
            )
        )
    path.write_text(json.dumps(raw))
    full, _ = run_report(root, config=config, analyzer=observe, only_architecture=True)
    assert full.architecture_projection is not None, full.diagnostics
    assert {
        item.id for item in full.architecture_projection.components if item.label == "shared"
    } == {"other:SHARED", "store:SHARED"}
    assert all(item.undecided == 0 for item in full.architecture_projection.levels)
    ambiguous, _ = run_report(
        root, config=config, analyzer=observe, only_architecture=True, component="shared"
    )
    assert ambiguous.exit_code == 2 and ambiguous.diagnostics[0].kind == "filter_unknown"
    focused, _ = run_report(
        root, config=config, analyzer=observe, only_architecture=True, component="store:shared"
    )
    assert [item.id for item in focused.architecture_projection.components] == ["store:SHARED"]
    assert focused.declared_rules == full.declared_rules


def test_required_target_relationships_are_distinct_from_permission_and_usage(tmp_path):
    root, config = _nested_repository(tmp_path)
    result, encoded = run_report(root, config=config, analyzer=observe, only_architecture=True)
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    report = architecture_report(model)
    expected = {item.id for item in report.target.relationships if item.kind != "requires"}
    relationships = result.architecture_projection.required_relationships
    assert relationships and {item.id for item in relationships} == expected
    assert all(item.kind != "requires" and item.reasons for item in relationships)
    unavailable = architecture_projection(
        model,
        replace(report, comparison=None),
        result.rule_assessments,
        violation_remedy="existing remedy",
    )
    assert all(item.status == "UNKNOWN" for item in unavailable.required_relationships)
    assert unavailable.unknowns and unavailable.status == "UNKNOWN"


@pytest.mark.parametrize("implemented", [False, True])
def test_native_parent_slice_retains_descendant_wiring_and_summaries(
    tmp_path, capsys, validator, implemented
):
    root, config = _nested_repository(tmp_path)
    (root / "archkeel.toml").write_text(
        '[scan]\nroots=["sample"]\nnamespace="sample"\ncontract="contract.json"\n'
    )
    for filename in ("inside.json", "leaf.json"):
        path = root / filename
        contract = json.loads(path.read_bytes())
        uml = contract["declarations"]["uml"]
        uml["entities"].append(
            {**uml["entities"][0], "id": "base", "qualified_name": "sample.core.Base"}
        )
        uml["relationships"].append(
            {
                "id": "base-inheritance",
                "kind": "inherits",
                "source_id": "service",
                "target_id": "base",
                "provenance": ["docs/target.md"],
            }
        )
        path.write_text(json.dumps(contract))
    path = root / config.contract
    outer = json.loads(path.read_bytes())
    outer["components"].append(
        {
            **outer["components"][0],
            "id": "PEER",
            "label": "peer",
            "packages": ["sample.peer"],
            "namespace": "sample.peer",
            "inside": "peer.json",
        }
    )
    path.write_text(json.dumps(outer))
    (root / "peer.json").write_text(
        (root / "leaf.json").read_text().replace("sample.core", "sample.peer")
    )
    native_source = (
        "from typing import Protocol\nclass Port(Protocol):\n"
        "    def run(self, request: str) -> str: ...\nclass Base: pass\n"
        "class Service" + ("(Port, Base)" if implemented else "") + ":\n"
        "    def run(self, request: str) -> str:\n        return request\n"
    )
    for module in ("core", "peer"):
        (root / "sample" / f"{module}.py").write_text(native_source)
    full, canonical = run_report(root, config=config, analyzer=observe, only_architecture=True)
    whole = json.loads(result_bytes(full))["architecture_projection"]
    whole_details = {row["id"]: row for row in whole["required_relationships"]}
    whole_summaries = {row["scope"]: row for row in whole["required_summaries"]}
    for selector, expected_details, expected_scopes in (
        (
            "ROOT",
            {"core:implementation", "core:service:implementation"},
            {"core:service", "core:service:operations"},
        ),
        (
            "core:service",
            {"core:implementation", "core:service:implementation"},
            {"core:service", "core:service:operations"},
        ),
        ("core:service:operations", {"core:service:implementation"}, {"core:service:operations"}),
    ):
        selected, encoded = run_report(
            root, config=config, analyzer=observe, only_architecture=True, component=selector
        )
        assert encoded == canonical
        assert (
            main(
                [
                    "report",
                    "--root",
                    str(root),
                    "--only",
                    "architecture",
                    "--component",
                    selector,
                    "--output",
                    str(tmp_path / "slice.json"),
                    "--json",
                ]
            )
            == 0
        )
        assert capsys.readouterr().out.encode() == result_bytes(selected)
        wire = json.loads(result_bytes(selected))
        view = wire["architecture_projection"]
        assert {row["id"] for row in view["required_relationships"]} == expected_details
        assert {row["scope"] for row in view["required_summaries"]} == expected_scopes
        for row in view["required_relationships"]:
            assert row == whole_details[row["id"]]
            assert row["status"] == ("PASS" if implemented else "FAIL")
        for row in view["required_summaries"]:
            assert row == whole_summaries[row["scope"]]
            assert row["count"] == 1 and row["kind"] == "inherits"
            assert row["status"] == ("PASS" if implemented else "FAIL")
        assert {row.id for row in selected.architecture_projection.required_relationships} == (
            expected_details
            | {
                "core:base-inheritance"
                if scope == "core:service"
                else "core:service:base-inheritance"
                for scope in expected_scopes
            }
        )
        context = {row["id"] for row in view["policy_context"]}
        assert "peer:core" not in context
        assert "PEER" in context
        if selector != "core:service:operations":
            assert "core:service:core" in context
        assert selected.architecture_projection.source == full.architecture_projection.source
        assert selected.architecture_projection.unknowns == full.architecture_projection.unknowns
        assert selected.declared_rules == full.declared_rules and selected.coverage == full.coverage
        assert view["unknowns"] == whole["unknowns"]
        assert not list(validator.iter_errors(wire))


def test_symbol_finding_is_attached_to_its_component_without_changing_id_or_location(tmp_path):
    root, config = _repository(tmp_path)
    path = root / config.contract
    raw = json.loads(path.read_bytes())
    raw["rules"].append(
        {
            "id": "NO-GETATTR",
            "kind": "forbidden_construct",
            "source": "sample.core",
            "constructs": ["getattr"],
            "rationale": "Keep runtime access explicit.",
            "provenance": ["docs/target.md"],
            "decided_by": "architect",
        }
    )
    path.write_text(json.dumps(raw))
    (root / "sample/core.py").write_text("def lookup(obj):\n    return getattr(obj, 'field')\n")
    result, _ = run_report(
        root, config=config, analyzer=observe, only_architecture=True, component="core"
    )
    violation = next(
        item for item in result.filtered_violations if item.record.rule_ids == ("NO-GETATTR",)
    )
    (component,) = result.architecture_projection.components
    assert component.status == "FAIL"
    assert violation.record.id in component.finding_ids
    assert [(item.path, item.line) for item in violation.locations] == [("sample/core.py", 2)]


def test_every_unknown_enters_one_exact_cause_and_scope_group(tmp_path):
    root, config = _repository(tmp_path, closed=False)
    result, _ = run_report(root, config=config, analyzer=observe, only_architecture=True)
    unknowns = result.architecture_projection.unknowns
    expected = Counter((row.kind, row.reason, row.scopes) for row in unknowns)
    groups = unknown_groups(unknowns)
    actual = {
        (kind, reason, scopes): count
        for kind, reasons in groups.items()
        for reason, counts in reasons.items()
        for scopes, count in counts
    }
    assert actual == expected
    assert sum(actual.values()) == len(unknowns)
    assert any("other" in scopes for _, _, scopes in actual)
    selected, _ = run_report(
        root, config=config, analyzer=observe, only_architecture=True, component="store"
    )
    assert architecture_command_envelope(selected).architecture_projection.unknowns == groups
    assert selected.declared_rules == result.declared_rules == "FAIL"


@pytest.mark.parametrize(
    "selector",
    ["sample.core", "sample.core.child", "sample.core:API", "sample.other", "sample.core_extra"],
)
def test_namespace_abbreviation_reconstructs_the_exact_identity(selector):
    prefix = "sample.core"
    short = short_selector(selector, prefix)
    restored = prefix + short if not short or short.startswith((".", ":")) else short
    assert restored == selector


def test_compact_required_relationships_restore_exact_ids_names_and_core_results(
    tmp_path, validator
):
    root, config = _nested_repository(tmp_path)
    result, _ = run_report(root, config=config, analyzer=observe, only_architecture=True)
    payload = json.loads(result_bytes(result))
    wire = payload["architecture_projection"]
    expected = {
        item.id: item
        for item in result.architecture_projection.required_relationships
        if item.internal_scope is None
    }
    restored = wire["required_relationships"]
    assert {item["id"] for item in restored} == set(expected) and restored
    for item in restored:
        original = expected[item["id"]]
        assert (
            item["kind"],
            item["source_id"],
            item["source"],
            item["target_id"],
            item["target"],
            item["status"],
            tuple(item["reasons"]),
        ) == (
            original.kind,
            original.source_id,
            original.source,
            original.target_id,
            original.target,
            original.status,
            original.reasons,
        )
    assert not list(validator.iter_errors(payload))


def test_compact_components_restore_api_modules_and_all_permission_deciders(tmp_path):
    root, config = _repository(tmp_path)
    contract_path = root / config.contract
    contract = json.loads(contract_path.read_bytes())
    contract["components"][0]["public"] = [
        "sample.core",
        "sample.core:API",
        "sample.core:Secondary",
        "sample.core.child:Nested",
    ]
    contract["components"][0]["planned"] = []
    contract_path.write_text(json.dumps(contract))
    result, _ = run_report(root, config=config, analyzer=observe, only_architecture=True)
    wire = json.loads(result_bytes(result))["architecture_projection"]
    canonical = {item.id: item for item in result.architecture_projection.components}
    for item in wire["components"]:
        original = canonical[item["id"]]
        prefix = item.get("selector_prefix", item.get("namespace"))

        def full_name(value, prefix=prefix):
            return (
                prefix + value
                if prefix is not None and (not value or value.startswith((".", ":")))
                else value
            )

        for key in ("public", "planned"):
            groups = item.get(key)
            restored = (
                None
                if groups is None
                else tuple(
                    full_name(module) + (":" + symbol if symbol else "")
                    for module, symbols in groups.items()
                    for symbol in symbols
                )
            )
            expected = original.public if key == "public" else original.planned
            assert (None if restored is None else tuple(sorted(restored))) == expected
        assert {
            full_name(name): None
            if path is None
            else item["path"]
            if not path
            else item["path"] + "/" + path
            for name, path in item.get("modules", {}).items()
        } == {module.name: module.path for module in original.modules}
        restored_permissions = {}
        for permission in item.get("permissions", []):
            for target in permission["target_ids"]:
                identifiers = permission.get("rule_ids", []) + [
                    requirement["id"]
                    for requirement in item.get("requires", [])
                    if permission["status"] == "allowed" and requirement["target_id"] == target
                ]
                restored_permissions[target] = (
                    permission["status"],
                    tuple(sorted(identifiers)),
                    wire["reasons"][permission["reason"]],
                )
        assert restored_permissions == {
            row.target_id: (row.status, row.rule_ids, row.reason) for row in original.permissions
        }


def _target_boundary_repository(tmp_path):
    root, config = _repository(tmp_path)
    path = root / config.contract
    contract = json.loads(path.read_bytes())
    contract["schema_version"] = "2.2.0"
    entities = [
        ("CLASS-A", "class", "sample.core.A", "CORE"),
        ("CLASS-B", "class", "sample.core.B", "CORE"),
        ("METHOD-A", "method", "sample.core.A.run", "CLASS-A"),
        ("METHOD-B", "method", "sample.core.B.run", "CLASS-B"),
        ("PORT", "interface", "sample.core.Port", "CORE"),
        ("PORT-METHOD", "method", "sample.core.Port.send", "PORT"),
        ("PEER", "class", "sample.store.Peer", "STORE"),
        ("OUTSIDE", "class", "sample.unowned.External", None),
    ]
    edges = [
        ("INTERNAL-TYPE", "references", "CLASS-A", "CLASS-B"),
        ("INTERNAL-METHOD", "calls", "METHOD-A", "METHOD-B"),
        ("PORT-REQUIRED", "realizes", "CLASS-A", "PORT"),
        ("PORT-METHOD-REQUIRED", "calls", "METHOD-A", "PORT-METHOD"),
        ("CROSS-REQUIRED", "references", "CLASS-A", "PEER"),
        ("COMPONENT-REQUIRED", "references", "CORE", "STORE"),
        ("UNOWNED-REQUIRED", "references", "CLASS-A", "OUTSIDE"),
        ("PUBLISHED-REQUIRED", "publishes", "CLASS-A", "CLASS-B"),
    ]
    contract["declarations"] = {
        "uml": {
            "schema_version": "1.0.0",
            "entities": [
                {
                    "id": identity,
                    "kind": kind,
                    "qualified_name": name,
                    "language": "python",
                    "parent_id": parent,
                    "presence": "planned",
                    "responsibilities": ["Own this declared Target fact."],
                    "provenance": ["docs/target.md"],
                }
                for identity, kind, name, parent in entities
            ],
            "relationships": [
                {
                    "id": identity,
                    "kind": kind,
                    "source_id": source,
                    "target_id": target,
                    "provenance": ["docs/target.md"],
                }
                for identity, kind, source, target in edges
            ],
        }
    }
    path.write_text(json.dumps(contract))
    return root, config


def test_required_partition_keeps_ports_cross_scope_components_and_unowned_details(tmp_path):
    root, config = _target_boundary_repository(tmp_path)
    result, _ = run_report(root, config=config, analyzer=observe, only_architecture=True)
    assert result.architecture_projection is not None, result.diagnostics
    view = result.architecture_projection
    assert {row.id for row in view.required_relationships if row.internal_scope is not None} == {
        "INTERNAL-TYPE",
        "INTERNAL-METHOD",
    }
    envelope = architecture_command_envelope(result).architecture_projection
    assert {row.id for row in envelope.required_relationships} == {
        "PORT-REQUIRED",
        "PORT-METHOD-REQUIRED",
        "CROSS-REQUIRED",
        "COMPONENT-REQUIRED",
        "UNOWNED-REQUIRED",
        "PUBLISHED-REQUIRED",
    }
    expected = Counter(
        (row.internal_scope, row.kind, row.status, row.reasons)
        for row in view.required_relationships
        if row.internal_scope is not None
    )
    assert {
        (row.scope, row.kind, row.status, row.reasons): row.count
        for row in envelope.required_summaries
    } == expected
    assert len(envelope.required_relationships) + sum(
        row.count for row in envelope.required_summaries
    ) == len(view.required_relationships)
    assert all(row.scope == "core" for row in envelope.required_summaries)
    peer, _ = run_report(
        root, config=config, analyzer=observe, only_architecture=True, component="store"
    )
    peer_wire = architecture_command_envelope(peer).architecture_projection
    assert {row.id for row in peer_wire.required_relationships} == {
        "CROSS-REQUIRED",
        "COMPONENT-REQUIRED",
    }
    assert not peer_wire.required_summaries
    assert peer_wire.unknowns == envelope.unknowns and peer.coverage == result.coverage


@pytest.mark.parametrize("role", ["interface", "contract"])
def test_interface_and_contract_component_roles_never_hide_required_details(tmp_path, role):
    root, config = _target_boundary_repository(tmp_path)
    path = root / config.contract
    contract = json.loads(path.read_bytes())
    contract["components"][0]["role"] = role
    path.write_text(json.dumps(contract))
    result, _ = run_report(root, config=config, analyzer=observe, only_architecture=True)
    assert result.architecture_projection is not None, result.diagnostics
    wire = architecture_command_envelope(result).architecture_projection
    assert not wire.required_summaries
    assert (
        len(wire.required_relationships)
        == len(result.architecture_projection.required_relationships)
        == 8
    )


def test_required_summaries_preserve_missing_core_evidence_reasons_and_counts(tmp_path):
    root, config = _target_boundary_repository(tmp_path)
    result, encoded = run_report(root, config=config, analyzer=observe, only_architecture=True)
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    report = replace(architecture_report(model), comparison=None)
    projection = architecture_projection(
        model, report, result.rule_assessments, violation_remedy="existing remedy"
    )
    unavailable = replace(result, architecture_projection=projection)
    wire = architecture_command_envelope(unavailable).architecture_projection
    assert len(wire.required_relationships) == 6
    assert sum(row.count for row in wire.required_summaries) == 2
    assert all(row.status == "UNKNOWN" for row in wire.required_summaries)
    assert all(
        row.reasons == ("No authenticated Core assessment exists for this required relationship.",)
        for row in wire.required_summaries
    )
    assert sum(
        count
        for reasons in wire.unknowns.values()
        for rows in reasons.values()
        for scopes, count in rows
    ) == len(projection.unknowns)


def test_native_allowed_declaration_cannot_bypass_complete_requires(tmp_path, capsys):
    root, config = _repository(tmp_path)
    path = root / config.contract
    contract = json.loads(path.read_bytes())
    contract["components"][0]["requires"] = []
    contract["rules"].append(
        {
            "id": "ALLOW-STORE",
            "kind": "allowed_dependency",
            "source": "sample.core",
            "target": "sample.store",
            "rationale": "Store use is declared permitted.",
            "provenance": ["docs/target.md"],
            "decided_by": "architect",
        }
    )
    path.write_text(json.dumps(contract))
    assert (
        main(
            [
                "report",
                "--root",
                str(root),
                "--only",
                "architecture",
                "--output",
                str(tmp_path / "out.json"),
                "--json",
            ]
        )
        == 0
    )
    wire = json.loads(capsys.readouterr().out)
    projection = wire["architecture_projection"]
    core = next(row for row in projection["components"] if row["id"] == "CORE")
    permission = next(row for row in core["permissions"] if "STORE" in row["target_ids"])
    assert permission["status"] == "forbidden"
    assert set(permission["rule_ids"]) == {"COMPLETE", "ALLOW-STORE"}
    assert {row["declaration"]["id"] for row in projection["permission_rules"]} >= {
        "COMPLETE",
        "ALLOW-STORE",
    }
    assert any(
        "COMPLETE" in row["rule_ids"] and row["data"]["target_module"] == "sample.store"
        for row in wire["filtered_violations"]
    )
    assert wire["declared_rules"] == "FAIL"


@pytest.mark.parametrize("observed_violation", [False, True])
def test_native_nested_slice_retains_governing_ancestor_policy_without_findings(
    tmp_path, observed_violation, validator
):
    root, config = _repository(tmp_path)
    path = root / config.contract
    contract = json.loads(path.read_bytes())
    child = {**contract["components"][0], "id": "CHILD", "label": "child", "requires": []}
    child.pop("namespace")
    contract["components"][0]["inside"] = "inside.json"
    (root / "inside.json").write_text(
        json.dumps({"schema_version": "2.1.0", "components": [child], "rules": []})
    )
    path.write_text(json.dumps(contract))
    if not observed_violation:
        (root / "sample/core.py").write_text("import sample.store\n")
    full, _ = run_report(root, config=config, analyzer=observe, only_architecture=True)
    selected, _ = run_report(
        root, config=config, analyzer=observe, only_architecture=True, component="core:child"
    )
    wire = json.loads(result_bytes(selected))
    view = wire["architecture_projection"]
    assert {row["declaration"]["id"] for row in view["permission_rules"]} >= {
        "NO-OTHER",
        "COMPLETE",
    }
    assert {row["parent_id"] for row in view["levels"]} == {None, "CORE"}
    context = {row["id"]: row for row in view["policy_context"]}
    assert context["CORE"]["scope"] == "core"
    assert context["CORE"]["packages"] == ["sample.core"]
    assert context["OTHER"]["scope"] == "other" and context["OTHER"]["packages"] == ["sample.other"]
    ancestor_permissions = {
        target: row["status"]
        for row in context["CORE"]["permissions"]
        for target in row["target_ids"]
    }
    assert ancestor_permissions["OTHER"] == "forbidden"
    assert ancestor_permissions["STORE"] == "allowed"
    assert bool(wire["filtered_violations"]) is observed_violation
    assert selected.declared_rules == full.declared_rules
    assert view["unknowns"] == json.loads(result_bytes(full))["architecture_projection"]["unknowns"]
    assert selected.coverage == full.coverage
    assert not list(validator.iter_errors(wire))


@pytest.mark.parametrize("type_only", [False, True])
def test_native_parent_slice_retains_descendant_policy_and_endpoint_context(
    tmp_path, capsys, validator, type_only
):
    root, config = _repository(tmp_path)
    path = root / config.contract
    contract = json.loads(path.read_bytes())
    contract["components"][0]["inside"] = "core.json"
    contract["components"][1]["inside"] = "store.json"
    (root / "sample/core.py").unlink()
    (root / "sample/core").mkdir()
    (root / "sample/core/__init__.py").write_text("")
    (root / "sample/core/right.py").write_text("")
    (root / "sample/core/left.py").write_text(
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import sample.core.right\n"
        if type_only
        else "import sample.core.right\n"
    )
    children = [
        {
            **contract["components"][0],
            "id": label.upper(),
            "label": label,
            "packages": [f"sample.core.{label}"],
            "namespace": f"sample.core.{label}",
            "public": [f"sample.core.{label}"],
            "planned": [f"sample.core.{label}:Future"],
            "requires": [],
        }
        for label in ("left", "right")
    ]
    for child in children:
        child.pop("inside")
    children[0]["requires"] = [{"component": "right", "rationale": "Reach the published boundary."}]
    children[0]["inside"] = "left.json"
    complete = contract["rules"][-1]
    (root / "core.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": children,
                "rules": [
                    complete,
                    {
                        **complete,
                        "id": "RESTRICT",
                        "kind": "sibling_isolation",
                        "members": ["sample.core.left", "sample.core.right"],
                        "include_type_checking": False,
                    },
                ],
            }
        )
    )
    for owner, filename in ((children[0], "left.json"), (contract["components"][1], "store.json")):
        leaf = {**owner, "id": "LEAF", "label": "leaf", "requires": []}
        leaf.pop("inside")
        (root / filename).write_text(
            json.dumps({"schema_version": "2.1.0", "components": [leaf], "rules": [complete]})
        )
    path.write_text(json.dumps(contract))
    full, canonical = run_report(root, config=config, analyzer=observe, only_architecture=True)
    selected, encoded = run_report(
        root, config=config, analyzer=observe, only_architecture=True, component="core"
    )
    assert encoded == canonical
    command = [
        "report",
        "--root",
        str(root),
        "--only",
        "architecture",
        "--component",
        "core",
        "--output",
        str(tmp_path / "slice.json"),
        "--json",
    ]
    for _ in range(2):
        assert main(command) == 0
        assert capsys.readouterr().out.encode() == result_bytes(selected)
    wire = json.loads(result_bytes(selected))
    view = wire["architecture_projection"]
    policies = {row["declaration"]["id"]: row for row in view["permission_rules"]}
    assert set(policies) == {
        "COMPLETE",
        "NO-OTHER",
        "core:COMPLETE",
        "core:RESTRICT",
        "core:left:COMPLETE",
    }
    assert {row["parent_id"] for row in view["levels"]} == {None, "CORE", "core:LEFT"}
    context = {row["id"]: row for row in view["policy_context"]}
    assert {"core:LEFT", "core:RIGHT", "core:left:LEAF"} <= context.keys()
    assert "store:LEAF" not in context
    assert context["core:RIGHT"]["packages"] == ["sample.core.right"]
    assert context["core:RIGHT"]["public"] == ["sample.core.right"]
    assert context["core:RIGHT"]["planned"] == ["sample.core.right:Future"]
    assert context["core:LEFT"]["requires"][0]["target_id"] == "core:RIGHT"
    model = parse_observation(decode_canonical_model(json.loads(canonical)))
    declarations = {row.id: row for row in model.records("declarations")}
    assessments = {row.id: row for row in full.rule_assessments}
    for identity, row in policies.items():
        assert parse_record(row["declaration"]) == declarations[identity]
        assert row["assessment"] == json.loads(json.dumps(asdict(assessments[identity])))
    assert policies["core:RESTRICT"]["assessment"]["status"] == ("PASS" if type_only else "FAIL")
    assert policies["core:RESTRICT"]["declaration"]["data"]["include_type_checking"] is False
    assert bool(wire["filtered_violations"]) is not type_only
    assert selected.declared_rules == full.declared_rules
    assert selected.coverage == full.coverage
    assert selected.architecture_projection.source == full.architecture_projection.source
    assert selected.architecture_projection.unknowns == full.architecture_projection.unknowns
    assert view["unknowns"] == json.loads(result_bytes(full))["architecture_projection"]["unknowns"]
    assert not list(validator.iter_errors(wire))


def test_native_id_scope_collision_is_diagnosed_instead_of_selecting_first(tmp_path, capsys):
    root, config = _repository(tmp_path)
    path = root / config.contract
    contract = json.loads(path.read_bytes())
    contract["components"][1]["id"] = "core"
    path.write_text(json.dumps(contract))
    assert (
        main(
            [
                "report",
                "--root",
                str(root),
                "--only",
                "architecture",
                "--component",
                "core",
                "--output",
                str(tmp_path / "out.json"),
                "--json",
            ]
        )
        == 2
    )
    wire = json.loads(capsys.readouterr().out)
    assert wire["diagnostics"][0]["kind"] == "filter_unknown"
    selected, _ = run_report(
        root, config=config, analyzer=observe, only_architecture=True, component="store"
    )
    assert [row.id for row in selected.architecture_projection.components] == ["core"]


def test_native_allow_without_complete_constraint_retains_the_positive_decision(tmp_path):
    root, config = _repository(tmp_path, closed=False)
    path = root / config.contract
    contract = json.loads(path.read_bytes())
    contract["components"][0]["requires"] = []
    contract["rules"].append(
        {
            "id": "ALLOW-STORE",
            "kind": "allowed_dependency",
            "source": "sample.core",
            "target": "sample.store",
            "rationale": "Store use is permitted.",
            "provenance": ["docs/target.md"],
            "decided_by": "architect",
        }
    )
    path.write_text(json.dumps(contract))
    result, _ = run_report(root, config=config, analyzer=observe, only_architecture=True)
    core = next(row for row in result.architecture_projection.components if row.id == "CORE")
    permission = next(row for row in core.permissions if row.target_id == "STORE")
    assert permission.status == "allowed" and permission.rule_ids == ("ALLOW-STORE",)
    assert not any(row.record.kind == "complete_requires" for row in result.filtered_violations)


def test_native_forbidden_requires_pair_keeps_all_declarations_and_requirement_ids(tmp_path):
    root, config = _repository(tmp_path)
    path = root / config.contract
    contract = json.loads(path.read_bytes())
    for kind, identity in [
        ("forbidden_dependency", "NO-STORE"),
        ("allowed_dependency", "ALLOW-STORE"),
    ]:
        contract["rules"].append(
            {
                "id": identity,
                "kind": kind,
                "source": "sample.core",
                "target": "sample.store",
                **({"include_type_checking": True} if kind == "forbidden_dependency" else {}),
                "rationale": "Retain each independent constraint.",
                "provenance": ["docs/target.md"],
                "decided_by": "architect",
            }
        )
    path.write_text(json.dumps(contract))
    result, _ = run_report(root, config=config, analyzer=observe, only_architecture=True)
    wire = json.loads(result_bytes(result))["architecture_projection"]
    core = next(row for row in wire["components"] if row["id"] == "CORE")
    permission = next(row for row in core["permissions"] if "STORE" in row["target_ids"])
    requirement_id = core["requires"][0]["id"]
    assert permission["status"] == "forbidden"
    assert set(permission["rule_ids"]) == {"NO-STORE", "ALLOW-STORE", "COMPLETE", requirement_id}
    assert any("NO-STORE" in row.record.rule_ids for row in result.filtered_violations)
    assert not any(
        row.record.kind == "complete_requires"
        and row.record.data.get("target_module") == "sample.store"
        for row in result.filtered_violations
    )


def test_native_core_through_enforcement_uses_the_shared_predicate(tmp_path):
    from archkeel.check.evaluation.rules import _requires_covers
    from archkeel.ir.model import requires_covers

    assert _requires_covers is requires_covers
    root, config = _repository(tmp_path)
    (root / "sample/store.py").unlink()
    (root / "sample/store").mkdir()
    for name in ("__init__", "allowed", "other"):
        (root / f"sample/store/{name}.py").write_text("")
    (root / "sample/core.py").write_text("import sample.store.allowed\nimport sample.store.other\n")
    path = root / config.contract
    contract = json.loads(path.read_bytes())
    contract["components"][0]["requires"][0]["through"] = ["sample.store.allowed"]
    path.write_text(json.dumps(contract))
    result, _ = run_report(root, config=config, analyzer=observe, only_architecture=True)
    complete_findings = [
        row.record for row in result.filtered_violations if row.record.kind == "complete_requires"
    ]
    assert [row.data.get("target_module") for row in complete_findings] == ["sample.store.other"]
    core = next(row for row in result.architecture_projection.components if row.id == "CORE")
    assert core.requires[0].through == ("sample.store.allowed",)


def test_native_stable_id_and_nested_label_collision_is_diagnosed(tmp_path):
    root, config = _repository(tmp_path)
    path = root / config.contract
    contract = json.loads(path.read_bytes())
    child = {**contract["components"][0], "id": "CHILD", "label": "CORE", "requires": []}
    child.pop("namespace")
    contract["components"][0]["inside"] = "inside.json"
    (root / "inside.json").write_text(
        json.dumps({"schema_version": "2.1.0", "components": [child], "rules": []})
    )
    path.write_text(json.dumps(contract))
    collision, _ = run_report(
        root, config=config, analyzer=observe, only_architecture=True, component="CORE"
    )
    assert collision.exit_code == 2 and collision.diagnostics[0].kind == "filter_unknown"
    selected, _ = run_report(
        root, config=config, analyzer=observe, only_architecture=True, component="core:CORE"
    )
    assert [row.id for row in selected.architecture_projection.components] == ["core:CHILD"]


_POLICY_KINDS = (
    "sibling_isolation",
    "interface_boundary",
    "external_dependency_scope",
    "complete_external_scope",
    "no_component_cycles",
)


def _policy_repository(tmp_path, kind, *, include_type_checking=True):
    root, config = _repository(tmp_path)
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_bytes())
    rule = {
        "id": "RESTRICT",
        "kind": kind,
        "rationale": "Preserve the explicitly governed boundary.",
        "provenance": ["docs/target.md"],
        "decided_by": "architect",
    }
    target = "sample.store"
    if kind == "sibling_isolation":
        rule.update(
            members=["sample.core", "sample.store"], include_type_checking=include_type_checking
        )
    elif kind == "interface_boundary":
        (root / "sample/store.py").unlink()
        (root / "sample/store").mkdir()
        for name in ("__init__", "public", "private"):
            (root / "sample/store" / f"{name}.py").write_text("")
        contract["components"][1]["public"] = ["sample.store.public"]
        contract["components"][1]["planned"] = ["sample.store.future"]
        rule["include_type_checking"] = include_type_checking
        target = "sample.store.private"
    elif kind == "external_dependency_scope":
        (root / "sample/store.py").unlink()
        (root / "sample/store").mkdir()
        for name in ("__init__", "allowed", "denied"):
            (root / "sample/store" / f"{name}.py").write_text("")
        rule.update(
            dependency="sqlite3",
            allowed_sources=["sample.store.allowed"],
            exact_sources=["sample.store"],
        )
        target = "sqlite3"
    elif kind == "complete_external_scope":
        rule["source"] = "sample.core"
        contract["rules"].append(
            {
                "id": "EXTERNAL",
                "kind": "external_dependency_scope",
                "dependency": "sqlite3",
                "allowed_sources": ["sample.store"],
                "exact_sources": ["sample.core"],
                "rationale": "Use a declared database driver.",
                "provenance": ["docs/target.md"],
                "decided_by": "architect",
            }
        )
        target = "requests"
    elif kind == "no_component_cycles":
        rule["components"] = ["core"]
        contract["components"][1]["requires"] = [
            {
                "component": "core",
                "rationale": "Call the explicit core boundary.",
            }
        ]
        (root / "sample/store.py").write_text("import sample.core\n")
    contract["rules"].append(rule)
    path.write_text(json.dumps(contract))
    (root / "sample/core.py").write_text("")
    return root, config, target


def _policy_row(view, identity="RESTRICT"):
    return next(item for item in view["permission_rules"] if item["declaration"]["id"] == identity)


@pytest.mark.parametrize("kind", _POLICY_KINDS)
@pytest.mark.parametrize("nested", [False, True])
def test_native_governing_policy_survives_before_and_after_violation(
    tmp_path, capsys, validator, kind, nested
):
    root, config, target = _policy_repository(tmp_path, kind)
    selector = "core"
    if nested:
        path = root / "architecture-contract.json"
        contract = json.loads(path.read_bytes())
        child = {**contract["components"][0], "id": "CHILD", "label": "child", "requires": []}
        child.pop("namespace")
        contract["components"][0]["inside"] = "inside.json"
        (root / "inside.json").write_text(
            json.dumps(
                {
                    "schema_version": "2.1.0",
                    "components": [child],
                    "rules": [],
                }
            )
        )
        path.write_text(json.dumps(contract))
        selector = "core:child"
    for violated in (False, True):
        if violated:
            (root / "sample/core.py").write_text(f"import {target}\n")
        full, canonical = run_report(root, config=config, analyzer=observe, only_architecture=True)
        assert (
            main(
                [
                    "report",
                    "--root",
                    str(root),
                    "--only",
                    "architecture",
                    "--component",
                    selector,
                    "--output",
                    str(tmp_path / "slice.json"),
                    "--json",
                ]
            )
            == 0
        )
        wire = json.loads(capsys.readouterr().out)
        view = wire["architecture_projection"]
        model = parse_observation(decode_canonical_model(json.loads(canonical)))
        declaration = next(item for item in model.records("declarations") if item.id == "RESTRICT")
        native = next(item for item in full.rule_assessments if item.id == "RESTRICT")
        assert "RESTRICT" in {
            item["declaration"]["id"] if "declaration" in item else item["id"]
            for item in view["permission_rules"]
        }
        row = _policy_row(view)
        assert parse_record(row["declaration"]) == declaration
        assert row["declaration"]["kind"] == declaration.kind == kind
        assert row["declaration"]["subjects"] == list(declaration.subjects)
        assert row["declaration"]["data"]["rationale"] == declaration.data.get("rationale")
        assert row["assessment"]["status"] == native.status == ("FAIL" if violated else "PASS")
        assert row["assessment"]["count"] == native.count == int(violated)
        assert row["assessment"]["evaluation_proven"] == native.evaluation_proven
        assert row["assessment"]["reason"] == native.reason
        rebuilt = architecture_projection(
            model,
            architecture_report(model),
            full.rule_assessments,
            violation_remedy=full.architecture_projection.violation_remedy,
        )
        assert rebuilt == full.architecture_projection
        whole = json.loads(result_bytes(full))
        assert wire["declared_rules"] == whole["declared_rules"]
        assert wire["coverage"] == whole["coverage"]
        assert view["unknowns"] == whole["architecture_projection"]["unknowns"]
        assert view["source"] == whole["architecture_projection"]["source"]
        assert _policy_row(whole["architecture_projection"]) == row
        core = next(
            item for item in (*view["components"], *view["policy_context"]) if item["id"] == "CORE"
        )
        permission = next(item for item in core["permissions"] if "STORE" in item["target_ids"])
        assert permission["status"] == "allowed"
        assert "Declared component permission" in view["reasons"][permission["reason"]]
        assert "all governing rules" in view["reasons"][permission["reason"]]
        if kind == "sibling_isolation":
            assert row["declaration"]["subjects"] == ["sample.core", "sample.store"]
            assert row["declaration"]["data"]["include_type_checking"] is True
        elif kind == "interface_boundary":
            store = next(item for item in view["policy_context"] if item["id"] == "STORE")
            assert store["public"] == ["sample.store.public"]
            assert store["planned"] == ["sample.store.future"]
        elif kind == "external_dependency_scope":
            assert row["declaration"]["data"]["dependency"] == "sqlite3"
            assert row["declaration"]["data"]["allowed_sources"] == ["sample.store.allowed"]
            assert row["declaration"]["data"]["exact_sources"] == ["sample.store"]
        elif kind == "complete_external_scope":
            external = _policy_row(view, "EXTERNAL")["declaration"]["data"]
            assert external["dependency"] == "sqlite3"
            assert external["allowed_sources"] == ["sample.store"]
            assert external["exact_sources"] == ["sample.core"]
        elif kind == "no_component_cycles":
            assert row["declaration"]["data"]["components"] == ["core"]
            assert row["assessment"]["scope"] == native.scope
        assert not list(validator.iter_errors(wire))


@pytest.mark.parametrize("kind", ["sibling_isolation", "interface_boundary"])
@pytest.mark.parametrize("include_type_checking", [False, True])
def test_native_policy_type_checking_exception_is_exact(tmp_path, kind, include_type_checking):
    root, config, target = _policy_repository(
        tmp_path, kind, include_type_checking=include_type_checking
    )
    (root / "sample/core.py").write_text(
        f"from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import {target}\n"
    )
    result, _ = run_report(
        root, config=config, analyzer=observe, only_architecture=True, component="core"
    )
    row = _policy_row(json.loads(result_bytes(result))["architecture_projection"])
    assert row["declaration"]["data"]["include_type_checking"] is include_type_checking
    assert row["assessment"]["count"] == int(include_type_checking)
    assert row["assessment"]["status"] == ("FAIL" if include_type_checking else "PASS")


def test_native_external_scope_prefix_and_exact_exceptions_retain_their_boundary(tmp_path):
    root, config, _ = _policy_repository(tmp_path, "external_dependency_scope")
    for name in ("__init__", "allowed", "denied"):
        (root / "sample/store" / f"{name}.py").write_text("import sqlite3\n")
    result, _ = run_report(
        root, config=config, analyzer=observe, only_architecture=True, component="core"
    )
    row = _policy_row(json.loads(result_bytes(result))["architecture_projection"])
    assert row["assessment"]["count"] == 1
    assert row["declaration"]["data"]["allowed_sources"] == ["sample.store.allowed"]
    assert row["declaration"]["data"]["exact_sources"] == ["sample.store"]
    assert not result.filtered_violations
    full, _ = run_report(root, config=config, analyzer=observe, only_architecture=True)
    assert result.declared_rules == full.declared_rules == "FAIL"
    assert result.coverage == full.coverage
    assert result.architecture_projection.unknowns == full.architecture_projection.unknowns
    violation = next(
        item for item in full.filtered_violations if "RESTRICT" in item.record.rule_ids
    )
    assert violation.record.data.get("source_module") == "sample.store.denied"


def test_native_module_cycle_selector_and_core_assessment_are_retained(tmp_path):
    root, config, _ = _policy_repository(tmp_path, "no_component_cycles")
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_bytes())
    contract["rules"][-1]["level"] = "module"
    path.write_text(json.dumps(contract))
    (root / "sample/core.py").write_text("import sample.store\n")
    result, _ = run_report(
        root, config=config, analyzer=observe, only_architecture=True, component="core"
    )
    row = _policy_row(json.loads(result_bytes(result))["architecture_projection"])
    assert row["declaration"]["data"]["level"] == "module"
    assert row["declaration"]["data"]["components"] == ["core"]
    native = next(item for item in result.rule_assessments if item.id == "RESTRICT")
    assert row["assessment"]["status"] == native.status == "FAIL"
    assert row["assessment"]["count"] == native.count == 1


@pytest.mark.parametrize("kind", _POLICY_KINDS)
def test_native_governing_policy_forged_metadata_is_rejected(tmp_path, kind):
    root, config, _ = _policy_repository(tmp_path, kind)

    def forged_analyzer(*args, **kwargs):
        result = observe(*args, **kwargs)
        sections = tuple(
            replace(
                section,
                records=tuple(
                    replace(record, subjects=("forged.selector",))
                    if record.id == "RESTRICT"
                    else record
                    for record in section.records
                ),
            )
            for section in result.observation.sections
        )
        return replace(result, observation=replace(result.observation, sections=sections))

    result, _ = run_report(root, config=config, analyzer=forged_analyzer, only_architecture=True)
    assert result.exit_code == 2 and result.diagnostics
    assert (
        result.architecture_projection is None
        or not result.architecture_projection.permission_rules
    )


def test_native_projection_uses_the_complete_core_declaration_catalogue(tmp_path):
    from archkeel.ir.model import RULE_KINDS

    root, config = _repository(tmp_path)
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_bytes())
    contract["rules"].append(
        {
            "id": "OWNERSHIP",
            "kind": "complete_assignment",
            "source": "sample",
            "rationale": "Keep ownership decisions explicit.",
            "provenance": ["docs/target.md"],
            "decided_by": "architect",
        }
    )
    path.write_text(json.dumps(contract))
    result, canonical = run_report(root, config=config, analyzer=observe, only_architecture=True)
    model = parse_observation(decode_canonical_model(json.loads(canonical)))
    declarations = tuple(
        sorted(
            (item for item in model.records("declarations") if item.kind in RULE_KINDS),
            key=lambda item: item.id,
        )
    )
    rows = result.architecture_projection.permission_rules
    assert tuple(item.declaration for item in rows) == declarations
    assert tuple(item.assessment for item in rows) == tuple(
        next(
            assessment for assessment in result.rule_assessments if assessment.id == declaration.id
        )
        for declaration in declarations
    )
    projection = architecture_projection(
        model, architecture_report(model), (), violation_remedy="existing remedy"
    )
    assert tuple(item.declaration for item in projection.permission_rules) == declarations
    assert all(item.assessment is None for item in projection.permission_rules)

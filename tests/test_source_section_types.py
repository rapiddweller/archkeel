# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Owned source sections stay nominal through Core without closing observation metadata."""

import ast
import copy
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import get_type_hints

import pytest
from test_architecture_demo import _prepare_repo
from test_source_evaluation import _facts
from test_uml_evaluation import _model

from archkeel.check.evaluation.evaluate import ScanResult, evaluate_source
from archkeel.check.ports import ScanConfig
from archkeel.ir import facts_validation
from archkeel.ir.codec import parse_contract
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.facts import SourceSectionName
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.source_graph import _section_coverage
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
GUARD = "PROFILE-SECTION-CONTROL"
PORTS = {
    "PROFILE-SECTIONS-ScanResult.observed_sections",
    "PROFILE-SECTIONS-source-record",
    "PROFILE-SECTIONS-base-declarations",
    "PROFILE-SECTIONS-section-coverage",
}


def _scan():
    return evaluate_source(
        _facts(),
        parse_contract({"schema_version": "2.1.0", "components": [], "rules": []}),
        roots=("src",),
        namespace="project",
    )


def test_scan_result_keeps_actual_producer_section_type():
    scan = _scan()
    assert scan.observed_sections
    assert all(isinstance(section, SourceSectionName) for section in scan.observed_sections)
    assert get_type_hints(ScanResult)["observed_sections"] == frozenset[SourceSectionName]


def test_legacy_scan_result_section_strings_normalize_at_constructor():
    scan = replace(
        _scan(), observed_sections=frozenset(section.value for section in SourceSectionName)
    )
    assert scan.observed_sections == frozenset(SourceSectionName)
    assert all(isinstance(section, SourceSectionName) for section in scan.observed_sections)
    assert replace(scan, observed_sections=frozenset()).observed_sections == frozenset()


@pytest.mark.parametrize("invalid", ["future_section", "modules", "archkeel-python-analyzer"])
def test_scan_result_rejects_unsupported_source_sections(invalid):
    with pytest.raises(ValueError):
        replace(_scan(), observed_sections=frozenset({invalid}))


def test_section_helpers_keep_the_existing_enum_port():
    for operation in (
        facts_validation._source_record,
        facts_validation._base_declarations,
        _section_coverage,
    ):
        assert get_type_hints(operation)["section"] is SourceSectionName


def test_source_record_target_signature_includes_guard_proof_context():
    ir = json.loads((ROOT / "docs/architecture/contracts/ir.json").read_text())
    target = next(
        entity
        for entity in ir["declarations"]["uml"]["entities"]
        if entity["id"] == "PROFILE-SECTIONS-source-record"
    )
    expected = target["signature"]["parameters"]
    tree = ast.parse(Path(facts_validation.__file__).read_text())
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_source_record"
    )
    actual = [*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs]
    actual_defaults = [None] * (len(actual) - len(function.args.defaults)) + [
        ast.unparse(default) for default in function.args.defaults
    ]

    assert [item["name"] for item in expected] == [parameter.arg for parameter in actual]
    assert [item["annotation"] for item in expected] == [
        ast.unparse(parameter.annotation) for parameter in actual
    ]
    assert [item.get("default") for item in expected] == actual_defaults


def _authored_target(*, include_guard=True):
    ir = json.loads((ROOT / "docs/architecture/contracts/ir.json").read_text())
    check = json.loads((ROOT / "docs/architecture/contracts/check.json").read_text())
    target = copy.deepcopy(ir)
    target.pop("$schema", None)
    target["components"].extend(check["components"])
    target["declarations"]["modules"] = []
    wanted = PORTS | {
        "archkeel.ir.facts",
        "IR-COLLECTOR-facts.SourceSectionName",
        "IR-UML-source_graph",
        "PROFILE-SECTIONS-validation",
        "PROFILE-SECTIONS-evaluate",
        "PROFILE-SECTIONS-ScanResult",
    }
    entities = [*ir["declarations"]["uml"]["entities"], *check["declarations"]["uml"]["entities"]]
    target["declarations"]["uml"].update(
        entities=[entity for entity in entities if entity["id"] in wanted],
        relationships=[],
        scopes=[],
    )
    assert {entity["id"] for entity in target["declarations"]["uml"]["entities"]} == wanted
    target["rules"] = [rule for rule in ir["rules"] if include_guard and rule["id"] == GUARD]
    assert len(target["rules"]) == int(include_guard)
    return target


def _native_repository(tmp_path, *, include_guard=True):
    target = _authored_target(include_guard=include_guard)
    files = {
        "archkeel/__init__.py": "",
        "archkeel/ir/__init__.py": "",
        "archkeel/check/__init__.py": "",
        "archkeel/check/evaluation/__init__.py": "",
        "contract.json": json.dumps(target),
    }
    for item in [
        *target["components"],
        *target["rules"],
        *target["declarations"]["uml"]["entities"],
    ]:
        for path in item["provenance"]:
            files[path] = (ROOT / path).read_text()
    for path in (
        "ir/facts.py",
        "ir/profiles.py",
        "ir/facts_validation.py",
        "ir/source_graph.py",
        "check/evaluation/evaluate.py",
    ):
        files["archkeel/" + path] = (ROOT / "src/archkeel" / path).read_text()
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def test_authored_section_ports_are_required_and_parse():
    parse_contract(_authored_target())
    required = (
        (ROOT / "Makefile").read_text().split("pr-test:", 1)[1].split("pr-report-test:", 1)[0]
    )
    assert "tests/test_source_section_types.py" in required


def test_actual_section_ports_fulfil_unchanged_authored_target(tmp_path):
    root, config = _native_repository(tmp_path, include_guard=False)
    comparison = architecture_report(_model(root, config)).comparison
    assert comparison is not None and comparison.status == "PASS", comparison


def test_actual_section_coverage_native_control_is_proven(tmp_path):
    root, config = _native_repository(tmp_path)
    model = _model(root, config)
    guard = next(row for row in rule_assessments(model, undecided_by_rule={}) if row.id == GUARD)
    assert guard.status == "PASS" and guard.evaluation_proven
    assert not trace_valid_violations(model)


def test_actual_section_coverage_raw_control_mutation_fails_unchanged_policy(tmp_path):
    root, config = _native_repository(tmp_path)
    path = root / "archkeel/ir/source_graph.py"
    source = path.read_text()
    nominal = "section == SourceSectionName.CALLS"
    assert nominal in source
    path.write_text(source.replace(nominal, 'section == "calls"', 1))
    authored = (root / "contract.json").read_bytes()
    model = _model(root, config)
    guard = next(row for row in rule_assessments(model, undecided_by_rule={}) if row.id == GUARD)
    assert guard.status == "FAIL" and guard.evaluation_proven
    assert any(GUARD in row.rule_ids for row in trace_valid_violations(model))
    assert (root / "contract.json").read_bytes() == authored


@pytest.mark.parametrize(
    "subject,path,nominal,weakened",
    [
        (
            "PROFILE-SECTIONS-ScanResult.observed_sections",
            "check/evaluation/evaluate.py",
            "observed_sections: frozenset[SourceSectionName]",
            "observed_sections: frozenset[str]",
        ),
        (
            "PROFILE-SECTIONS-source-record",
            "ir/facts_validation.py",
            "def _source_record(\n    record: Record,\n    section: SourceSectionName,",
            "def _source_record(\n    record: Record,\n    section: str,",
        ),
        (
            "PROFILE-SECTIONS-base-declarations",
            "ir/facts_validation.py",
            "def _base_declarations(record: Record, section: SourceSectionName)",
            "def _base_declarations(record: Record, section: str)",
        ),
        (
            "PROFILE-SECTIONS-section-coverage",
            "ir/source_graph.py",
            "    section: SourceSectionName,",
            "    section: str,",
        ),
    ],
)
def test_actual_section_port_weakening_fails_unchanged_authored_target(
    tmp_path, subject, path, nominal, weakened
):
    root, config = _native_repository(tmp_path, include_guard=False)
    source = root / "archkeel" / path
    original = source.read_text()
    assert nominal in original
    source.write_text(original.replace(nominal, weakened, 1))
    authored = (root / "contract.json").read_bytes()
    comparison = architecture_report(_model(root, config)).comparison
    assert comparison is not None and any(
        row.status == "FAIL"
        and row.subject_id == subject
        and row.aspect == ("annotation" if subject.endswith("observed_sections") else "signature")
        for row in comparison.assessments
    ), comparison
    assert (root / "contract.json").read_bytes() == authored


def test_actual_section_ports_reject_raw_strings_and_wrong_enums_under_strict_typing(tmp_path):
    common = """from archkeel.check.evaluation.evaluate import ScanResult
from archkeel.ir.facts import Record, SourceProfile, SourceSectionName
from archkeel.ir.facts_validation import _source_record, _base_declarations
from archkeel.ir.profiles import Profile, UnmeasurableScalar
from archkeel.ir.source_graph import _section_coverage
from archkeel.ir.model import Observation
def check(scan: ScanResult, record: Record, observation: Observation, profile: Profile) -> None:
"""
    cases = {
        "canonical": """    scan.observed_sections = frozenset({SourceSectionName.CALLS})
    _source_record(record, SourceSectionName.SYMBOLS)
    _base_declarations(record, SourceSectionName.SYMBOLS)
    _section_coverage(observation, "scope", SourceSectionName.CALLS, (), (), True)
    profile = Profile("future-analyzer", ".future",
        unmeasured=frozenset({UnmeasurableScalar.CALLS_UNRESOLVED}))
""",
        "raw-field": '    scan.observed_sections = frozenset({"calls"})\n',
        "wrong-field-domain": "    scan.observed_sections = frozenset({SourceProfile.PYTHON})\n",
        "raw-source-record": '    _source_record(record, "symbols")\n',
        "wrong-base-domain": (
            "    _base_declarations(record, UnmeasurableScalar.CALLS_UNRESOLVED)\n"
        ),
        "raw-coverage": '    _section_coverage(observation, "scope", "calls", (), (), True)\n',
    }
    for name, body in cases.items():
        path = tmp_path / (name.replace("-", "_") + ".py")
        path.write_text(common + body)
        result = subprocess.run(
            [sys.executable, "-m", "mypy", "--strict", "--no-incremental", str(path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert (result.returncode == 0) == (name == "canonical"), result.stdout + result.stderr
        if name != "canonical":
            assert "[arg-type]" in result.stdout or "[assignment]" in result.stdout

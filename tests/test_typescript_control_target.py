# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Independent own Target and native mutation controls for TypeScript's typed API."""

import copy
import json
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo
from test_uml_evaluation import _model

from archkeel.check.ports import ScanConfig
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
MODULE = "archkeel.analyzer.typescript"
GUARDS = (
    "TARGET-TYPESCRIPT-CONFIG-TYPED-CONTROL",
    "TARGET-TYPESCRIPT-RESOLVE-TYPED-CONTROL",
    "TARGET-TYPESCRIPT-PARSER-TYPED-CONTROL",
    "TARGET-TYPESCRIPT-COLLECTOR-TYPED-CONTROL",
    "TARGET-TYPESCRIPT-SYNTAX-TYPED-CONTROL",
)


def _contract():
    contract = copy.deepcopy(
        json.loads((ROOT / "docs/architecture/contracts/typescript.json").read_text())
    )
    contract.pop("$schema", None)
    return contract


def _repository(tmp_path, *, changed=None):
    sources = {
        f"archkeel/analyzer/typescript/{name}.py": (
            ROOT / f"src/archkeel/analyzer/typescript/{name}.py"
        ).read_text()
        for name in ("config", "resolve", "parse", "collect", "syntax", "source_input")
        if (ROOT / f"src/archkeel/analyzer/typescript/{name}.py").exists()
    }
    sources.update(changed or {})
    root = _prepare_repo(
        tmp_path,
        {
            "archkeel/__init__.py": "",
            "archkeel/analyzer/__init__.py": "",
            "archkeel/analyzer/typescript/__init__.py": "",
            **sources,
            "contract.json": json.dumps(_contract()),
            "docs/architecture/typescript-control-types.md": (
                ROOT / "docs/architecture/typescript-control-types.md"
            ).read_text(),
            "docs/architecture/typescript-syntax-types.md": (
                ROOT / "docs/architecture/typescript-syntax-types.md"
            ).read_text(),
            "docs/architecture/typescript-json-field-boundary.md": (
                ROOT / "docs/architecture/typescript-json-field-boundary.md"
            ).read_text(),
            "docs/architecture/typescript-source-input.md": (ROOT / "docs/architecture/typescript-source-input.md").read_text(),
            "docs/architecture/language-adapter-target.md": (
                ROOT / "docs/architecture/language-adapter-target.md"
            ).read_text(),
        },
    )
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def _rule(model, identity):
    return next(
        row
        for row in rule_assessments(model, undecided_by_rule={})
        if row.id == identity or row.id.endswith(":" + identity)
    )


def test_native_typescript_api_matches_the_independent_target(tmp_path):
    root, config = _repository(tmp_path)
    model = _model(root, config)
    comparison = architecture_report(model).comparison
    assert comparison is not None and comparison.assessments
    assert comparison.status == "PASS", [
        (row.subject_id, row.aspect, row.reason)
        for row in comparison.assessments
        if row.status != "PASS"
    ]
    target = next(
        row for row in rule_assessments(model, undecided_by_rule={}) if row.kind == "uml_target"
    )
    assert target.status == "PASS" and target.evaluation_proven
    for name in GUARDS:
        rule = _rule(model, name)
        assert rule.status == "PASS" and rule.evaluation_proven, rule
    assert not trace_valid_violations(model)


@pytest.mark.parametrize(
    ("module", "old", "new"),
    [
        ("config", "module: ModuleKind | None", "module: str | None"),
        (
            "config",
            "def has_field(record: Json, name: str) -> bool:",
            "def has_field(record: Json, name: str) -> str:",
        ),
        ("config", "module_resolution: ModuleResolution | None", "module_resolution: str | None"),
        ("config", "target: ScriptTarget | None", "target: str | None"),
        ("config", "def emit_module(self) -> ModuleKind:", "def emit_module(self) -> str:"),
        ("config", "def resolution(self) -> ModuleResolution:", "def resolution(self) -> str:"),
        ("resolve", "mode: ModuleFormat | None,", "mode: str | None,"),
        (
            "resolve",
            "def format_of(self, rel: str) -> ModuleFormat | Unknown | None:",
            "def format_of(self, rel: str) -> str | Unknown | None:",
        ),
    ],
    ids=[
        "module",
        "json-presence-result",
        "resolution",
        "target",
        "derived-emit",
        "derived-resolution",
        "mode",
        "format",
    ],
)
def test_native_source_type_widening_fails_with_fixed_intent(tmp_path, module, old, new):
    source = (ROOT / f"src/archkeel/analyzer/typescript/{module}.py").read_text()
    assert old in source
    root, config = _repository(
        tmp_path,
        changed={f"archkeel/analyzer/typescript/{module}.py": source.replace(old, new, 1)},
    )
    before = (root / "contract.json").read_bytes()
    model = _model(root, config)
    comparison = architecture_report(model).comparison
    assert comparison is not None and comparison.status == "FAIL", comparison
    target = next(
        row for row in rule_assessments(model, undecided_by_rule={}) if row.kind == "uml_target"
    )
    assert target.status == "FAIL"
    assert any(target.id in row.rule_ids for row in trace_valid_violations(model))
    assert (root / "contract.json").read_bytes() == before


@pytest.mark.parametrize("module", ["config", "resolve", "parse", "collect", "syntax", "source_input"])
@pytest.mark.parametrize(
    "probe",
    [
        'def _probe(value):\n    return value == "node16"\n',
        'def _probe(value):\n    return value.startswith("node:")\n',
        'def _probe(value):\n    return value.endswith(".ts")\n',
        'def _probe(value):\n    return value in ("node16", "nodenext")\n',
        'def _probe(value):\n    return "node16" in value\n',
        'def _probe(value):\n    match value:\n        case "node16":\n            return True\n',
        (
            'from typing import Final\nTOKEN: Final[str] = "node16"\n'
            "def _probe(value):\n    return value == TOKEN\n"
        ),
    ],
    ids=["equality", "prefix", "suffix", "membership", "literal-left-membership", "match", "final-alias"],
)
def test_native_parser_and_protocol_strings_fail_without_exceptions(tmp_path, module, probe):
    source = (ROOT / f"src/archkeel/analyzer/typescript/{module}.py").read_text()
    root, config = _repository(
        tmp_path, changed={f"archkeel/analyzer/typescript/{module}.py": source + "\n" + probe}
    )
    before = (root / "contract.json").read_bytes()
    model = _model(root, config)
    guard = _rule(model, GUARDS[("config", "resolve", "parse", "collect", "syntax", "source_input").index(module)])
    assert guard.status == "FAIL"
    assert any(guard.id in row.rule_ids for row in trace_valid_violations(model))
    assert (root / "contract.json").read_bytes() == before


def test_own_observation_proves_both_migrated_module_guards(self_observation):
    for name in GUARDS:
        rule = _rule(self_observation, name)
        assert rule.status == "PASS" and rule.evaluation_proven, rule
    assert not [
        row
        for row in self_observation.records("constructs")
        if row.kind == "string_literal_compare"
        and any(
            row.data.get("owner") == f"{MODULE}.{module}"
            or row.data.get("owner", "").startswith(f"{MODULE}.{module}.")
            for module in ("config", "resolve", "parse", "collect", "syntax", "source_input")
        )
    ]


def test_guards_cover_whole_migrated_modules_without_allowances():
    for identity in GUARDS:
        rule = next(row for row in _contract()["rules"] if row["id"] == identity)
        assert rule["source"] in {
            f"{MODULE}.{name}" for name in ("config", "resolve", "parse", "collect", "syntax", "source_input")
        }
        assert rule["constructs"] == ["string_literal_compare"]
        assert not rule.get("allowed_sources") and not rule.get("exact_sources")


def test_native_configuration_crossing_must_use_its_named_public_api(tmp_path):
    root, config = _repository(
        tmp_path,
        changed={"archkeel/analyzer/typescript/collect.py": "from .config import _normalized\n"},
    )
    model = _model(root, config)
    assert any("TARGET-INTERFACE_BOUNDARY" in row.rule_ids for row in trace_valid_violations(model))


@pytest.mark.parametrize("identity", GUARDS[2:])
def test_native_parser_and_collector_guards_are_proven_without_exceptions(tmp_path, identity):
    root, config = _repository(tmp_path)
    model = _model(root, config)
    rule = _rule(model, identity)
    assert rule.status == "PASS" and rule.evaluation_proven, rule


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("form: ReferenceForm", "form: str"),
        ("kind: DefinitionKind", "kind: str"),
        ("visibility: Visibility | None", "visibility: str | None"),
        ("relationship: BaseRelationship", "relationship: str"),
        ("kind: SiteKind", "kind: str"),
        ("use: SiteUse", "use: str"),
        ("receiver_kind: ReceiverKind", "receiver_kind: str"),
    ],
)
def test_native_syntax_field_widening_fails_against_fixed_port_intent(tmp_path, old, new):
    source = (ROOT / "src/archkeel/analyzer/typescript/syntax.py").read_text()
    assert old in source
    root, config = _repository(
        tmp_path, changed={"archkeel/analyzer/typescript/syntax.py": source.replace(old, new, 1)}
    )
    before = (root / "contract.json").read_bytes()
    model = _model(root, config)
    comparison = architecture_report(model).comparison
    assert comparison is not None and comparison.status == "FAIL", comparison
    target = next(
        row for row in rule_assessments(model, undecided_by_rule={}) if row.kind == "uml_target"
    )
    assert target.status == "FAIL"
    assert any(target.id in row.rule_ids for row in trace_valid_violations(model))
    assert (root / "contract.json").read_bytes() == before

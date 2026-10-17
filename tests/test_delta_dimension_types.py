# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Current Delta decisions are nominal; future public dimensions remain wire data."""

import ast
import json
from enum import StrEnum
from pathlib import Path
from typing import get_type_hints

import pytest
from test_architecture_demo import _prepare_repo
from test_delta import _delta
from test_delta import _model as _observation
from test_dependency_api_target import _source_members
from test_expectation import _expectation_payload
from test_uml_evaluation import _model

from archkeel.check import delta, expectation
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir import codec_delta, model, profiles
from archkeel.ir.codec import (
    canonical_json_bytes, decode_canonical_model, delta_payload, parse_delta, parse_observation,
)
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
DOC = "docs/architecture/delta-dimension-types.md"
DIMENSIONS = [
    ("VIOLATIONS", "violations"),
    ("DEPENDENCY_EDGES", "dependency_edges"),
    ("CYCLES", "cycles"),
    ("API_CROSSINGS", "api_crossings"),
    ("PRIVATE_CROSSINGS", "private_crossings"),
    ("TYPING_SIGNALS", "typing_signals"),
    ("UNKNOWNS", "unknowns"),
    ("COVERAGE", "coverage"),
]


def _dimension():
    value = getattr(profiles, "DeltaDimension", None)
    assert value is not None, "the actual acyclic dimension owner must exist"
    return value


def test_actual_owner_identity_nominal_ports_and_open_public_fields():
    kind = _dimension()
    assert issubclass(kind, StrEnum) and kind.__module__ == "archkeel.ir.profiles"
    assert model.DeltaDimension is kind
    assert [(item.name, str(item)) for item in kind] == DIMENSIONS
    assert get_type_hints(profiles.parse_delta_dimension) == {
        "value": str,
        "return": kind | None,
    }
    assert get_type_hints(profiles.delta_dimension_applicable)["dimension"] is kind
    assert get_type_hints(expectation.ExpectedSemanticChange)["dimension"] is kind
    for cls, field in [(model.SemanticChange, "dimension"), (model.DimensionDelta, "name")]:
        assert get_type_hints(cls)[field] is str
    for helper in [delta._logical_payload, delta._semantic_payload, delta._delta_records]:
        assert get_type_hints(helper)["dimension"] is kind
    assert list(delta.SUPPORTED_DIMENSIONS) == [wire for _, wire in DIMENSIONS]
    assert all(type(value) is str for value in delta.SUPPORTED_DIMENSIONS)


@pytest.mark.parametrize(("name", "wire"), DIMENSIONS)
def test_actual_known_ingress_and_valid_legacy_selected_constructor(name, wire):
    kind = _dimension()
    assert profiles.parse_delta_dimension(wire) is kind[name]
    assert profiles.parse_delta_dimension(kind[name]) is kind[name]
    selected = expectation.ExpectedSemanticChange(wire, "added", "f", 0, 1)
    assert selected.dimension is kind[name]
    assert profiles.delta_dimension_applicable(profiles.PYTHON, kind[name])


@pytest.mark.parametrize("wire", ["future.dimension", "", "CYCLES"])
def test_unknown_profile_data_keeps_legacy_fallback_and_fixed_ingress_rejects(wire):
    _dimension()
    assert profiles.parse_delta_dimension(wire) is None
    assert profiles.delta_dimension_applicable(profiles.PYTHON, wire)
    raw = dict(dimension=wire, change="invalid", fingerprint="f", before_count=False, after_count=0)
    with pytest.raises(expectation.ExpectationError) as error:
        expectation._parse_selected_change(raw, index=4)
    assert str(error.value) == (
        f"selected_changes[4] has unsupported dimension {wire!r}"
        if wire
        else "selected_changes[4].dimension must be a non-empty string"
    )


@pytest.mark.parametrize("version", ["1.2.0", "1.3.0", "1.4.0", "2.0.0"])
def test_future_public_dimensions_roundtrip_exactly_but_fixed_governance_rejects(version):
    raw = _delta(_observation(git_head="1" * 40), _observation(git_head="2" * 40))
    raw["schema_version"] = version
    raw["semantic_changes"].append(
        dict(
            dimension="vendor.future",
            change="added",
            fingerprint="f",
            before_count=0,
            after_count=1,
            before=None,
            after=None,
        )
    )
    raw["unknowns"].append(
        dict(
            id="future",
            dimension="vendor.future",
            reason="future",
            evidence_class="UNKNOWN",
        )
    )
    raw["dimensions"]["vendor.future"] = dict(
        status="SUPPORTED",
        before_count=0,
        after_count=1,
        added=[],
        removed=[],
        relocated=[],
        changed=[],
    )
    parsed = parse_delta(raw)
    assert canonical_json_bytes(delta_payload(parsed)) == canonical_json_bytes(raw)
    with pytest.raises(expectation.ExpectationError) as error:
        expectation._index_semantic_changes(parsed.semantic_changes)
    assert str(error.value) == "semantic_changes[0] has unsupported dimension 'vendor.future'"


def test_nominal_index_keys_retain_plain_duplicate_prose():
    kind = _dimension()
    change = model.SemanticChange("violations", "added", "f", 0, 1, None, None)
    actual, removed, added = expectation._index_semantic_changes((change,))
    assert next(iter(actual))[0] is kind.VIOLATIONS
    assert not removed and not added
    with pytest.raises(expectation.ExpectationError) as error:
        expectation._index_semantic_changes((change, change))
    assert str(error.value) == "delta repeats semantic fingerprint: ('violations', 'added', 'f')"


@pytest.mark.parametrize("value", [None, True, 1, [], {}, "", "FACT", "hypothesis", "UNKNOWN"])
def test_expectation_evidence_invalid_values_keep_error_before_digest_validation(value):
    raw = _expectation_payload()
    raw["evidence_class"] = value
    raw["checker_digest"] = False
    with pytest.raises(expectation.ExpectationError) as error:
        expectation.parse_expectation(raw)
    assert str(error.value) == "architecture expectation evidence_class must be HYPOTHESIS"


@pytest.mark.parametrize("value", [None, True, 1, [], {}, "", "FACT", "unknown", "HYPOTHESIS"])
def test_delta_unknown_evidence_invalid_values_keep_existing_label(value):
    with pytest.raises(ValueError) as error:
        codec_delta._parse_delta_unknown(
            dict(
                id=False,
                dimension=False,
                reason=False,
                evidence_class=value,
            )
        )
    assert str(error.value) == "unknown.evidence_class invalid"


def _contract():
    contracts = [
        json.loads((ROOT / f"docs/architecture/contracts/{name}.json").read_text())
        for name in ("ir", "check")
    ]
    anchors = {
        "IR-MODULE-OBJECT-profiles",
        "IR-DEPENDENCY-model",
        "IR-DELTA-VERSION-codec",
        "KNOWN-ACTION-delta",
        "KNOWN-ACTION-expectation",
        "KNOWN-ACTION-wire",
        "KNOWN-ACTION-selected",
    }
    entities = [
        row
        for contract in contracts
        for row in contract["declarations"]["uml"]["entities"]
        if row["id"].startswith("DELTA-DIMENSION-") or row["id"] in anchors
    ]
    for row in entities:
        if row["kind"] == "module":
            row.pop("parent_id", None)
    contract = contracts[0]
    contract.pop("$schema", None)
    contract["components"] = [
        dict(
            id="CORE", label="core", role="component", packages=["archkeel"],
            responsibilities=["Own the actual typed Delta API fixture."],
            forbidden_responsibilities=[], provenance=[DOC], public=["archkeel"],
        )
    ]
    contract["declarations"] = dict(
        uml=dict(
            schema_version="1.0.0",
            entities=entities,
            relationships=[],
            scopes=[],
        )
    )
    contract["rules"] = [
        row
        for original in contracts
        for row in original["rules"]
        if row["id"].startswith("DELTA-DIMENSION-")
    ]
    return contract


def _repository(tmp_path):
    prefix = "from __future__ import annotations\nfrom dataclasses import dataclass\n"
    files = {
        "archkeel/__init__.py": "",
        "archkeel/ir/__init__.py": "",
        "archkeel/check/__init__.py": "",
        "archkeel/ir/profiles.py": (ROOT / "src/archkeel/ir/profiles.py").read_text(),
        "archkeel/ir/facts.py": (ROOT / "src/archkeel/ir/facts.py").read_text(),
        "archkeel/ir/model.py": prefix
        + "from enum import StrEnum\n"
        + "from archkeel.ir.profiles import DeltaDimension as DeltaDimension\n"
        + "from archkeel.ir.facts import Record as Record, RecordData as RecordData\n"
        + _source_members(
            "src/archkeel/ir/model.py", {"KnownSemanticChangeKind", "SemanticChange"}
        ),
        "archkeel/ir/codec_delta.py": prefix
        + "from archkeel.ir.facts import EvidenceClass as _EvidenceClass\n"
        + _source_members("src/archkeel/ir/codec_delta.py", {"_parse_delta_unknown"}),
        "archkeel/check/delta.py": prefix
        + "from archkeel.ir.model import Record, RecordData\n"
        + "from archkeel.ir.profiles import DeltaDimension as _DeltaDimension\n"
        + _source_members(
            "src/archkeel/check/delta.py",
            {
                "_logical_payload",
                "_semantic_payload",
                "_section",
                "_delta_records",
            },
        ),
        "archkeel/check/expectation.py": prefix
        + "import builtins as _builtins\n"
        + "from archkeel.ir.profiles import DeltaDimension as _DeltaDimension\n"
        + "from archkeel.ir.model import KnownSemanticChangeKind as _KnownSemanticChangeKind\n"
        + _source_members(
            "src/archkeel/check/expectation.py",
            {
                "ExpectationError",
                "ExpectedSemanticChange",
                "_index_semantic_changes",
                "_guardrail_failures",
            },
        ),
    }
    contract = _contract()
    files["contract.json"] = json.dumps(contract)
    for row in contract["declarations"]["uml"]["entities"]:
        for path in row.get("provenance", ()):
            files[path] = "Authored actual Delta control intent.\n"
    files[DOC] = "Current nominal Delta dimensions and future-open wire data.\n"
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def _valid(root, config):
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert result.exit_code == 0 and encoded is not None, result.diagnostics
    observed = parse_observation(decode_canonical_model(json.loads(encoded)))
    comparison = architecture_report(observed).comparison
    assert comparison is not None and comparison.status == "PASS", [
        (row.subject_id, row.aspect, row.status, row.reason)
        for row in comparison.assessments
        if row.status != "PASS"
    ]
    assert not trace_valid_violations(observed)



def test_native_actual_delta_ports_match_independent_fixed_target(tmp_path):
    root, config = _repository(tmp_path)
    _valid(root, config)


@pytest.mark.parametrize(
    ("path", "old", "new"),
    [
        ("ir/profiles.py", "class DeltaDimension(StrEnum):", "class DeltaDimension(str):"),
        (
            "ir/profiles.py",
            "value: str) -> DeltaDimension | None",
            "value: object) -> DeltaDimension | None",
        ),
        ("ir/profiles.py", "value: str) -> DeltaDimension | None", "value: str) -> str | None"),
        ("ir/profiles.py", "dimension: DeltaDimension", "dimension: str"),
        ("ir/model.py", "dimension: str", "dimension: DeltaDimension"),
        (
            "check/delta.py",
            "def _logical_payload(dimension: _DeltaDimension",
            "def _logical_payload(dimension: str",
        ),
        (
            "check/delta.py",
            "def _semantic_payload(dimension: _DeltaDimension",
            "def _semantic_payload(dimension: str",
        ),
        ("check/expectation.py", "dimension: _DeltaDimension", "dimension: str"),
    ],
)
def test_native_actual_api_weakening_fails_unchanged_target(tmp_path, path, old, new):
    root, config = _repository(tmp_path)
    _valid(root, config)
    source = root / "archkeel" / path
    original = source.read_text()
    assert old in original
    intent = (root / "contract.json").read_bytes()
    source.write_text(original.replace(old, new, 1))
    assert trace_valid_violations(_model(root, config))
    assert (root / "contract.json").read_bytes() == intent


@pytest.mark.parametrize(
    ("path", "old", "new"),
    [
        ("ir/profiles.py", "known == DeltaDimension.API_CROSSINGS", 'known == "api_crossings"'),
        ("check/delta.py", "dimension == _DeltaDimension.COVERAGE:", 'dimension == "coverage":'),
        ("check/expectation.py", "dimension == _DeltaDimension.CYCLES", 'dimension == "cycles"'),
        (
            "ir/codec_delta.py",
            "evidence_class is not _EvidenceClass.UNKNOWN",
            'evidence_class != "UNKNOWN"',
        ),
    ],
)
def test_native_actual_owner_and_consumer_raw_reversion_fails(tmp_path, path, old, new):
    root, config = _repository(tmp_path)
    _valid(root, config)
    source = root / "archkeel" / path
    original = source.read_text()
    assert old in original
    intent = (root / "contract.json").read_bytes()
    source.write_text(original.replace(old, new, 1))
    assert any(row.rule_ids for row in trace_valid_violations(_model(root, config)))
    assert (root / "contract.json").read_bytes() == intent


def _ownership_repository(tmp_path):
    """Project the real two-owner adjacency, with complete selected source inventory."""
    contract = json.loads((ROOT / "docs/architecture/contracts/ir.json").read_text())
    contract.pop("$schema", None)
    components = []
    for original in contract["components"]:
        if original["label"] not in {"profiles", "governance"}:
            continue
        row = dict(original)
        row.pop("exact_modules", None)
        row["packages"] = [
            "archkeel.ir.profiles" if row["label"] == "profiles" else "archkeel.ir.model"
        ]
        row["public"] = list(row["packages"])
        row["requires"] = [
            value for value in row.get("requires", ())
            if value["component"] in {"profiles", "governance"}
        ]
        components.append(row)
    contract["components"] = components
    contract["rules"] = [
        row for row in contract["rules"] if row["id"] == "TARGET-COMPLETE_REQUIRES"
    ]
    assert len(contract["rules"]) == 1
    target = contract["declarations"]["uml"]
    target["entities"] = []
    target["relationships"] = []
    target["scopes"] = []
    profile_source = "from enum import StrEnum\n" + _source_members(
        "src/archkeel/ir/profiles.py", {"DeltaDimension", "parse_delta_dimension"}
    ) + "\n"
    original_model = (ROOT / "src/archkeel/ir/model.py").read_text()
    facade = next(
        node for node in ast.parse(original_model).body
        if isinstance(node, ast.ImportFrom) and node.module == "profiles"
        and any(alias.name == "DeltaDimension" for alias in node.names)
    )
    files = {
        "archkeel/__init__.py": "", "archkeel/ir/__init__.py": "",
        "archkeel/ir/profiles.py": profile_source,
        "archkeel/ir/model.py": ast.get_source_segment(original_model, facade) + "\n",
        "contract.json": json.dumps(contract),
    }
    for component in components:
        for path in component["provenance"]:
            files[path] = "Actual two-owner adjacency projection.\n"
    for rule in contract["rules"]:
        for path in rule["provenance"]:
            files[path] = "Existing complete-requires policy.\n"
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def test_native_canonical_owner_relocation_fails_fixed_target(tmp_path):
    root, config = _ownership_repository(tmp_path)
    before = _model(root, config)
    rule = next(row for row in rule_assessments(before, undecided_by_rule={})
                if row.id == "TARGET-COMPLETE_REQUIRES")
    assert rule.status == "PASS" and rule.evaluation_proven, rule
    assert not trace_valid_violations(before)
    source = root / "archkeel/ir/profiles.py"
    text = source.read_text()
    node = next(
        node for node in ast.parse(text).body
        if isinstance(node, ast.ClassDef) and node.name == "DeltaDimension"
    )
    lines = text.splitlines(keepends=True)
    definition = "".join(lines[node.lineno - 1:node.end_lineno])
    source.write_text(
        "from .model import DeltaDimension\n"
        + "".join(lines[:node.lineno - 1] + lines[node.end_lineno:])
    )
    destination = root / "archkeel/ir/model.py"
    destination.write_text("from enum import StrEnum\n" + definition + "\n")
    intent = (root / "contract.json").read_bytes()
    observed = _model(root, config)
    rule = next(row for row in rule_assessments(observed, undecided_by_rule={})
                if row.id == "TARGET-COMPLETE_REQUIRES")
    assert rule.status == "FAIL", rule
    assert any("TARGET-COMPLETE_REQUIRES" in row.rule_ids
               for row in trace_valid_violations(observed))
    assert (root / "contract.json").read_bytes() == intent

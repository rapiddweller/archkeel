# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Actual measurement tags preserve wire data and independent nominal API intent."""

import ast
import copy
import json
from enum import StrEnum
from pathlib import Path
from typing import get_type_hints

import pytest
from test_architecture_demo import _prepare_repo
from test_dependency_api_target import _source_members
from test_uml_evaluation import _model

from archkeel.check.ports import ScanConfig
from archkeel.ir import measurements as m
from archkeel.ir import model
from archkeel.ir.codec import baseline_bytes, parse_measurements, parse_validation_baseline
from archkeel.ir.codec_governance import _measurement_payload
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
DOC = "docs/architecture/measurement-control-types.md"
DOMAINS = {
    "MeasurementBudgetName": [
        ("CYCLE_EDGES", "cycle_edges"),
        ("PRIVATE_CROSSINGS", "private_crossings"),
        ("TYPING_POSITIONS", "typing_positions"),
        ("CALLS_UNRESOLVED", "calls_unresolved"),
        ("UNTYPED_PRIVATE_ACCESSES", "untyped_private_accesses"),
        ("UNKNOWN_POSITIONS", "unknown_positions"),
    ],
    "NameBudgetKind": [("FACADE_NAMES", "facade_names"), ("COUPLING_NAMES", "coupling_names")],
    "MeasurementResolution": [("MEASURED", "measured"), ("NOT_APPLICABLE", "n/a")],
    "MetricComparisonStatus": [
        ("PASS", "PASS"),
        ("FAIL", "FAIL"),
        ("NOT_APPLICABLE", "n/a"),
    ],
}


def _scalars(unresolved=0):
    return m.RatchetScalars(0, 0, 0, 0, unresolved, 0)


@pytest.mark.parametrize("name", DOMAINS)
def test_actual_measurement_owner_has_exact_distinct_nominal_domains(name):
    assert hasattr(m, name), name
    domain = getattr(m, name)
    assert isinstance(domain, type) and issubclass(domain, StrEnum)
    assert domain.__module__ == "archkeel.ir.measurements"
    assert [(member.name, str(member)) for member in domain] == DOMAINS[name]
    assert len({getattr(m, key) for key in DOMAINS if hasattr(m, key)}) == 4


def test_real_fields_and_comparison_return_use_precise_owner_types():
    assert hasattr(m, "MeasurementResolution")
    assert get_type_hints(m.MeasurementBudget)["name"] == m.MeasurementBudgetName | m.NameBudgetKind
    assert get_type_hints(m.Measurements)["resolution"] is m.MeasurementResolution
    assert get_type_hints(model.ContractMeasurementBudget)["name"] is m.MeasurementBudgetName
    assert get_type_hints(model.InterfaceBudgetResult)["budget"] is m.NameBudgetKind
    assert (
        get_type_hints(m.compare_measurements)["return"]
        == tuple[tuple[str, str, str, m.MetricComparisonStatus], ...]
    )


@pytest.mark.parametrize("raw", [value for _, value in DOMAINS["MeasurementBudgetName"]])
def test_legacy_scalar_budget_constructor_and_contract_value_normalize_once(raw):
    budget = m.MeasurementBudget(raw, 2)
    declared = model.ContractMeasurementBudget(raw, ("docs/architecture/example.md",))
    assert type(budget.name) is m.MeasurementBudgetName
    assert declared.name is budget.name
    assert budget.label == raw


@pytest.mark.parametrize("raw", ["facade_names", "coupling_names"])
def test_legacy_keyed_budget_and_interface_result_share_owned_kind(raw):
    budget = m.MeasurementBudget(raw, 1, "consumer -> provider", ("module:API",))
    result = model.InterfaceBudgetResult(
        raw, "consumer -> provider", "/declarations", 2, 1, 0, ("module:API",), ()
    )
    assert type(budget.name) is m.NameBudgetKind
    assert result.budget is budget.name
    assert budget.label == raw + " consumer -> provider"


@pytest.mark.parametrize(
    "arguments",
    [
        ("calls_unresolved", True),
        ("calls_unresolved", -1),
        ("facade_names", 1),
        ("coupling_names", 2, "pair", ("one",)),
        ("facade_names", 2, "component", ("z", "a")),
        ("facade_names", 2, "component", ("same", "same")),
    ],
)
def test_existing_invalid_budget_invariants_keep_ratchet_error(arguments):
    with pytest.raises(m.RatchetError):
        m.MeasurementBudget(*arguments)


@pytest.mark.parametrize(
    ("unresolved", "total", "raw"),
    [(0, 2, "measured"), (0, 0, "n/a"), (None, None, "n/a")],
)
def test_valid_legacy_availability_constructor_and_payload_keep_exact_wire(unresolved, total, raw):
    value = m.Measurements(_scalars(unresolved), total, raw)
    assert type(value.resolution) is getattr(m, "MeasurementResolution", None)
    payload = _measurement_payload(value)
    assert json.loads(json.dumps(payload)) == {
        "scalars": {
            "violations": 0,
            "cycle_edges": 0,
            "private_crossings": 0,
            "typing_positions": 0,
            "calls_unresolved": unresolved,
            "coverage_failures": 0,
            "untyped_private_accesses": 0,
            "unknown_positions": 0,
        },
        "calls_total": total,
        "resolution": raw,
    }
    decoded = parse_measurements(payload, "measurement")
    assert decoded == value
    assert decoded.resolution is value.resolution


@pytest.mark.parametrize(
    ("unresolved", "total", "resolution"),
    [(0, 0, "measured"), (0, 2, "n/a"), (None, 0, "n/a"), (0, None, "n/a")],
)
def test_invalid_zero_none_and_availability_combinations_stay_rejected(
    unresolved, total, resolution
):
    with pytest.raises(m.RatchetError):
        m.Measurements(_scalars(unresolved), total, resolution)


def test_legacy_zero_unmeasured_wire_is_none_without_widening_nonnullable_formats():
    payload = _measurement_payload(m.Measurements(_scalars(None), None, "n/a"))
    payload["calls_total"] = 0
    decoded = parse_measurements(payload, "legacy", nullable_calls=False)
    assert decoded.calls_total is None and decoded.scalars.calls_unresolved is None
    assert type(decoded.resolution) is getattr(m, "MeasurementResolution", None)
    payload["calls_total"] = None
    with pytest.raises(m.RatchetError, match="null call totals require a nullable format"):
        parse_measurements(payload, "legacy", nullable_calls=False)


@pytest.mark.parametrize(
    ("before", "after", "wire"), [(1, 2, "FAIL"), (2, 1, "PASS"), (None, 1, "n/a")]
)
def test_comparison_tuple_shape_and_status_are_precise_without_closing_display_labels(
    before, after, wire
):
    row = m._compare("arbitrary metric label", before, after)
    assert isinstance(row, tuple) and row[0] == "arbitrary metric label"
    assert str(row[3]) == wire
    assert type(row[3]) is getattr(m, "MetricComparisonStatus", None)
    rows = m.compare_measurements(
        m.Measurements(_scalars(), 0, "n/a"), m.Measurements(_scalars(), 0, "n/a")
    )
    assert all(type(item[3]) is m.MetricComparisonStatus for item in rows)


def test_baseline_budget_names_keep_wire_keys_and_existing_namespace_data():
    raw = {
        "schema_version": "1.3.0",
        "violations": [],
        "budgets": {"calls_unresolved": 2, "facade_names": {"arbitrary/component": ["module:API"]}},
    }
    value = parse_validation_baseline(raw)
    assert {type(item.name) for item in value.budgets} == {
        m.MeasurementBudgetName,
        m.NameBudgetKind,
    }
    assert json.loads(baseline_bytes(value.violations, value.budgets)) == raw


def _contract():
    intent = copy.deepcopy(json.loads((ROOT / "docs/architecture/contracts/ir.json").read_text()))
    intent.pop("$schema", None)
    intent["declarations"]["uml"]["entities"] = [
        row
        for row in intent["declarations"]["uml"]["entities"]
        if row["id"].startswith("IR-MEASURE-") or row["id"] == "IR-DEPENDENCY-model"
    ]
    intent["declarations"]["uml"]["relationships"] = []
    intent["declarations"]["uml"]["scopes"] = []
    intent["rules"] = [
        {
            "id": "MEASURE-CONTROL",
            "kind": "forbidden_construct",
            "source": "archkeel.ir.measurements",
            "constructs": ["string_literal_compare"],
            "rationale": "Measurement control decisions use the real nominal owner.",
            "provenance": [DOC],
            "decided_by": "architect",
        }
    ]
    return intent


def _repository(tmp_path):
    files = {
        "archkeel/__init__.py": "",
        "archkeel/ir/__init__.py": "",
        "archkeel/ir/measurements.py": (ROOT / "src/archkeel/ir/measurements.py").read_text(),
        "archkeel/ir/profiles.py": "from enum import StrEnum\n"
        + _source_members("src/archkeel/ir/profiles.py", {"UnmeasurableScalar"}),
        "archkeel/ir/model.py": (
            "from __future__ import annotations\nimport builtins\nfrom dataclasses import dataclass\n"
            "from .measurements import MeasurementBudgetName, NameBudgetKind\n"
            + _source_members(
                "src/archkeel/ir/model.py", {"ContractMeasurementBudget", "InterfaceBudgetResult"}
            )
        ),
        "contract.json": json.dumps(_contract()),
        DOC: "Independent measurement API intent.\n",
    }
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def _valid(value):
    comparison = architecture_report(value).comparison
    assert comparison is not None and comparison.status == "PASS", [
        (row.subject_id, row.aspect, row.status, row.reason) for row in comparison.assessments
        if row.status != "PASS"
    ]
    assert not trace_valid_violations(value)


def test_native_actual_source_matches_fourteen_independent_targets_and_existing_anchor(tmp_path):
    assert len(_contract()["declarations"]["uml"]["entities"]) == 15
    root, config = _repository(tmp_path)
    _valid(_model(root, config))


@pytest.mark.parametrize(
    ("path", "old", "new"),
    [
        ("measurements.py", "name: MeasurementBudgetName | NameBudgetKind", "name: str"),
        ("measurements.py", "resolution: MeasurementResolution", "resolution: str"),
        ("model.py", "name: MeasurementBudgetName", "name: str"),
        ("model.py", "budget: NameBudgetKind", "budget: str"),
        (
            "measurements.py",
            ") -> tuple[tuple[str, str, str, MetricComparisonStatus], ...]:",
            ") -> tuple[tuple[str, str, str, str], ...]:",
        ),
        *[
            ("measurements.py", "class " + name + "(StrEnum):", "class " + name + "(str):")
            for name in DOMAINS
        ],
    ],
)
def test_native_type_widening_and_enum_substitution_fail_fixed_intent(tmp_path, path, old, new):
    root, config = _repository(tmp_path)
    _valid(_model(root, config))
    source = root / "archkeel/ir" / path
    content = source.read_text()
    assert old in content
    intent = (root / "contract.json").read_bytes()
    source.write_text(content.replace(old, new, 1))
    changed = _model(root, config)
    assert trace_valid_violations(changed)
    assert any(row.status == "FAIL" for row in architecture_report(changed).comparison.assessments)
    assert (root / "contract.json").read_bytes() == intent


@pytest.mark.parametrize(
    "probe",
    [
        'def _probe(value):\n    return value == "measured"\n',
        'def _probe(value):\n    return value in ("PASS", "FAIL", "n/a")\n',
        'def _probe(value):\n    match value:\n        case "facade_names":\n'
        "            return True\n        case _:\n            return False\n",
        'from typing import Final\nTAG: Final[str] = "coupling_names"\n'
        "def _probe(value):\n    return value == TAG\n",
    ],
)
def test_native_complete_measurement_owner_rejects_raw_dispatch(tmp_path, probe):
    root, config = _repository(tmp_path)
    _valid(_model(root, config))
    source = root / "archkeel/ir/measurements.py"
    source.write_text(source.read_text() + "\n" + probe)
    value = _model(root, config)
    assert any("MEASURE-CONTROL" in row.rule_ids for row in trace_valid_violations(value))

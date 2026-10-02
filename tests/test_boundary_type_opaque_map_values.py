# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Issue #253: the outer map and its opaque value need separate exact decisions."""

from __future__ import annotations

import json
import subprocess
from html import unescape
from pathlib import Path

import pytest
from test_analyzer import _observe
from test_architecture_demo import _prepare_repo
from test_boundary_type_allowances import _contract
from test_boundary_types_contained_mapping import _commit_report_fixture, _VisibleHTMLText
from test_boundary_types_nested_dtos import _write_app
from test_contract_model import VALIDATOR

from archkeel.analyzer import observe
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.check.run import inspect_observation
from archkeel.check.validation import run_validate
from archkeel.cli import main
from archkeel.ir.codec import (
    contract_bytes,
    contract_digest,
    decode_canonical_model,
    observation_payload,
    parse_contract,
    parse_observation,
)
from archkeel.ir.model import ObservationResult, Record
from archkeel.ir.trace import trace_valid_violations
from archkeel.ir.widening import contract_widenings
from archkeel.render.html import render_html
from fixtures.architecture_demo import CATALOG

_OUTER = {
    "qualified_name": "sample.app.impl.validate_raw",
    "position": "values",
    "annotation": "dict[str, object]",
}
_VALUE = {**_OUTER, "container_depth": 1}
_SOURCE = (
    "def validate_raw(values: dict[str, object]) -> dict[str, object]:\n"
    "    if 'count' not in values: raise ValueError('count required')\n"
    "    return values\n"
)


def _app(
    root: Path,
    *,
    source: str = _SOURCE,
    allowances: tuple[dict[str, object], ...] = (),
    declared: tuple[str, ...] = ("sample.app.impl:validate_raw",),
) -> None:
    _write_app(root, implementation=source, declared=declared)
    path = root / "contract.json"
    contract = json.loads(path.read_text())
    contract["rules"][0]["allowed_positions"] = list(allowances)
    path.write_text(json.dumps(contract))
    provenance = root / "docs/architecture/sample.md"
    provenance.parent.mkdir(parents=True, exist_ok=True)
    provenance.write_text(
        "Validate raw values before constructing a typed model.\n"
        "<!-- archkeel-component-graph -->\n```mermaid\ngraph TD\n```\n"
    )


def _opacity_facts(result: ObservationResult) -> list[Record]:
    assert result.observation is not None
    return [
        record
        for record in result.observation.records("typing_signals") or ()
        if record.kind == "boundary_type_allowance" and record.data.get("accepted_opacity") is True
    ]


def test_explicit_map_value_coordinate_is_a_valid_contract() -> None:
    raw = _contract()
    raw["rules"][0]["allowed_positions"] = [_OUTER, _VALUE]

    assert not list(VALIDATOR.iter_errors(raw))
    parsed = parse_contract(raw)
    assert json.loads(contract_bytes(parsed))["rules"][0]["allowed_positions"] == [
        {**_OUTER, "field_path": ""},
        {**_VALUE, "field_path": ""},
    ]


def test_separate_input_and_return_value_decisions_accept_only_the_raw_map(
    tmp_path: Path,
) -> None:
    allowances = tuple(
        {**selector, "position": position}
        for position in ("values", "return")
        for selector in (_OUTER, _VALUE)
    )
    _app(tmp_path, allowances=allowances)

    result = _observe(tmp_path)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    assert inspect_observation(result.observation)[1] == "PASS"
    facts = _opacity_facts(result)
    assert len(facts) == 2
    assert {record.data.get("position") for record in facts} == {"values", "return"}
    for fact in facts:
        assert fact.data.get("annotation") == "dict[str, object]"
        assert fact.data.get("nested_annotation") == "object"
        assert fact.data.get("container_depth") == 1
        assert fact.provenance == ("docs/architecture/sample.md",)
        assert fact.evidence_ids and fact.rule_ids == ("APP-TYPES-NOT-DICT",)
        assert "accepted opacity" in fact.title and "type closure remains unproven" in fact.title


def test_outer_map_decisions_leave_both_opaque_values_forbidden(tmp_path: Path) -> None:
    _app(
        tmp_path,
        allowances=tuple({**_OUTER, "position": position} for position in ("values", "return")),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    findings = trace_valid_violations(result.observation)
    assert len(findings) == 2
    assert all(record.data.get("nested_annotation") == "object" for record in findings)
    assert _opacity_facts(result) == []


def test_value_decision_leaves_the_outer_map_forbidden(tmp_path: Path) -> None:
    _app(tmp_path, allowances=(_VALUE,))

    result = _observe(tmp_path)

    assert result.observation is not None
    findings = trace_valid_violations(result.observation)
    assert len(findings) == 3
    assert not any(
        record.data.get("position") == "values" and record.data.get("nested_annotation") == "object"
        for record in findings
    )
    assert len(_opacity_facts(result)) == 1


def test_input_permission_keeps_return_other_function_and_nullable_constructor_context(
    tmp_path: Path,
) -> None:
    _app(
        tmp_path,
        source=_SOURCE
        + "def other(values: dict[str, object]) -> str: return ''\n"
        + "class Context:\n    def __init__(self, ctx: object | None) -> None: pass\n",
        declared=(
            "sample.app.impl:validate_raw",
            "sample.app.impl:other",
            "sample.app.impl:Context",
        ),
        allowances=(_OUTER, _VALUE),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    findings = trace_valid_violations(result.observation)
    assert len(findings) == 5
    assert {(item.data.get("qualified_name"), item.data.get("position")) for item in findings} == {
        ("sample.app.impl.validate_raw", "return"),
        ("sample.app.impl.other", "values"),
        ("sample.app.impl.Context.__init__", "ctx"),
    }
    assert len(_opacity_facts(result)) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"qualified_name": "sample.app.impl.other"},
        {"position": "other"},
        {"container_depth": 2},
        {"annotation": "dict[int, object]"},
        {"annotation": "dict[str, Any]"},
        {"annotation": "object"},
    ],
    ids=("symbol", "parameter", "depth", "key", "value", "root-object"),
)
def test_value_permission_requires_every_coordinate(
    tmp_path: Path, change: dict[str, object]
) -> None:
    _app(tmp_path, allowances=(_OUTER, {**_VALUE, **change}))

    result = _observe(tmp_path)

    assert result.observation is not None
    assert len(trace_valid_violations(result.observation)) == 3
    assert _opacity_facts(result) == []


@pytest.mark.parametrize(
    "annotation",
    [
        "dict[object, object]",
        "dict[object, str]",
        "tuple[dict[str, object], list[object]]",
        "tuple[dict[str, object], dict[str, object]]",
        "dict[str, object] | dict[int, object]",
        "dict[str, Payload]",
        "Raw",
        "dict[str, Any]",
        "dict",
    ],
    ids=(
        "key-value",
        "key-only",
        "same-depth-sibling",
        "duplicate-map",
        "union-maps",
        "aliased-value",
        "aliased-map",
        "any",
        "bare",
    ),
)
def test_ambiguous_or_nonliteral_values_cannot_accept_opacity(
    tmp_path: Path, annotation: str
) -> None:
    _app(
        tmp_path,
        source=(
            "from typing import Any\nPayload = object\nRaw = dict[str, object]\n"
            f"def validate_raw(values: {annotation}) -> str: return ''\n"
        ),
        allowances=(
            {
                **_VALUE,
                "annotation": annotation,
                "container_depth": 2 if annotation.startswith("tuple") else 1,
            },
        ),
    )

    result = _observe(tmp_path)

    if annotation == "dict":
        assert result.observation is None
    else:
        assert result.observation is not None
        assert trace_valid_violations(result.observation)
        assert _opacity_facts(result) == []


def test_exact_deeper_value_decision_does_not_use_root_depth(tmp_path: Path) -> None:
    annotation = "list[dict[str, object]]"
    _app(
        tmp_path,
        source=f"def validate_raw(values: {annotation}) -> str: return ''\n",
        allowances=({**_VALUE, "annotation": annotation, "container_depth": 2},),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    [finding] = trace_valid_violations(result.observation)
    assert finding.data.get("nested_annotation") == "dict[str, object]"
    [fact] = _opacity_facts(result)
    assert fact.data.get("container_depth") == 2


def test_value_opacity_preserves_an_unknown_union_neighbor(tmp_path: Path) -> None:
    annotation = "dict[str, object] | Missing"
    _app(
        tmp_path,
        source=f"def validate_raw(values: {annotation}) -> str: return ''\n",
        allowances=tuple({**selector, "annotation": annotation} for selector in (_OUTER, _VALUE)),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    assert len(_opacity_facts(result)) == 1
    assert any(
        item.kind == "boundary_type_position"
        for item in result.observation.records("unknowns") or ()
    )
    assert inspect_observation(result.observation)[1] == "UNKNOWN"


def test_class_shadowed_object_value_stays_unknown(tmp_path: Path) -> None:
    _app(
        tmp_path,
        source=(
            "class Hidden: pass\nclass Converter:\n    object = Hidden\n"
            "    def validate_raw(self, values: dict[str, object]) -> str: return ''\n"
        ),
        declared=("sample.app.impl:Converter",),
        allowances=({**_VALUE, "qualified_name": "sample.app.impl.Converter.validate_raw"},),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert _opacity_facts(result) == []
    assert any(
        item.kind == "boundary_type_position"
        for item in result.observation.records("unknowns") or ()
    )


@pytest.mark.parametrize("annotation", ["object", "object | None", "list[object]"])
def test_depth_coordinate_cannot_accept_nonmapping_native_payloads(
    tmp_path: Path, annotation: str
) -> None:
    _app(
        tmp_path,
        source=f"def validate_raw(values: {annotation}) -> str: return ''\n",
        allowances=({**_VALUE, "annotation": annotation},),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert trace_valid_violations(result.observation)
    assert _opacity_facts(result) == []


@pytest.mark.parametrize("depth", [0, -1, True, 1.5, "1", None])
def test_malformed_container_depth_is_rejected(depth: object) -> None:
    raw = _contract()
    raw["rules"][0]["allowed_positions"] = [{**_VALUE, "container_depth": depth}]

    assert list(VALIDATOR.iter_errors(raw))
    with pytest.raises(ValueError):
        parse_contract(raw)


def test_decoder_refuses_a_float_container_coordinate_without_coercing() -> None:
    raw = _contract()
    raw["rules"][0]["allowed_positions"] = [{**_VALUE, "container_depth": 1.0}]

    with pytest.raises(ValueError):
        parse_contract(raw)


def test_dto_field_and_container_coordinate_cannot_be_combined() -> None:
    raw = _contract()
    raw["rules"][0]["allowed_positions"] = [{**_VALUE, "field_path": "items"}]

    assert list(VALIDATOR.iter_errors(raw))
    with pytest.raises(ValueError):
        parse_contract(raw)


def test_new_depth_permission_is_a_widening_and_removal_narrows() -> None:
    before = _contract(allowance=_OUTER)
    after = _contract(allowance=_OUTER)
    after["rules"][0]["allowed_positions"].append(_VALUE)
    old, new = parse_contract(before), parse_contract(after)

    [widening] = contract_widenings(old, new)
    assert "allowed_positions gained" in widening and "container_depth=1" in widening
    assert contract_widenings(new, old) == ()
    assert contract_digest(old) != contract_digest(new)


def test_omitted_depth_keeps_the_pre_selector_canonical_digest() -> None:
    contract = parse_contract(_contract(allowance=_OUTER))

    assert (
        contract_digest(contract)
        == "b8e822f1e19731e4ac24505a392eeff08e1c118f3991ac071a1fb9dea1ed3ae1"
    )
    assert b"container_depth" not in contract_bytes(contract)


def test_value_fact_roundtrips_and_report_retains_source_packet(tmp_path: Path) -> None:
    _app(tmp_path, allowances=(_OUTER, _VALUE))
    _observe(tmp_path)
    _commit_report_fixture(tmp_path)
    report, artifact = run_report(
        tmp_path, config=ScanConfig((".",), "sample", "contract.json", "0" * 64), analyzer=observe
    )

    assert artifact is not None
    observation = parse_observation(decode_canonical_model(json.loads(artifact)))
    payload = observation_payload(observation)
    [fact] = [
        item
        for item in payload["typing_signals"]
        if item["kind"] == "boundary_type_allowance" and item["data"].get("accepted_opacity")
    ]
    assert fact["data"]["container_depth"] == 1 and fact["data"]["nested_annotation"] == "object"
    [declaration] = [item for item in payload["declarations"] if item["id"] == "APP-TYPES-NOT-DICT"]
    assert declaration["data"]["allowed_positions"] == [
        {**_OUTER, "field_path": ""},
        {**_VALUE, "field_path": ""},
    ]
    html = render_html(
        report, observation, repository="sample", architecture_href="architecture.json"
    ).decode()
    text = _VisibleHTMLText()
    text.feed(html)
    visible = " ".join(text.parts)
    assert "opaque mapping value" in visible and "accepted opacity" in visible
    assert "type closure remains unproven" in visible and "container depth 1" in visible
    [finding] = [
        item
        for item in trace_valid_violations(observation)
        if item.data.get("nested_annotation") == "object"
    ]
    assert f"Evidence for {finding.id}" in html
    decoded = unescape(html)
    assert "returns dict[str, object] holding object" in decoded
    assert "Recorded evidence (repository content):" in decoded and "Source digest:" in decoded


def test_adding_value_permission_against_git_requires_amendment(tmp_path: Path) -> None:
    source = _SOURCE.replace("-> dict[str, object]", "-> str").replace(
        "return values", "return str(values)"
    )
    _app(tmp_path, source=source, allowances=(_OUTER,))
    _observe(tmp_path)
    _commit_report_fixture(tmp_path)
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()
    _app(tmp_path, source=source, allowances=(_OUTER, _VALUE))

    result, _ = run_validate(
        tmp_path, ScanConfig((".",), "sample", "contract.json", "0" * 64), observe, against=base
    )

    assert result.exit_code == 1, result.diagnostics
    assert any(
        "allowed_positions gained" in failure and "container_depth=1" in failure
        for failure in result.failures
    )
    amendment = tmp_path / "amendment.json"
    written, files = run_validate(
        tmp_path,
        ScanConfig((".",), "sample", "contract.json", "0" * 64),
        observe,
        against=base,
        amendment=amendment,
        write_amendment=True,
        decided_by="architect",
        rationale="Accept this exact opaque map value before model validation.",
    )
    assert written.exit_code == 0, written.diagnostics
    amendment.write_bytes(files[str(amendment)])
    accepted, _ = run_validate(
        tmp_path,
        ScanConfig((".",), "sample", "contract.json", "0" * 64),
        observe,
        against=base,
        amendment=amendment,
    )
    assert accepted.exit_code == 0 and accepted.failures == ()


@pytest.mark.parametrize(
    ("variant_id", "missing_values", "declared_rules"),
    [
        ("class-a-boundary-types-opaque-map-values", 0, "UNKNOWN"),
        ("class-a-boundary-types-opaque-map-values-missing", 2, "FAIL"),
        ("class-a-boundary-types-opaque-map-values-unknown", 0, "UNKNOWN"),
    ],
)
def test_catalog_raw_map_decisions_retain_exact_cli_evidence(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    variant_id: str,
    missing_values: int,
    declared_rules: str,
) -> None:
    variant = next(item for item in CATALOG if item.id == variant_id)
    root = _prepare_repo(tmp_path, dict(variant.files))
    output = tmp_path / "architecture.json"

    assert main(["report", "--root", str(root), "--output", str(output), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["declared_rules"] == declared_rules
    observation = parse_observation(decode_canonical_model(json.loads(output.read_text())))
    findings = [
        item for item in trace_valid_violations(observation) if item.kind == "boundary_types"
    ]
    assert len(findings) == missing_values
    assert all(
        item.data.get("nested_annotation") == "object" and item.data.get("container_depth") == 1
        for item in findings
    )
    facts = [
        item
        for item in observation.records("typing_signals") or ()
        if item.kind == "boundary_type_allowance" and item.data.get("accepted_opacity")
    ]
    assert len(facts) == (0 if missing_values else 2)

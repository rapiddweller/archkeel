# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A native-value decision selects one complete DTO field and container depth."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from test_analyzer import _observe
from test_boundary_type_opaque_map_values import _app, _opacity_facts
from test_boundary_types_contained_mapping import _commit_report_fixture
from test_contract_model import VALIDATOR
from test_html_report import _native_audit

from archkeel.ir.codec import (
    contract_bytes,
    contract_digest,
    decode_canonical_model,
    parse_contract,
    parse_observation,
)
from archkeel.ir.model import stable_id
from archkeel.ir.trace import trace_valid_violations
from archkeel.ir.widening import contract_widenings

_ANNOTATION = "dict[str, list[object]] | None"


def _fixture(
    root: Path,
    annotation: str = _ANNOTATION,
    *,
    depth: int = 2,
    position: str = "return",
    facade: bool = False,
    value: bool = True,
    outer: bool = True,
    signature: str = "Envelope",
    route: str = "Detail",
    prefix: str = "",
    extra_declared: tuple[str, ...] = (),
    change: dict[str, object] | None = None,
) -> None:
    selector = {
        "qualified_name": f"sample.app{'' if facade else '.impl'}.run",
        "position": position,
        "field_path": "result.payload",
        "annotation": annotation,
    }
    declaration = (
        f"def run() -> {signature}: pass\n"
        if position == "return"
        else f"def run(value: {signature}) -> None: pass\n"
    )
    _app(
        root,
        source=(
            prefix
            + "class Detail:\n"
            + f"    payload: {annotation}\n"
            + "    control: dict[str, int]\n    uncertain: Missing\n\n"
            + f"class Envelope:\n    result: {route}\n\n"
            + declaration
        ),
        declared=(
            "sample.app.impl:Detail",
            "sample.app.impl:Envelope",
            *extra_declared,
            f"sample.app{'' if facade else '.impl'}:run",
        ),
        allowances=(
            *((selector,) if outer else ()),
            *(({**selector, "container_depth": depth, **(change or {})},) if value else ()),
        ),
    )
    if facade:
        (root / "sample/app/__init__.py").write_text("from .impl import run\n__all__ = ['run']\n")
    (root / "archkeel.toml").write_text(
        '[scan]\nroots = ["."]\nnamespace = "sample"\ncontract = "contract.json"\n'
    )


@pytest.mark.parametrize("facade", [False, True], ids=["direct", "facade"])
@pytest.mark.parametrize("position", ["return", "value"])
@pytest.mark.parametrize(
    ("annotation", "signature", "depth"),
    [
        ("dict[str, object]", "Envelope", 1),
        ("list[dict[str, object]]", "Envelope", 2),
        (_ANNOTATION, "Envelope", 2),
        (_ANNOTATION, "list[Envelope]", 3),
    ],
)
def test_exact_native_dto_field_keeps_siblings_unknown_and_legacy_ids(
    tmp_path: Path, facade: bool, position: str, annotation: str, signature: str, depth: int
) -> None:
    options = dict(facade=facade, position=position, signature=signature, depth=depth)
    _fixture(tmp_path, annotation, value=False, **options)
    before = _observe(tmp_path)
    assert before.observation is not None
    [sibling] = [
        r
        for r in trace_valid_violations(before.observation)
        if r.data.get("path") == f"{position}.result.control"
    ]
    [outer] = [
        r
        for r in before.observation.records("typing_signals") or ()
        if r.kind == "boundary_type_allowance"
    ]
    _fixture(tmp_path, annotation, **options)
    result = _observe(tmp_path)
    assert result.observation is not None and result.diagnostics == ()
    assert trace_valid_violations(result.observation) == (sibling,)
    assert outer in result.observation.records("typing_signals")
    assert before.observation.records("unknowns") == result.observation.records("unknowns")
    [fact] = _opacity_facts(result)
    assert fact.data.get("field_path") == "result.payload"
    assert fact.data.get("annotation") == annotation
    assert fact.data.get("nested_annotation") == "object"
    assert fact.data.get("container_depth") == depth
    assert fact.provenance == ("docs/architecture/sample.md",)
    assert fact.evidence_ids and fact.fact_ids and fact.rule_ids == ("APP-TYPES-NOT-DICT",)
    assert "accepted opacity" in fact.title and "type closure remains unproven" in fact.title
    [leaf] = [
        r
        for r in trace_valid_violations(before.observation)
        if r.data.get("path") == f"{position}.result.payload"
    ]
    assert fact.id == stable_id(
        "TYPE",
        "APP-TYPES-NOT-DICT",
        leaf.id,
        fact.data.get("qualified_name"),
        position,
        "result.payload",
        annotation,
        str(depth),
    )
    repeated = _observe(tmp_path)
    assert repeated.observation is not None
    assert trace_valid_violations(repeated.observation) == (sibling,)
    assert _opacity_facts(repeated) == [fact]


@pytest.mark.parametrize(
    "change",
    [
        {"qualified_name": "sample.app.impl.other"},
        {"position": "value"},
        {"field_path": "payload"},
        {"field_path": "result.control"},
        {"annotation": "Envelope"},
        {"annotation": "object"},
        {"annotation": "dict[str, list[object]]"},
        {"annotation": "dict[int, list[object]] | None"},
        {"annotation": "dict[str,list[object]] | None"},
        {"annotation": "dict[str, list[list[object]]] | None"},
        {"container_depth": 1},
        {"container_depth": 3},
    ],
)
def test_native_dto_field_rejects_inexact_coordinates(tmp_path: Path, change) -> None:
    _fixture(tmp_path, change=change)
    result = _observe(tmp_path)
    assert result.observation is not None
    assert len(trace_valid_violations(result.observation)) == 2
    assert _opacity_facts(result) == []


@pytest.mark.parametrize(
    ("annotation", "prefix", "depth"),
    [
        ("Raw", f"Raw = {_ANNOTATION}\n", 2),
        ("dict[str, Values]", "Values = list[object]\n", 2),
        ("dict[str, list[Native]]", "Native = object\n", 2),
        ("dict[str, object] | dict[int, object]", "", 1),
        ("dict[object, object]", "", 1),
        ("tuple[dict[str, object], dict[str, object]]", "", 2),
        ("dict[str, list[object]] | list[list[object]]", "", 2),
        ("dict[str, tuple[object, ...]]", "", 2),
        ("dict[str, Iterable[object]]", "from collections.abc import Iterable\n", 2),
        ("dict[str, list[list[object]]]", "", 3),
        ("dict[str, list[object | None]]", "", 2),
        (_ANNOTATION, "class list: pass\n", 2),
        (_ANNOTATION, "class object: pass\n", 2),
        (_ANNOTATION, "from builtins import list\nfrom typing import List as list\n", 2),
        (_ANNOTATION, "from missing import *\n", 2),
    ],
)
def test_native_dto_field_requires_one_literal_proven_value(
    tmp_path: Path, annotation: str, prefix: str, depth: int
) -> None:
    _fixture(tmp_path, annotation, prefix=prefix, depth=depth)
    result = _observe(tmp_path)
    assert result.observation is not None
    assert _opacity_facts(result) == []
    assert trace_valid_violations(result.observation) or result.observation.records("unknowns")


@pytest.mark.parametrize("other", [_ANNOTATION, "int", "Missing", "object"])
def test_same_path_declarations_stay_ambiguous_even_without_duplicate_findings(
    tmp_path: Path, other: str
) -> None:
    _fixture(
        tmp_path,
        route="Detail | Other",
        prefix=f"class Other:\n    payload: {other}\n",
        extra_declared=("sample.app.impl:Other",),
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    assert _opacity_facts(result) == []
    assert any(
        r.data.get("path") == "return.result.payload"
        and r.data.get("nested_annotation") == "object"
        for r in trace_valid_violations(result.observation)
    )


def test_native_dto_value_permission_keeps_outer_map_and_object_key(tmp_path: Path) -> None:
    _fixture(tmp_path, "dict[object, list[object]]", outer=False)
    result = _observe(tmp_path)
    assert result.observation is not None
    selected = [
        r
        for r in trace_valid_violations(result.observation)
        if r.data.get("path") == "return.result.payload"
    ]
    assert {
        (r.data.get("nested_annotation"), r.data.get("container_depth", 0)) for r in selected
    } == {("dict[object, list[object]]", 0), ("object", 1)}
    assert len(_opacity_facts(result)) == 1


def test_nullable_dto_value_keeps_an_unknown_member(tmp_path: Path) -> None:
    _fixture(tmp_path, "dict[str, list[object]] | Missing | None")
    result = _observe(tmp_path)
    assert result.observation is not None
    assert len(_opacity_facts(result)) == 1
    assert any(
        r.kind == "boundary_type_position" and r.data.get("path") == "return.result.payload"
        for r in result.observation.records("unknowns") or ()
    )


def test_native_dto_value_accepts_proven_optional_and_builtin_imports(tmp_path: Path) -> None:
    _fixture(
        tmp_path,
        "Optional[dict[str, list[object]]]",
        prefix="from typing import Optional\nfrom builtins import list\n",
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    assert len(_opacity_facts(result)) == 1
    [sibling] = trace_valid_violations(result.observation)
    assert sibling.data.get("path") == "return.result.control"


def test_native_dto_value_does_not_cross_a_dto_alias(tmp_path: Path) -> None:
    _fixture(tmp_path, route="Alias", prefix="Alias = Detail\n")
    result = _observe(tmp_path)
    assert result.observation is not None
    assert _opacity_facts(result) == []


def test_native_dto_value_keeps_an_identical_sibling_field(tmp_path: Path) -> None:
    _fixture(tmp_path, value=False)
    source = tmp_path / "sample/app/impl.py"
    source.write_text(
        source.read_text().replace("control: dict[str, int]", f"control: {_ANNOTATION}")
    )
    before = _observe(tmp_path)
    assert before.observation is not None
    siblings = tuple(
        r
        for r in trace_valid_violations(before.observation)
        if r.data.get("path") == "return.result.control"
    )
    assert len(siblings) == 2
    contract = tmp_path / "contract.json"
    raw = json.loads(contract.read_text())
    positions = raw["rules"][0]["allowed_positions"]
    positions.append({**positions[0], "container_depth": 2})
    contract.write_text(json.dumps(raw))
    result = _observe(tmp_path)
    assert result.observation is not None
    assert trace_valid_violations(result.observation) == siblings
    assert len(_opacity_facts(result)) == 1


def test_dto_depth_roundtrips_and_remains_a_widening(tmp_path: Path) -> None:
    _fixture(tmp_path)
    raw = json.loads((tmp_path / "contract.json").read_text())
    assert not list(VALIDATOR.iter_errors(raw))
    after = parse_contract(raw)
    assert parse_contract(json.loads(contract_bytes(after))) == after
    raw["rules"][0]["allowed_positions"].pop()
    before = parse_contract(raw)
    [widening] = contract_widenings(before, after)
    assert "result.payload" in widening and "container_depth=2" in widening
    assert contract_widenings(after, before) == ()
    assert contract_digest(before) != contract_digest(after)
    raw = json.loads(contract_bytes(after))
    raw["rules"][0]["allowed_positions"][1]["container_depth"] = 3
    assert contract_widenings(after, parse_contract(raw))


@pytest.mark.parametrize("facade", [False, True], ids=["direct", "facade"])
@pytest.mark.parametrize("depth", [2, 1], ids=["exact", "wrong-depth"])
def test_native_dto_value_survives_ordinary_cli_and_report(
    tmp_path: Path, facade: bool, depth: int
) -> None:
    _fixture(tmp_path, facade=facade, depth=depth)
    _observe(tmp_path)
    _commit_report_fixture(tmp_path)
    output = tmp_path / "architecture.json"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "from archkeel.cli import main; raise SystemExit(main())",
            "report",
            "--root",
            str(tmp_path),
            "--output",
            str(output),
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["coverage"]["status"] == "PASS" and summary["diagnostics"] == []
    assert summary["declared_rules"] == "FAIL"
    observation = parse_observation(decode_canonical_model(json.loads(output.read_text())))
    findings = trace_valid_violations(observation)
    facts = [
        r
        for r in observation.records("typing_signals") or ()
        if r.kind == "boundary_type_allowance" and r.data.get("accepted_opacity") is True
    ]
    _native_audit(output.with_suffix(".report.html").read_text(), observation, output.name)
    assert any(r.data.get("path") == "return.result.control" for r in findings)
    assert any(
        r.kind == "boundary_type_position" and r.data.get("path") == "return.result.uncertain"
        for r in observation.records("unknowns") or ()
    )
    if depth == 2:
        assert len(findings) == 1 and len(facts) == 1
        assert facts[0].data.get("field_path") == "result.payload"
        assert facts[0].data.get("container_depth") == 2 and facts[0].provenance
    else:
        assert len(findings) == 2 and facts == []
        assert any(r.data.get("container_depth") == 2 for r in findings)

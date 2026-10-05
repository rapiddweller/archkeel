# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Exact native list leaves retain their mapping owner and neighboring findings."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from test_analyzer import _observe
from test_boundary_type_opaque_map_values import _app, _opacity_facts
from test_boundary_types_contained_mapping import _commit_report_fixture

from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.trace import trace_valid_violations

_ANNOTATION = "dict[str, list[object]]"


def _fixture(
    root: Path,
    *,
    facade: bool = False,
    value: bool = True,
    annotation: str = _ANNOTATION,
    prefix: str = "",
    class_body: str = "",
    change: dict[str, object] | None = None,
) -> None:
    qualified_name = f"sample.app{'' if facade else '.impl'}.Capture.get_result"
    outer = {"qualified_name": qualified_name, "position": "return", "annotation": annotation}
    _app(
        root,
        source=(
            prefix
            + "class Capture:\n"
            + class_body
            + f"    def get_result(self) -> {annotation}: return {{}}\n"
            "    def fixed_control(self, counts: dict[str, int]) -> None: pass\n"
        ),
        declared=(f"sample.app{'' if facade else '.impl'}:Capture",),
        allowances=(outer, {**outer, "container_depth": 2, **(change or {})})
        if value
        else (outer,),
    )
    if facade:
        (root / "sample/app/__init__.py").write_text(
            "from .impl import Capture\n__all__ = ['Capture']\n"
        )
    (root / "archkeel.toml").write_text(
        '[scan]\nroots = ["."]\nnamespace = "sample"\ncontract = "contract.json"\n'
    )


@pytest.mark.parametrize("facade", [False, True], ids=["direct", "facade"])
def test_native_list_leaf_keeps_the_fixed_control_and_accepted_opacity(
    tmp_path: Path, facade: bool
) -> None:
    _fixture(tmp_path, facade=facade, value=False)
    control = _observe(tmp_path)
    assert control.observation is not None
    [sibling] = [
        item
        for item in trace_valid_violations(control.observation)
        if str(item.data.get("qualified_name")).endswith(".fixed_control")
    ]
    _fixture(tmp_path, facade=facade)
    result = _observe(tmp_path)
    assert result.observation is not None and result.diagnostics == ()
    assert trace_valid_violations(result.observation) == (sibling,)
    [fact] = _opacity_facts(result)
    assert fact.data.get("annotation") == _ANNOTATION
    assert fact.data.get("nested_annotation") == "object"
    assert fact.data.get("container_depth") == 2
    assert fact.provenance == ("docs/architecture/sample.md",)
    assert fact.evidence_ids and fact.fact_ids and fact.rule_ids == ("APP-TYPES-NOT-DICT",)
    assert "accepted opacity" in fact.title and "type closure remains unproven" in fact.title


@pytest.mark.parametrize("facade", [False, True], ids=["direct", "facade"])
def test_native_list_leaf_survives_the_ordinary_cli_and_report(
    tmp_path: Path, facade: bool
) -> None:
    _fixture(tmp_path, facade=facade)
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
    [sibling] = trace_valid_violations(observation)
    assert str(sibling.data.get("qualified_name")).endswith(".fixed_control")
    [fact] = [
        item
        for item in observation.records("typing_signals") or ()
        if item.kind == "boundary_type_allowance" and item.data.get("accepted_opacity") is True
    ]
    assert fact.data.get("container_depth") == 2 and fact.provenance
    html = output.with_suffix(".report.html").read_text()
    assert "accepted opacity" in html and "type closure remains unproven" in html
    assert "container depth 2" in html


@pytest.mark.parametrize(
    "change",
    [
        {"qualified_name": "sample.app.impl.Capture.fixed_control"},
        {"position": "counts"},
        {"annotation": "object"},
        {"annotation": "dict[int, list[object]]"},
        {"annotation": "dict[str,list[object]]"},
        {"annotation": "dict[str, list[list[object]]]"},
        {"container_depth": 1},
        {"container_depth": 3},
    ],
    ids=[
        "symbol",
        "position",
        "leaf-spelling",
        "key",
        "full-spelling",
        "nesting",
        "shallow",
        "deep",
    ],
)
def test_native_list_leaf_rejects_an_inexact_coordinate(tmp_path: Path, change) -> None:
    _fixture(tmp_path, change=change)
    result = _observe(tmp_path)
    assert result.observation is not None
    assert len(trace_valid_violations(result.observation)) == 2
    assert _opacity_facts(result) == []


@pytest.mark.parametrize(
    ("annotation", "prefix", "class_body", "depth"),
    [
        ("Raw", f"Raw = {_ANNOTATION}\n", "", 2),
        ("dict[str, Values]", "Values = list[object]\n", "", 2),
        ("dict[str, list[Payload]]", "Payload = object\n", "", 2),
        ("tuple[dict[str, list[object]], dict[str, list[object]]]", "", "", 3),
        ("tuple[dict[str, list[object]], list[list[object]]]", "", "", 3),
        ("dict[str, tuple[list[object], list[object]]]", "", "", 3),
        ("dict[str, list[list[object]]]", "", "", 3),
        ("dict[str, list[object | None]]", "", "", 2),
        (_ANNOTATION, "class list: pass\n", "", 2),
        (_ANNOTATION, "class Hidden: pass\nlist = Hidden\n", "", 2),
        (_ANNOTATION, "from builtins import list\nfrom typing import List as list\n", "", 2),
        (_ANNOTATION, "class Hidden: pass\n", "    list = Hidden\n", 2),
        (_ANNOTATION, "class object: pass\n", "", 2),
        (_ANNOTATION, "object = Missing\n", "", 2),
        (_ANNOTATION, "from builtins import object\nfrom typing import Any as object\n", "", 2),
        (_ANNOTATION, "class Hidden: pass\n", "    object = Hidden\n", 2),
        (_ANNOTATION, "from missing import *\n", "", 2),
        (_ANNOTATION, "class Hidden: pass\nif condition: list = Hidden\n", "", 2),
        (_ANNOTATION, "class Hidden: pass\nfor list in (): pass\n", "", 2),
        (_ANNOTATION, "class Hidden: pass\n", "    def list(self): pass\n", 2),
        (_ANNOTATION, "class Hidden: pass\n", "    def object(self): pass\n", 2),
    ],
)
def test_native_list_leaf_requires_one_literal_proven_value(
    tmp_path: Path, annotation: str, prefix: str, class_body: str, depth: int
) -> None:
    _fixture(
        tmp_path,
        annotation=annotation,
        prefix=prefix,
        class_body=class_body,
        change={"container_depth": depth},
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    assert _opacity_facts(result) == []
    assert trace_valid_violations(result.observation) or result.observation.records("unknowns")


@pytest.mark.parametrize("neighbor", ["None", "Missing"])
def test_native_list_leaf_keeps_nullable_and_unknown_neighbors(
    tmp_path: Path, neighbor: str
) -> None:
    _fixture(tmp_path, annotation=f"{_ANNOTATION} | {neighbor}")
    result = _observe(tmp_path)
    assert result.observation is not None
    [sibling] = trace_valid_violations(result.observation)
    assert str(sibling.data.get("qualified_name")).endswith(".fixed_control")
    [fact] = _opacity_facts(result)
    assert fact.data.get("annotation") == f"{_ANNOTATION} | {neighbor}"
    assert fact.data.get("container_depth") == 2
    positions = [
        item
        for item in result.observation.records("unknowns") or ()
        if item.kind == "boundary_type_position"
    ]
    assert bool(positions) == (neighbor == "Missing")


def test_native_list_leaf_requires_a_proven_builtin_import(tmp_path: Path) -> None:
    _fixture(tmp_path, prefix="from builtins import list\n")
    result = _observe(tmp_path)
    assert result.observation is not None
    [sibling] = trace_valid_violations(result.observation)
    assert str(sibling.data.get("qualified_name")).endswith(".fixed_control")
    assert len(_opacity_facts(result)) == 1


def test_native_list_value_permission_keeps_its_outer_map_checked(tmp_path: Path) -> None:
    _fixture(tmp_path)
    contract_path = tmp_path / "contract.json"
    contract = json.loads(contract_path.read_text())
    rule = next(item for item in contract["rules"] if item["id"] == "APP-TYPES-NOT-DICT")
    rule["allowed_positions"] = rule["allowed_positions"][1:]
    contract_path.write_text(json.dumps(contract))
    result = _observe(tmp_path)
    assert result.observation is not None
    findings = trace_valid_violations(result.observation)
    assert len(findings) == 2
    [getter] = [item for item in findings if item.data.get("position") == "return"]
    assert getter.data.get("annotation") == _ANNOTATION
    assert getter.data.get("nested_annotation") == _ANNOTATION
    assert getter.data.get("reason") == "instead of a typed model"
    assert len(_opacity_facts(result)) == 1

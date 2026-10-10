# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Native Properties unions need proven alternatives, not a looser map count."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from test_analyzer import _observe
from test_boundary_type_opaque_map_values import _app, _opacity_facts
from test_boundary_types_contained_mapping import _commit_report_fixture
from test_html_report import _native_audit

from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.trace import trace_valid_violations

_ANNOTATION = "dict[str, str] | dict[str, object] | None"


def _fixture(
    root: Path,
    *,
    dto: bool,
    annotation: str = _ANNOTATION,
    prefix: str = "",
    outer: bool = True,
    value: bool = True,
    depth: int = 1,
    signature: str = "Request",
    change: dict[str, object] | None = None,
) -> None:
    selector = {
        "qualified_name": "sample.app.impl.run",
        "position": "request" if dto else "properties",
        "field_path": "properties" if dto else "",
        "annotation": annotation,
    }
    source = (
        f"class Request:\n    properties: {annotation}\n"
        "    control: dict[str, int]\n    uncertain: Missing\n"
        f"def run(request: {signature}) -> None: pass\n"
        if dto
        else f"def run(properties: {annotation}, control: dict[str, int], uncertain: Missing)"
        " -> None: pass\n"
    )
    _app(
        root,
        source=prefix + source,
        declared=("sample.app.impl:run", *(("sample.app.impl:Request",) if dto else ())),
        allowances=(
            *(({**selector, **(change or {})},) if outer else ()),
            *(({**selector, "container_depth": depth, **(change or {})},) if value else ()),
        ),
    )
    (root / "archkeel.toml").write_text(
        '[scan]\nroots = ["."]\nnamespace = "sample"\ncontract = "contract.json"\n'
    )
    (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')


@pytest.mark.parametrize("dto", [False, True], ids=["direct", "dto-field"])
@pytest.mark.parametrize("nullable", [False, True], ids=["required", "nullable"])
def test_exact_alternative_maps_need_separate_outer_and_native_value_permissions(
    tmp_path: Path, dto: bool, nullable: bool
) -> None:
    annotation = _ANNOTATION if nullable else "dict[str, str] | dict[str, object]"
    _fixture(tmp_path, dto=dto, annotation=annotation, outer=False, value=False)
    baseline = _observe(tmp_path)
    assert baseline.observation is not None and baseline.diagnostics == ()
    findings = trace_valid_violations(baseline.observation)
    [control] = [
        item
        for item in findings
        if item.data.get("position") == "control" or item.data.get("path") == "request.control"
    ]
    selected = tuple(item for item in findings if item != control)
    assert len(selected) == 3
    assert {item.data.get("nested_annotation") for item in selected} == {
        "dict[str, str]",
        "dict[str, object]",
        "object",
    }

    _fixture(tmp_path, dto=dto, annotation=annotation, value=False)
    outer_only = _observe(tmp_path)
    assert outer_only.observation is not None
    [leaf] = [item for item in selected if item.data.get("nested_annotation") == "object"]
    assert set(trace_valid_violations(outer_only.observation)) == {control, leaf}
    outer_facts = tuple(
        item
        for item in outer_only.observation.records("typing_signals") or ()
        if item.kind == "boundary_type_allowance"
    )
    assert len(outer_facts) == 2
    assert {item.data.get("nested_annotation") for item in outer_facts} == {
        "dict[str, str]",
        "dict[str, object]",
    }
    assert _opacity_facts(outer_only) == []

    _fixture(tmp_path, dto=dto, annotation=annotation, outer=False)
    value_only = _observe(tmp_path)
    assert value_only.observation is not None
    assert set(trace_valid_violations(value_only.observation)) == set(findings) - {leaf}
    assert len(_opacity_facts(value_only)) == 1

    _fixture(tmp_path, dto=dto, annotation=annotation)
    result = _observe(tmp_path)
    assert result.observation is not None and result.diagnostics == ()
    assert trace_valid_violations(result.observation) == (control,)
    assert result.observation.records("unknowns") == baseline.observation.records("unknowns")
    facts = result.observation.records("typing_signals") or ()
    assert all(fact in facts for fact in outer_facts)
    [fact] = _opacity_facts(result)
    assert fact.data.get("annotation") == annotation
    assert fact.data.get("field_path") == ("properties" if dto else "")
    assert fact.data.get("container_depth") == 1
    assert fact.data.get("nested_annotation") == "object"
    assert fact.provenance == ("docs/architecture/sample.md",)
    assert fact.evidence_ids and fact.fact_ids
    assert "accepted opacity" in fact.title and "type closure remains unproven" in fact.title
    repeated = _observe(tmp_path)
    assert repeated.observation is not None
    assert repeated.observation.records("typing_signals") == facts
    assert trace_valid_violations(repeated.observation) == (control,)


@pytest.mark.parametrize("dto", [False, True], ids=["direct", "dto-field"])
@pytest.mark.parametrize(
    ("annotation", "prefix"),
    [
        ("dict[str, dict[str, object]]", ""),
        ("tuple[dict[str, str], dict[str, object]]", ""),
        ("dict[str, str] | dict[str, dict[str, object]]", ""),
        ("dict[str, object] | dict[int, object]", ""),
        ("dict[str, str] | dict[str, object] | dict[str, object]", ""),
        ("dict[str, str] | dict[str, object] | Missing", ""),
        ("dict[str, str] | dict[object, object]", ""),
        ("dict[str, object] | dict[str, Missing]", ""),
        ("dict[str, object] | dict[str, str | Missing]", ""),
        ("list[dict[str, str] | dict[str, object]]", ""),
        ("tuple[dict[str, str] | dict[str, object], dict[str, int]]", ""),
        ("dict[str, object] | Strings", "Strings = dict[str, str]\n"),
        ("dict[str, object] | dict[str, String]", "String = str\n"),
        ("dict[str, str] | dict[str, Native]", "Native = object\n"),
        ("Properties", f"Properties = {_ANNOTATION}\n"),
        (_ANNOTATION, "from missing import *\n"),
        (_ANNOTATION, "class dict: pass\n"),
        (_ANNOTATION, "class str: pass\n"),
        ("Union[dict[str, str], dict[str, object]]", "from typing import Union\nUnion = object\n"),
        (
            "Optional[dict[str, str] | dict[str, object]]",
            "from typing import Optional\nclass Optional: pass\n",
        ),
        (
            "Union[dict[str, str], dict[str, object]]",
            "from typing import Union\nfrom missing import *\n",
        ),
    ],
)
def test_alternative_native_map_permission_rejects_unproven_or_simultaneous_maps(
    tmp_path: Path, dto: bool, annotation: str, prefix: str
) -> None:
    _fixture(tmp_path, dto=dto, annotation=annotation, prefix=prefix, outer=False, value=False)
    before = _observe(tmp_path)
    assert before.observation is not None
    _fixture(tmp_path, dto=dto, annotation=annotation, prefix=prefix)
    result = _observe(tmp_path)
    assert result.observation is not None
    assert _opacity_facts(result) == []
    assert trace_valid_violations(result.observation) or result.observation.records("unknowns")
    if annotation != "dict[str, dict[str, object]]":
        assert trace_valid_violations(result.observation) == trace_valid_violations(
            before.observation
        )
        assert not any(
            item.kind == "boundary_type_allowance"
            for item in result.observation.records("typing_signals") or ()
        )


@pytest.mark.parametrize("dto", [False, True], ids=["direct", "dto-field"])
@pytest.mark.parametrize(
    "change",
    [
        {"qualified_name": "sample.app.impl.other"},
        {"position": "other"},
        {"field_path": "other"},
        {"annotation": "dict[str, object] | None"},
        {"annotation": "dict[str,str] | dict[str,object] | None"},
        {"container_depth": 2},
    ],
)
def test_alternative_maps_keep_exact_selector_coordinates(
    tmp_path: Path, dto: bool, change: dict[str, object]
) -> None:
    _fixture(tmp_path, dto=dto, outer=False, value=False)
    before = _observe(tmp_path)
    assert before.observation is not None
    _fixture(tmp_path, dto=dto, outer="container_depth" not in change, change=change)
    after = _observe(tmp_path)
    assert after.observation is not None
    assert trace_valid_violations(after.observation) == trace_valid_violations(before.observation)
    assert _opacity_facts(after) == []


@pytest.mark.parametrize("other", [_ANNOTATION, "Missing", "object", "int"])
def test_same_field_reached_from_two_declarations_does_not_gain_union_permission(
    tmp_path: Path,
    other: str,
) -> None:
    _fixture(tmp_path, dto=True)
    source = tmp_path / "sample/app/impl.py"
    source.write_text(
        source.read_text().replace(
            "def run(request: Request)",
            f"class Other:\n    properties: {other}\n\ndef run(request: Request | Other)",
        )
    )
    contract = tmp_path / "contract.json"
    raw = json.loads(contract.read_text())
    raw["components"][0]["public"].append("sample.app.impl:Other")
    contract.write_text(json.dumps(raw))
    result = _observe(tmp_path)
    assert result.observation is not None
    assert _opacity_facts(result) == []
    assert result.observation.records("unknowns")


@pytest.mark.parametrize("dto", [False, True], ids=["direct", "dto-field"])
@pytest.mark.parametrize(
    ("annotation", "prefix", "depth"),
    [
        ("dict[str, object] | (dict[str, str] | None)", "", 1),
        ("Union[dict[str, str], dict[str, object], None]", "from typing import Union\n", 1),
        ("Optional[dict[str, str] | dict[str, object]]", "from typing import Optional\n", 1),
        ("typing.Union[dict[str, str], dict[str, object]]", "import typing\n", 1),
        ("dict[str, str] | dict[str, list[object]] | None", "", 2),
    ],
)
def test_alternative_maps_use_proven_syntax_and_existing_native_value_shapes(
    tmp_path: Path, dto: bool, annotation: str, prefix: str, depth: int
) -> None:
    _fixture(tmp_path, dto=dto, annotation=annotation, prefix=prefix, depth=depth)
    result = _observe(tmp_path)
    assert result.observation is not None
    [control] = trace_valid_violations(result.observation)
    assert (
        control.data.get("position") == "control" or control.data.get("path") == "request.control"
    )
    [leaf] = _opacity_facts(result)
    assert leaf.data.get("annotation") == annotation
    assert leaf.data.get("container_depth") == depth


def test_union_field_depth_counts_a_container_before_the_dto(tmp_path: Path) -> None:
    _fixture(tmp_path, dto=True, signature="list[Request]", depth=2)
    result = _observe(tmp_path)
    assert result.observation is not None
    [control] = trace_valid_violations(result.observation)
    assert control.data.get("path") == "request.control"
    [leaf] = _opacity_facts(result)
    assert leaf.data.get("container_depth") == 2
    assert leaf.data.get("field_path") == "properties"


@pytest.mark.parametrize("dto", [False, True], ids=["direct", "dto-field"])
def test_alternative_maps_survive_ordinary_cli_reports_with_stable_facts(
    tmp_path: Path, dto: bool
) -> None:
    _fixture(tmp_path, dto=dto)
    _commit_report_fixture(tmp_path)
    observations = []
    for index in range(2):
        output = tmp_path / f"architecture-{index}.json"
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
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        summary = json.loads(result.stdout)
        assert summary["coverage"]["status"] == "PASS" and summary["diagnostics"] == []
        observation = parse_observation(decode_canonical_model(json.loads(output.read_text())))
        [control] = trace_valid_violations(observation)
        assert (
            control.data.get("position") == "control"
            or control.data.get("path") == "request.control"
        )
        facts = tuple(
            item
            for item in observation.records("typing_signals") or ()
            if item.kind == "boundary_type_allowance"
        )
        assert len(facts) == 3
        assert sum(item.data.get("accepted_opacity") is True for item in facts) == 1
        assert sum("alternative mapping" in item.title for item in facts) == 2
        _native_audit(output.with_suffix(".report.html").read_text(), observation, output.name)
        observations.append((facts, observation.records("unknowns"), control))
    assert observations[0] == observations[1]

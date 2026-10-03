# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Issue #226: allow one exact mapping occurrence inside a typed signature container."""

from __future__ import annotations

import json
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest
from test_analyzer import _observe
from test_boundary_types_nested_dtos import _type_unknowns, _write_app

from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.check.run import inspect_observation
from archkeel.cli.observe import observe
from archkeel.ir.codec import (
    decode_canonical_model,
    observation_payload,
    parse_contract,
    parse_observation,
)
from archkeel.ir.trace import trace_valid_violations
from archkeel.render.html import render_html

QUALNAME = "sample.app.impl.read_csv_having_weight_column"
CONTAINED_ANNOTATION = "tuple[list[float], list[dict[str, str]]]"
_ALLOWANCE = {
    "qualified_name": QUALNAME,
    "position": "return",
    "field_path": "",
    "annotation": CONTAINED_ANNOTATION,
}


def _observe_signature(
    root: Path,
    implementation: str,
    allowance: dict[str, object] | None,
    *,
    declared: tuple[str, ...] = ("sample.app.impl:read_csv_having_weight_column",),
    extra_files: dict[str, str] | None = None,
):
    _write_app(
        root,
        implementation=implementation,
        declared=declared,
        allowed_positions=() if allowance is None else (allowance,),
    )
    for relative, content in (extra_files or {}).items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return _observe(root)


def _real_signature(annotation: str = CONTAINED_ANNOTATION) -> str:
    return f"def read_csv_having_weight_column() -> {annotation}:\n    return ([], [])\n"


def _commit_report_fixture(root: Path) -> None:
    for args in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "test@example.invalid"],
        ["git", "config", "user.name", "Archkeel test"],
        ["git", "add", "-A"],
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "report fixture"],
    ):
        subprocess.run(args, cwd=root, check=True, capture_output=True)


def _allowance_facts(result):
    assert result.observation is not None
    return [
        item
        for item in result.observation.records("typing_signals") or ()
        if item.kind == "boundary_type_allowance"
    ]


class _VisibleHTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.in_script = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script":
            self.in_script = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self.in_script = False

    def handle_data(self, data: str) -> None:
        if not self.in_script:
            self.parts.append(data)


def test_unique_contained_map_is_allowed_with_precise_evidence_and_visible_report(
    tmp_path: Path,
) -> None:
    result = _observe_signature(tmp_path, _real_signature(), _ALLOWANCE)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    assert _type_unknowns(result) == []
    [fact] = _allowance_facts(result)
    assert fact.evidence_class.value == "FACT"
    assert fact.rule_ids == ("APP-TYPES-NOT-DICT",)
    assert fact.evidence_ids
    assert dict(fact.data.entries) == {
        "qualified_name": QUALNAME,
        "position": "return",
        "field_path": "",
        "annotation": CONTAINED_ANNOTATION,
        "nested_annotation": "dict[str, str]",
        "container_depth": 2,
    }
    assert "unique contained mapping" in fact.title.lower()

    payload = json.loads(json.dumps(observation_payload(result.observation)))
    [json_fact] = [
        item for item in payload["typing_signals"] if item["kind"] == "boundary_type_allowance"
    ]
    assert json_fact["data"] == dict(fact.data.entries)
    assert json_fact["rule_ids"] == ["APP-TYPES-NOT-DICT"]
    assert json_fact["evidence_ids"]

    _commit_report_fixture(tmp_path)
    report, architecture = run_report(
        tmp_path,
        config=ScanConfig((".",), "sample", "contract.json", "0" * 64),
        analyzer=observe,
    )
    assert architecture is not None
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))
    html = render_html(
        report, observation, repository="sample", architecture_href="architecture.json"
    ).decode()
    visible = _VisibleHTMLText()
    visible.feed(html)
    visible_text = " ".join(visible.parts)
    visible_lower = visible_text.lower()
    assert "unique contained mapping" in visible_lower
    assert "dict[str, str]" in visible_text
    assert "container depth" in visible_lower
    assert "2" in visible_text
    assert "exceptions" in visible_lower
    assert "other violations" in visible_lower
    assert "unknown" in visible_lower


@pytest.mark.parametrize(
    ("change", "source_annotation"),
    (
        ({"qualified_name": "sample.app.impl.other"}, CONTAINED_ANNOTATION),
        ({"position": "value"}, CONTAINED_ANNOTATION),
        ({"field_path": "rows"}, CONTAINED_ANNOTATION),
        ({"field_path": "1.0"}, CONTAINED_ANNOTATION),
        ({"field_path": "return[1][0]"}, CONTAINED_ANNOTATION),
        ({"annotation": "dict[str, str]"}, CONTAINED_ANNOTATION),
        ({}, "tuple[list[float], tuple[dict[str, str]]]"),
    ),
    ids=(
        "callable",
        "position",
        "dto-field",
        "numeric-field",
        "synthetic-path",
        "inner-map",
        "changed-route",
    ),
)
def test_contained_allowance_requires_exact_coordinates_and_full_annotation(
    tmp_path: Path, change: dict[str, str], source_annotation: str
) -> None:
    selector = {**_ALLOWANCE, **change}
    implementation = _real_signature(source_annotation)
    result = _observe_signature(tmp_path, implementation, selector)

    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    assert len(violations) == 1
    assert violations[0].data.get("qualified_name") == QUALNAME
    assert violations[0].data.get("position") == "return"
    assert violations[0].data.get("nested_annotation") == "dict[str, str]"
    assert _allowance_facts(result) == []


def test_two_identical_contained_maps_are_ambiguous_even_when_the_finding_deduplicates(
    tmp_path: Path,
) -> None:
    annotation = "tuple[list[dict[str, str]], list[dict[str, str]]]"
    selector = {**_ALLOWANCE, "annotation": annotation}
    result = _observe_signature(
        tmp_path,
        _real_signature(annotation),
        selector,
    )

    assert result.observation is not None
    [finding] = trace_valid_violations(result.observation)
    assert finding.data.get("nested_annotation") == "dict[str, str]"
    assert finding.data.get("container_depth") == 2
    assert _allowance_facts(result) == []


def test_two_distinct_contained_maps_are_ambiguous(tmp_path: Path) -> None:
    annotation = "tuple[list[dict[str, str]], list[dict[str, bytes]]]"
    selector = {**_ALLOWANCE, "annotation": annotation}
    result = _observe_signature(tmp_path, _real_signature(annotation), selector)

    assert result.observation is not None
    findings = trace_valid_violations(result.observation)
    assert {item.data.get("nested_annotation") for item in findings} == {
        "dict[str, str]",
        "dict[str, bytes]",
    }
    assert _allowance_facts(result) == []


def test_unique_map_allowance_keeps_a_second_known_broad_member(tmp_path: Path) -> None:
    annotation = "tuple[list[dict[str, str]], object]"
    selector = {**_ALLOWANCE, "annotation": annotation}
    result = _observe_signature(tmp_path, _real_signature(annotation), selector)

    assert result.observation is not None
    [finding] = trace_valid_violations(result.observation)
    assert finding.data.get("nested_annotation") == "object"
    [fact] = _allowance_facts(result)
    assert fact.data.get("nested_annotation") == "dict[str, str]"
    assert fact.data.get("container_depth") == 2


@pytest.mark.parametrize(
    ("annotation", "expected_nested_annotation"),
    (
        (
            "tuple[list[float], list[dict[str, MissingType]]]",
            "dict[str, MissingType]",
        ),
        (
            "tuple[list[float], list[dict[str, str]] | MissingType]",
            "dict[str, str]",
        ),
    ),
    ids=("unresolved-map-value", "unresolved-sibling-branch"),
)
def test_contained_allowance_preserves_unknown_member_verdict(
    tmp_path: Path, annotation: str, expected_nested_annotation: str
) -> None:
    selector = {**_ALLOWANCE, "annotation": annotation}
    result = _observe_signature(tmp_path, _real_signature(annotation), selector)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    [unknown] = _type_unknowns(result)
    assert unknown.data.get("reason") == "unresolved_name"
    [fact] = _allowance_facts(result)
    assert fact.data.get("nested_annotation") == expected_nested_annotation
    _, declared_rules = inspect_observation(result.observation)
    assert declared_rules == "UNKNOWN"


def test_none_union_member_is_not_a_second_mapping_candidate(tmp_path: Path) -> None:
    annotation = "list[dict[str, str]] | None"
    selector = {**_ALLOWANCE, "annotation": annotation}
    result = _observe_signature(tmp_path, _real_signature(annotation), selector)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    assert _type_unknowns(result) == []
    [fact] = _allowance_facts(result)
    assert fact.data.get("nested_annotation") == "dict[str, str]"


def test_named_alias_route_to_contained_map_is_not_allowed(tmp_path: Path) -> None:
    annotation = "tuple[list[float], Rows]"
    implementation = "Rows = list[dict[str, str]]\n\n" + _real_signature(annotation)
    selector = {**_ALLOWANCE, "annotation": annotation}
    result = _observe_signature(tmp_path, implementation, selector)

    assert result.observation is not None
    [finding] = trace_valid_violations(result.observation)
    assert finding.data.get("reason") == "instead of a typed model"
    assert finding.data.get("nested_annotation") == "dict[str, str]"
    assert _allowance_facts(result) == []


def test_standard_library_import_alias_route_to_mapping_is_allowed(tmp_path: Path) -> None:
    annotation = "tuple[list[float], list[M[str, str]]]"
    implementation = "from collections.abc import Mapping as M\n\n" + _real_signature(annotation)
    selector = {**_ALLOWANCE, "annotation": annotation}
    result = _observe_signature(tmp_path, implementation, selector)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    [fact] = _allowance_facts(result)
    assert fact.data.get("nested_annotation") == "M[str, str]"
    assert fact.data.get("container_depth") == 2


def test_aliases_inside_mapping_key_and_value_do_not_block_allowance(tmp_path: Path) -> None:
    annotation = "tuple[list[float], list[M[Key, Cell]]]"
    implementation = (
        "from collections.abc import Mapping as M\n"
        "Key = str\n"
        "Cell = str\n\n" + _real_signature(annotation)
    )
    selector = {**_ALLOWANCE, "annotation": annotation}
    result = _observe_signature(tmp_path, implementation, selector)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    [fact] = _allowance_facts(result)
    assert fact.data.get("nested_annotation") == "M[Key, Cell]"


def test_new_type_argument_path_coordinate_is_rejected(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        implementation=_real_signature(),
        declared=("sample.app.impl:read_csv_having_weight_column",),
        allowed_positions=(_ALLOWANCE,),
    )
    contract_path = tmp_path / "contract.json"
    raw = json.loads(contract_path.read_text())
    raw["rules"][0]["allowed_positions"][0]["type_argument_path"] = "1.0"

    with pytest.raises(ValueError):
        parse_contract(raw)


def test_inherited_generic_facade_contained_map_uses_the_same_exact_allowance(
    tmp_path: Path,
) -> None:
    annotation = "tuple[list[float], list[dict[str, str]]]"
    implementation = (
        "from typing import Generic, TypeVar\n"
        "T = TypeVar('T')\n"
        "class Base(Generic[T]):\n"
        f"    def read(self) -> {annotation}: ...\n\n"
        "class Payload: pass\n\n"
        "class Public(Base[Payload]):\n"
        "    pass\n"
    )
    selector = {
        "qualified_name": "sample.app.impl.Public.read",
        "position": "return",
        "field_path": "",
        "annotation": annotation,
    }
    result = _observe_signature(
        tmp_path,
        implementation,
        selector,
        declared=("sample.app.impl:Public",),
    )

    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    [fact] = _allowance_facts(result)
    assert fact.data.get("qualified_name") == "sample.app.impl.Public.read"
    assert fact.data.get("nested_annotation") == "dict[str, str]"
    assert fact.data.get("container_depth") == 2

# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""An unproven effective property retains its source-declared signature candidates."""

import json
from pathlib import Path

import pytest
from test_analyzer import _component
from test_inherited_properties import _validate
from test_inside_publication import _inside, _rule, _write_project
from test_recursive_inside_independent_contracts import _commit_tree, _scan_config

from archkeel.check.report import run_report
from archkeel.check.validation import run_validate
from archkeel.cli.observe import observe
from archkeel.ir.codec import canonical_report_bytes, decode_canonical_model, parse_observation
from archkeel.ir.measurements import compare_measurements
from archkeel.ir.trace import trace_valid_violations
from archkeel.render.html import render_html


def _candidates(observation):
    return tuple(
        record
        for record in observation.records("unknowns") or ()
        if record.kind == "boundary_type_position"
        and record.data.get("signature_scope") == "declared"
    )


@pytest.mark.parametrize("uncertainty", ["exec", "base"])
def test_owned_accessor_candidates_survive_the_issue_306_fixture(tmp_path: Path, uncertainty: str):
    source = (
        "class Child:\n"
        "    @property\n    def properties(self): ...\n"
        "    @properties.setter\n    def properties(self, value): ...\n"
        "    @property\n    def generators(self) -> dict: ...\n"
        "    @generators.setter\n    def generators(self, value) -> None: ...\n"
    )
    if uncertainty == "exec":
        source = "def execute(code: str) -> None:\n    exec(code)\n" + source
    else:
        source = source.replace("class Child:", "class Child(Missing):")
    result, report, observation = _validate(tmp_path, source)
    assert report.declared_rules == "UNKNOWN"
    assert result.exit_code == 0
    assert trace_valid_violations(observation) == ()
    candidates = _candidates(observation)
    assert len(candidates) == 6
    assert sorted(record.data.get("annotation") for record in candidates) == [
        "",
        "",
        "",
        "",
        "None",
        "dict",
    ]
    assert report.measurements.scalars.unknown_positions == 7
    assert len({record.id for record in candidates}) == 6
    assert all(len(record.fact_ids) == 2 and len(record.evidence_ids) == 2 for record in candidates)
    assert (
        _candidates(
            parse_observation(
                decode_canonical_model(json.loads(canonical_report_bytes(observation)))
            )
        )
        == candidates
    )
    html = render_html(
        report, observation, repository="fixture", architecture_href="report.json"
    ).decode()
    assert "effective binding UNKNOWN" in html
    assert "declared annotation dict" in html


@pytest.mark.parametrize("annotation", ["object", "Hidden", "int", ""])
@pytest.mark.parametrize("uncertainty", ["base", "exec", "hook", "method-decorator"])
def test_declared_candidates_cannot_prove_runtime_types(
    tmp_path: Path, annotation: str, uncertainty: str
):
    result_type = f" -> {annotation}" if annotation else ""
    source = (
        "class Hidden: pass\nclass Child:\n"
        f"    @property\n    def value(self){result_type}: ...\n"
        "    @value.setter\n    def value(self, new) -> None: ...\n"
    )
    if uncertainty == "exec":
        source = "def execute(code: str) -> None:\n    exec(code)\n" + source
    elif uncertainty == "base":
        source = source.replace("class Child:", "class Child(Missing):")
    elif uncertainty == "hook":
        source = source.replace("class Child:", "@transform\nclass Child:")
    else:
        source += "    @custom\n    def unrelated(self) -> int: ...\n"
    _, report, observation = _validate(tmp_path, source)
    assert report.declared_rules == "UNKNOWN"
    assert trace_valid_violations(observation) == ()
    candidates = _candidates(observation)
    assert len(candidates) == 3
    assert any(record.data.get("annotation") == annotation for record in candidates)
    assert all(not record.data.get("resolved_types") for record in candidates)


def test_repeated_source_owners_do_not_borrow_accessor_candidates(tmp_path: Path):
    body = (
        "class Child(Missing):\n    @property\n    def value(self) -> object: ...\n"
        "    @value.setter\n    def value(self, new: int) -> None: ...\n"
    )
    _, report, observation = _validate(tmp_path, body + body.replace("object", "int"))
    assert report.declared_rules == "UNKNOWN"
    assert trace_valid_violations(observation) == ()
    assert _candidates(observation) == ()


@pytest.mark.parametrize("uncertainty", ["exec", "base"])
def test_reexported_candidates_keep_the_defining_source(tmp_path: Path, uncertainty: str):
    defining = (
        "class Hidden: pass\nclass Child:\n"
        "    @property\n    def value(self) -> Hidden: ...\n"
        "    @value.setter\n    def value(self, new: int) -> None: ...\n"
    )
    if uncertainty == "exec":
        defining = "def execute(code: str) -> None:\n    exec(code)\n" + defining
    else:
        defining = defining.replace("class Child:", "class Child(Missing):")
    result, report, observation = _validate(
        tmp_path,
        'from .base import Child\n__all__ = ["Child"]\n',
        {"sample/base.py": defining},
    )
    assert result.declared_rules == report.declared_rules == "UNKNOWN"
    candidates = _candidates(observation)
    assert len(candidates) == 3
    assert all(
        record.data.get("qualified_name") == "sample.api.Child.value" for record in candidates
    )
    sources = {evidence.id: evidence for evidence in observation.evidence}
    symbols = {record.id: record for record in observation.records("symbols")}
    for candidate in candidates:
        assert {sources[identity].file for identity in candidate.evidence_ids} == {"sample/base.py"}
        assert {
            symbols[identity].data.get("qualified_name") for identity in candidate.fact_ids
        } == {"sample.base.Child", "sample.base.Child.value"}
    assert trace_valid_violations(observation) == ()
    assert all(not record.data.get("facade_types") for record in observation.records("symbols"))


def test_final_plain_method_does_not_retain_superseded_accessor_candidates(tmp_path: Path):
    source = (
        "class Child(Missing):\n"
        "    @property\n    def value(self) -> object: ...\n"
        "    @value.setter\n    def value(self, new: object) -> None: ...\n"
        "    def value(self) -> int: ...\n"
    )
    _, report, observation = _validate(tmp_path, source)
    assert report.declared_rules == "UNKNOWN"
    assert _candidates(observation) == ()
    assert trace_valid_violations(observation) == ()


@pytest.mark.parametrize("scope", ["inside", "allowed", "exact", "other"])
def test_candidates_respect_contract_scope_and_exemptions(tmp_path: Path, scope: str):
    rule = _rule("TYPES", "boundary_types", source="sample.api")
    if scope == "allowed":
        rule["allowed_sources"] = ["sample.api"]
    elif scope == "exact":
        rule["exact_sources"] = ["sample.api"]
    elif scope == "other":
        rule["source"] = "sample.other"
    component = _component("api", packages=["sample"], public=["sample.api:Child"])
    _write_project(
        tmp_path,
        components=[{**component, "public": [], "inside": "inside.json"}]
        if scope == "inside"
        else [component],
        rules=[] if scope == "inside" else [rule],
        insides={"inside.json": _inside([component], [rule])} if scope == "inside" else {},
        files={
            "sample/api.py": (
                "class Child(Missing):\n    @property\n    def value(self) -> object: ...\n"
                "    @value.setter\n    def value(self, new: int) -> None: ...\n"
            )
        },
    )
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (tmp_path / "docs/architecture/sample.md").write_text(
        "<!-- archkeel-component-graph -->\n```mermaid\ngraph TD\n```\n"
    )
    _commit_tree(tmp_path)
    validation, _ = run_validate(tmp_path, _scan_config(), observe)
    report, artifact = run_report(tmp_path, config=_scan_config(), analyzer=observe)
    assert artifact is not None, report.diagnostics
    observation = parse_observation(decode_canonical_model(json.loads(artifact)))
    candidates = _candidates(observation)
    if scope == "inside":
        assert len(candidates) == 3
        assert all(record.rule_ids == ("api:TYPES",) for record in candidates)
        assert validation.declared_rules == report.declared_rules == "UNKNOWN"
        assert report.measurements.scalars.unknown_positions == 4
    else:
        assert candidates == ()


def test_retained_positions_reach_the_existing_unknown_ratchet(tmp_path: Path):
    before = tmp_path / "before"
    before.mkdir()
    after = tmp_path / "after"
    after.mkdir()
    _, accepted, _ = _validate(before, "class Child(Missing): pass\n")
    _, candidate, _ = _validate(
        after,
        (
            "class Child(Missing):\n    @property\n    def value(self) -> object: ...\n"
            "    @value.setter\n    def value(self, new: int) -> None: ...\n"
        ),
    )
    rows = compare_measurements(accepted.measurements, candidate.measurements)
    assert ("unknown_positions", "1", "4", "FAIL") in rows

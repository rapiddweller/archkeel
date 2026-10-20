# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Call-argument receipts require coverage of the selected source domain."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_exact_module_ownership import _component, _observe_tree

from archkeel.check.report import run_saved_report
from archkeel.ir.codec import encode_canonical_model, observation_payload
from archkeel.ir.decisions import rule_assessments

_PROVENANCE = ["docs/architecture/sample.md"]


def _rule(source: str) -> dict[str, object]:
    return {
        "id": "FORBID-QUERY-LITERAL",
        "kind": "forbidden_call_argument",
        "source": source,
        "target": "sample.safe.storage.page",
        "parameter": "query",
        "rationale": "Query text must come from a selected typed argument.",
        "provenance": _PROVENANCE,
        "decided_by": "architect",
    }


def _contract(*, mounted: bool, source: str) -> dict[str, object]:
    rule = _rule(source)
    if not mounted:
        return {
            "schema_version": "3.10.0",
            "components": [_component("all", ["sample"])],
            "rules": [rule],
        }
    inside = {
        "schema_version": "3.10.0",
        "components": [_component("inside", ["sample"])],
        "rules": [rule],
    }
    return {
        "schema_version": "3.10.0",
        "components": [_component("all", ["sample"], inside="inside.json")],
        "rules": [],
        "_inside": inside,
    }


def _observe(
    tmp_path: Path,
    *,
    roots: tuple[str, ...],
    mounted: bool,
    source: str,
    actual: str = "'literal'",
    parameters: str = "",
    class_method: bool = False,
):
    contract = _contract(mounted=mounted, source=source)
    caller = (
        f"from .storage import page\nclass Handler:\n"
        f"    def run(self, {parameters}): page({actual})\n"
        if class_method
        else f"from .storage import page\ndef run({parameters}): page({actual})\n"
    )
    files = {
        "sample/__init__.py": "",
        "sample/safe/__init__.py": "",
        "sample/safe/storage.py": "def page(query): pass\n",
        "sample/safe/caller.py": caller,
        "sample/core.py": ("from .safe.storage import page\ndef hidden(): page('sibling')\n"),
    }
    inside = contract.pop("_inside", None)
    if inside is not None:
        files["inside.json"] = json.dumps(inside)
    return _observe_tree(tmp_path, files, contract, roots=roots)


def _assessment(observation):
    [row] = [
        item
        for item in rule_assessments(observation, undecided_by_rule={})
        if item.kind == "forbidden_call_argument"
    ]
    return row


def _assert_saved_status(tmp_path: Path, observation, row, columnar: bool) -> None:
    payload = observation_payload(observation)
    encoded = encode_canonical_model(payload) if columnar else payload
    saved = tmp_path / "partial-argument-report.json"
    saved.write_text(json.dumps(encoded))
    [replayed] = run_saved_report(saved).rule_assessments
    assert (replayed.status, replayed.count, replayed.evaluation_proven) == (
        row.status,
        row.count,
        row.evaluation_proven,
    )


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
def test_omitted_sibling_keeps_known_argument_failure_and_unknown(
    tmp_path: Path, mounted: bool, columnar: bool
) -> None:
    result = _observe(
        tmp_path,
        roots=("sample/safe",),
        mounted=mounted,
        source="sample",
    )
    assert result.observation is not None, result.diagnostics
    row = _assessment(result.observation)
    assert row.status == "FAIL" and row.count == 1 and not row.evaluation_proven
    assert any(
        item.kind == "forbidden_call_argument" for item in result.observation.records("violations")
    )
    assert any(
        item.kind == "call_argument_limit" for item in result.observation.records("unknowns")
    )
    _assert_saved_status(tmp_path, result.observation, row, columnar)


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
def test_omitted_sibling_prevents_false_pass_without_visible_failure(
    tmp_path: Path, mounted: bool, columnar: bool
) -> None:
    result = _observe(
        tmp_path,
        roots=("sample/safe",),
        mounted=mounted,
        source="sample",
        actual="spec",
        parameters="spec",
    )
    assert result.observation is not None, result.diagnostics
    row = _assessment(result.observation)
    assert row.status == "UNKNOWN" and not row.evaluation_proven
    assert row.count == 0
    assert not result.observation.records("violations")
    assert any(
        item.kind == "call_argument_limit" for item in result.observation.records("unknowns")
    )
    _assert_saved_status(tmp_path, result.observation, row, columnar)


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
@pytest.mark.parametrize(
    ("source", "class_method"),
    [
        ("sample.safe", False),
        ("sample.safe.caller.run", False),
        ("sample.safe.caller.Handler.run", True),
    ],
)
def test_narrow_rule_source_is_complete_inside_partial_scan(
    tmp_path: Path, mounted: bool, columnar: bool, source: str, class_method: bool
) -> None:
    result = _observe(
        tmp_path,
        roots=("sample/safe",),
        mounted=mounted,
        source=source,
        actual="spec",
        parameters="spec",
        class_method=class_method,
    )
    assert result.observation is not None, result.diagnostics
    row = _assessment(result.observation)
    assert row.status == "PASS" and row.count == 0 and row.evaluation_proven
    assert not any(
        item.kind == "call_argument_limit" for item in result.observation.records("unknowns")
    )
    _assert_saved_status(tmp_path, result.observation, row, columnar)
